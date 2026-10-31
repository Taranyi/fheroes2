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

"""Optional SB3 battle wrapper and policy contracts."""

from pathlib import Path
import sys
import tempfile
import unittest

import test_world_state as support

PPO = None
try:
    import sb3_contrib
    import torch
    import numpy as np
except ImportError:
    pass
else:
    sys.path.insert(0, str(support.ROOT / 'python/examples'))
    import battle_ppo as PPO


@unittest.skipIf(PPO is None, 'Install optional battle-rl extra')
class BattlePPOTests(unittest.TestCase):
    def test_reward_has_signed_damage_and_no_healing_farm(self):
        initial = np.array([100., 200.])
        middle = np.array([80., 100.])
        parts = PPO.reward_parts(initial, middle, initial, 0, 'dense')
        self.assertAlmostEqual(parts['enemy_hp'], .25)
        self.assertAlmostEqual(parts['own_hp'], -.1)
        reverse = PPO.reward_parts(middle, initial, initial, 0, 'dense')
        self.assertAlmostEqual(sum(parts.values()) + sum(reverse.values()), -.004)
        sparse = PPO.reward_parts(initial, middle, initial, 1, 'sparse')
        self.assertEqual(sum(sparse.values()), 1.)

    def test_policy_is_candidate_equivariant_and_masks_padding(self):
        from gymnasium import spaces
        policy = PPO.CandidatePolicy(spaces.Box(-np.inf, np.inf, (256, 24), dtype=np.float32), spaces.Discrete(256), lambda _: .001)
        x = torch.zeros((1, 256, 24))
        x[0, :3, 0] = 1
        x[0, :3, 1:4] = torch.eye(3)
        p = policy.get_distribution(x).distribution.probs.detach().clone()
        np.testing.assert_allclose(p[0, :3].numpy(), [1/3]*3)
        self.assertEqual(float(p[0, 3:].sum()), 0.)
        with torch.no_grad():
            policy.actor[-1].weight.normal_()
        before = policy.get_distribution(x).distribution.probs.detach().clone()
        permuted = x.clone()
        permuted[:, [0, 2]] = x[:, [2, 0]]
        after = policy.get_distribution(permuted).distribution.probs.detach().clone()
        torch.testing.assert_close(before[:, [0, 2]], after[:, [2, 0]])
        torch.testing.assert_close(policy.predict_values(x), policy.predict_values(permuted))

    def test_real_ppo_update_reload_and_terminal_hp(self):
        from sb3_contrib import MaskablePPO
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with PPO.BattleTask(support.EXECUTABLE, directory) as env:
                manifest = PPO.cases('validation', 1)
                obs, info = env.reset(seed=manifest[0]['seed'], options={'battle_config': manifest[0]['config']})
                self.assertTrue(env.observation_space.contains(obs))
                model = MaskablePPO(PPO.CandidatePolicy, env, n_steps=32, batch_size=16, n_epochs=2, seed=7, device='cpu')
                before = model.policy.actor[-1].weight.detach().clone()
                model.learn(64)
                self.assertFalse(torch.equal(before, model.policy.actor[-1].weight))
                path = Path(directory) / 'weights'
                model.save(path)
                restored = PPO.load_model(path)
                score, rows = PPO.evaluate(env, manifest[:1], model, mode='heuristic')
                self.assertEqual(score['wins'], 1)
                self.assertEqual(rows[0]['remaining_hp_fraction'][1], 0.)
                self.assertGreater(rows[0]['reward_parts']['enemy_hp'], 0.)
                _, a = PPO.evaluate(env, manifest[:1], model)
                _, b = PPO.evaluate(env, manifest[:1], restored)
                self.assertEqual(a[0]['action_ids'], b[0]['action_ids'])
                self.assertEqual(a[0]['native_result'], b[0]['native_result'])
                score, rows = PPO.evaluate(env, manifest[:1], mode='uniform_no_retreat')
                self.assertEqual(score['episodes'], 1)
                self.assertTrue(rows[0]['terminated'] or rows[0]['truncated'])

    def test_finite_task_horizon_preserves_native_truncation_without_bootstrap(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with PPO.BattleTask(support.EXECUTABLE, directory) as env:
                config = PPO.configuration('melee', 'grass')
                config['max_rounds'] = 2
                env.reset(seed=32, options={'battle_config': config})
                for _ in range(20):
                    slots, features = PPO.base.action_features(env.raw_obs)
                    skip = np.flatnonzero(features[:, 1 + PPO.base.BATTLE_KINDS.index('skip')])
                    _, _, terminated, truncated, info = env.step(int(slots[skip[0]]))
                    if terminated or truncated:
                        self.assertTrue(terminated)
                        self.assertFalse(truncated)
                        self.assertTrue(info['native_truncated'])
                        self.assertFalse(info['native_terminated'])
                        self.assertEqual(info['native_reward'], 0.)
                        break
                else:
                    self.fail('Native round limit did not end the task')


if __name__ == '__main__':
    unittest.main()
