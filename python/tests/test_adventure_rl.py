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

"""Adventure reward invariants, true native transitions and real PPO reload."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

import test_world_state as support

sys.path.insert(0, str(support.ROOT / 'python/examples'))
try:
    import gymnasium as gym
    import numpy as np
    import torch
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.vec_env import DummyVecEnv
except ImportError:
    task = None
else:
    import adventure_task as task
    from packed_policy import PackedCandidatePolicy


@unittest.skipIf(task is None, 'Install optional battle-rl extra')
class AdventureRLTests(unittest.TestCase):
    def environment(self, directory, **kwargs):
        return task.AdventureTask(support.EXECUTABLE, directory, **kwargs)

    def test_official_gym_contract_and_padding_do_not_advance_the_world(self):
        from gymnasium.utils.env_checker import check_env
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.environment(directory) as env:
                check_env(env, skip_render_check=True)
                env.reset(seed=7)
                before = env.game.get_state(include_serialized=False)
                obs, reward, terminated, truncated, info = env.step(task.MAX_ACTIONS - 1)
                self.assertEqual((reward, terminated, truncated, info['action_accepted']), (-.005, False, False, False))
                self.assertEqual(env.game.get_state(include_serialized=False), before)

    def test_macro_actions_are_native_legal_and_recruitment_and_transfer_conserve_counts(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.environment(directory) as env:
                obs, info = env.reset(seed=7)
                self.assertTrue(all(env.game.check_actions(env.commands, token=env.decision['token'])))
                info['state']['players'][0]['funds']['gold'] = -999
                info['actions'].clear()
                obs.fill(0)
                self.assertGreater(env.state['players'][0]['funds']['gold'], 0)
                self.assertTrue(env.action_masks().any())
                initial = dict(env.current_metrics)
                index = next(i for i, c in enumerate(env.commands) if c['action'] == 'castle.recruit')
                count = env.commands[index]['params']['count']
                env.step(index)
                self.assertEqual(env.current_metrics['army'] - initial['army'], count)
                previous = dict(env.current_metrics)
                index = next(i for i, c in enumerate(env.commands) if c['action'] == 'army.transfer')
                transfer = env.commands[index]['params']['count']
                env.step(index)
                self.assertEqual(env.current_metrics['army'], previous['army'])
                self.assertEqual(env.current_metrics['mobile'] - previous['mobile'], transfer)

    def test_shaping_does_not_reward_split_trade_or_discounted_cycles(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.environment(directory) as env:
                env.reset(seed=7)
                a = dict(env.current_metrics)
                b = dict(a, army=a['army'] + 20, mobile=a['mobile'] + 20)
                outward = task.reward_parts(a, b, 0., False, 'dense')['potential']
                home = task.reward_parts(b, a, 0., False, 'dense')['potential']
                self.assertAlmostEqual(outward + task.GAMMA * home, (task.GAMMA ** 2 - 1) * task.potential(a))
                self.assertLessEqual(outward + task.GAMMA * home, 0)
                self.assertEqual(task.potential(a), task.potential(dict(a, gold=0)))
                state = deepcopy(env.state)
                hero = next(h for h in state['heroes'] if h['active'] and h['owner'] == env.player)
                source = next(t for t in hero['army'] if t and t['count'] > 1)
                target = next(i for i, t in enumerate(hero['army']) if t is None)
                source['count'] -= 1
                hero['army'][target] = dict(source, count=1)
                self.assertEqual(task.metrics(state, env.player), env.current_metrics)

    def test_native_long_routes_and_scouting_feature_match_real_transitions(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.environment(directory) as env:
                env.reset(seed=7)
                heroes = {h['id']: h for h in env.state['heroes']}
                moves = [(i, c) for i, c in enumerate(env.commands) if c['action'] == 'hero.move'
                         and env.state['map']['tiles'][c['params']['y'] * env.state['map']['width']
                                                      + c['params']['x']]['object_under_hero'] < 128]
                def distance(item):
                    p = item[1]['params']
                    h = heroes[p['hero_id']]['position']
                    return max(abs(p['x'] - h['x']), abs(p['y'] - h['y']))
                index, command = max(moves, key=distance)
                self.assertGreater(distance((index, command)), 1)
                p = command['params']
                previous = heroes[p['hero_id']]['move_points']
                env.step(index)
                hero = next(h for h in env.state['heroes'] if h['id'] == p['hero_id'])
                self.assertEqual((hero['position']['x'], hero['position']['y']), (p['x'], p['y']))
                self.assertLess(hero['move_points'], previous)
                self.assertEqual(task.scouting_gain(env.state, p['x'], p['y'], 0, env.player), 0)
                env.reset(seed=7)
                for index, command in enumerate(env.commands):
                    if command['action'] != 'hero.move':
                        continue
                    p = command['params']
                    hero = heroes[p['hero_id']]
                    if max(abs(p[k] - hero['position'][k]) for k in ('x', 'y')) != 1:
                        continue
                    tile = env.state['map']['tiles'][p['y'] * env.state['map']['width'] + p['x']]
                    if tile['object_under_hero'] >= 128:
                        continue
                    predicted = task.scouting_gain(env.state, p['x'], p['y'], hero['scouting_distance'], env.player)
                    self.assertAlmostEqual(env.obs[index, task.F['scout_gain']], predicted / 50, places=6)
                    explored = env.current_metrics['explored']
                    env.step(index)
                    self.assertEqual(env.current_metrics['explored'] - explored, predicted)
                    break
                else:
                    self.fail('Missing empty adjacent scouting probe')

    def test_training_limit_bootstraps_but_native_time_loss_is_absorbing(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.environment(directory, max_steps=1) as env:
                env.reset(seed=7)
                obs, _, terminated, truncated, info = env.step(0)
                self.assertEqual((terminated, truncated, info['native_reward']), (False, True, 0.))
                self.assertTrue(obs[:, 0].any())
                with self.assertRaises(gym.error.ResetNeeded):
                    env.step(0)
            with self.environment(directory, max_steps=64) as env:
                env.reset(seed=123, options={'map_path': support.ROOT / 'maps/7_deserts.fh2m'})
                while True:
                    previous = dict(env.current_metrics)
                    obs, _, terminated, truncated, info = env.step(0)
                    if terminated or truncated:
                        break
                self.assertTrue(terminated)
                self.assertFalse(truncated)
                self.assertEqual(info['native_reward'], -1.)
                self.assertEqual(info['reward_parts']['potential'], -task.potential(previous))
                self.assertFalse(obs[:, 0].any())

    def test_actual_ppo_updates_reload_and_initial_distribution_are_correct(self):
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            env = self.environment(directory, max_steps=16, rich_info=False)
            vec = DummyVecEnv([lambda: env])
            try:
                model = MaskablePPO(PackedCandidatePolicy, vec, seed=7, device='cpu', n_steps=16, batch_size=16, n_epochs=2)
                obs = vec.reset()
                tensor, _ = model.policy.obs_to_tensor(obs)
                mask = env.action_masks()
                probabilities = model.policy.get_distribution(tensor, mask[None]).distribution.probs.detach().numpy()[0]
                np.testing.assert_allclose(probabilities[mask], 1 / mask.sum(), atol=1e-7)
                self.assertFalse(probabilities[~mask].any())
                original = model.policy.actor[-1].weight.detach().clone()
                model.learn(32)
                self.assertFalse(torch.equal(original, model.policy.actor[-1].weight))
                obs = env.obs.copy()
                mask = env.action_masks()
                expected = int(model.predict(obs, deterministic=True, action_masks=mask)[0])
                path = Path(directory) / 'policy.zip'
                model.save(path)
                loaded = MaskablePPO.load(path, device='cpu')
                self.assertEqual(int(loaded.predict(obs, deterministic=True, action_masks=mask)[0]), expected)
                self.assertTrue(mask[expected])
            finally:
                vec.close()
            self.assertEqual(env.closed_process['returncode'], 0)


if __name__ == '__main__':
    unittest.main()
