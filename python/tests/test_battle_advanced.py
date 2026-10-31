###########################################################################
#   fheroes2: https://github.com/ihhub/fheroes2                           #
#   Copyright (C) 2026                                                    #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
###########################################################################

"""Native hard battle features, split isolation, spells, siege and PPO integration."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import test_world_state as support

ADV = None
try:
    import sb3_contrib
    import torch
    import numpy as np
except ImportError:
    pass
else:
    sys.path.insert(0, str(support.ROOT / 'python/examples'))
    import battle_advanced as ADV


@unittest.skipIf(ADV is None, 'Install optional battle-rl extra')
class AdvancedBattleTests(unittest.TestCase):
    def test_checkpoint_selection_cannot_publish_a_warmup_only_model(self):
        callback = ADV.Validation(None, [], Path('unused'), 256, eligible_after=256)
        callback.model = mock.Mock()
        with mock.patch.object(ADV, 'evaluate', side_effect=[({'win_rate': 1., 'own_hp': 1., 'spell_casts': {}}, []),
                                                           ({'win_rate': .5, 'own_hp': .2, 'spell_casts': {}}, [])]):
            callback.assess(256)
            callback.model.save.assert_not_called()
            callback.assess(512)
        self.assertEqual(callback.selected_steps, 512)
        self.assertFalse(callback.checkpoints[0]['eligible'])
        self.assertTrue(callback.checkpoints[1]['eligible'])

    def test_hex_geometry_matches_native_neighbor_parity(self):
        for row, col in ((0, 5), (1, 5), (4, 5), (5, 5)):
            cell = row * 11 + col
            neighbors = (cell - 1, cell + 1, cell + (10 if row % 2 else 11), cell + (11 if row % 2 else 12))
            for neighbor in neighbors:
                self.assertAlmostEqual(float(np.linalg.norm(ADV.xy(cell) - ADV.xy(neighbor))), 1.)

    def test_unseen_armies_and_seeds_are_really_disjoint(self):
        groups = [set(range(4096)), *({c['seed'] for c in ADV.cases(split)} for split in ('validation', 'test', 'ood'))]
        for i, group in enumerate(groups):
            for other in groups[i + 1:]:
                self.assertFalse(group & other)
        training = {m for pair in ADV.ARMIES for army in pair for m, _ in army}
        novel = {m for pair in ADV.UNSEEN_ARMIES for army in pair for m, _ in army}
        self.assertFalse(training & novel)
        self.assertEqual(len(ADV.cases('test')), 36)
        self.assertEqual(len(ADV.cases('ood')), 24)

    def test_all_contexts_have_native_spell_target_features_and_correct_perspective(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with ADV.AdvancedTask(support.EXECUTABLE, directory) as env:
                for context in ADV.CONTEXTS:
                    with self.subTest(context=context):
                        obs, info = env.reset(seed=15, options={'battle_config': ADV.configuration(context)})
                        self.assertTrue(env.observation_space.contains(obs))
                        self.assertEqual(env.color, 2 if context == 'defense' else 1)
                        self.assertEqual(info['player_id'], env.color)
                        self.assertTrue(np.all(env.initial_hp > 0))
                        mask = env.action_masks()
                        self.assertGreater(mask.sum(), 0)
                        self.assertTrue(np.isfinite(obs).all())
                        for kind in ('retreat', 'surrender'):
                            self.assertFalse(np.any(mask & (env.raw_obs['actions'][:, ADV.base.A['battle_kind']] == ADV.base.BATTLE_KINDS.index(kind) + 1)))
                        spell3 = np.flatnonzero(mask & (obs[:, len(ADV.base.FEATURES) + 2] == 1))
                        self.assertGreater(len(spell3), 0)
                        self.assertTrue(np.all(obs[spell3, -len(ADV.EXTRA)] == -1))
                        if context in ('assault', 'defense'):
                            self.assertTrue(np.any(obs[:, len(ADV.base.FEATURES) + 47] == 1))

    def test_spell_does_real_damage_costs_mana_and_obeys_round_cooldown(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with ADV.AdvancedTask(support.EXECUTABLE, directory) as env:
                obs, _ = env.reset(seed=32, options={'battle_config': ADV.configuration('field')})
                before_hp, before_mana = env.previous_hp.copy(), env.previous_mana
                spell = np.flatnonzero(env.action_masks() & (obs[:, len(ADV.base.FEATURES) + 2] == 1))[0]
                obs, reward, terminated, _, info = env.step(int(spell))
                self.assertGreater(before_hp[1], env.previous_hp[1])
                self.assertEqual(before_mana - env.previous_mana, 7)
                self.assertGreater(info['reward_parts']['enemy_hp'], 0)
                self.assertLess(info['reward_parts']['mana'], 0)
                self.assertFalse(terminated)
                spell_col = 1 + ADV.base.BATTLE_KINDS.index('spell')
                self.assertFalse(np.any(obs[:, spell_col]))

    def test_siege_earthquake_is_native_and_spends_mana(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with ADV.AdvancedTask(support.EXECUTABLE, directory) as env:
                obs, _ = env.reset(seed=71, options={'battle_config': ADV.configuration('assault')})
                options = np.flatnonzero(obs[:, len(ADV.base.FEATURES) + 47])
                self.assertEqual(len(options), 1)
                before = env.previous_mana
                _, _, _, _, info = env.step(int(options[0]))
                self.assertTrue(info['action_accepted'])
                self.assertGreater(before, env.previous_mana)

    def test_real_learning_reload_and_no_spell_control(self):
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with ADV.AdvancedTask(support.EXECUTABLE, directory) as env:
                model = ADV.MaskablePPO(ADV.previous.CandidatePolicy, env, n_steps=32, batch_size=16, n_epochs=2, seed=7, device='cpu')
                before = model.policy.actor[-1].weight.detach().clone()
                model.learn(64)
                self.assertFalse(torch.equal(before, model.policy.actor[-1].weight))
                path = Path(directory) / 'model'
                model.save(path)
                reloaded = ADV.previous.load_model(path)
                case = ADV.cases('validation')[:1]
                case[0]['config']['max_rounds'] = 3
                _, a = ADV.evaluate(env, case, model=model)
                _, b = ADV.evaluate(env, case, model=reloaded)
                self.assertEqual(a[0]['trace'], b[0]['trace'])
                self.assertEqual(a[0]['native_result'], b[0]['native_result'])
                _, rows = ADV.evaluate(env, case, model=reloaded, mode='no_spells')
                self.assertFalse(rows[0]['spells'])
                self.assertGreaterEqual(rows[0]['steps'], 1)


if __name__ == '__main__':
    unittest.main()
