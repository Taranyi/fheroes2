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

"""Equivalence, isolation and real multiprocessing for optimized Gym battle transport."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

import test_world_state as support
from fheroes2_env import EngineError
from fheroes2_env.gym_candidates import ProfileLimitError

PERF = None
try:
    import numpy as np
    import sb3_contrib
except ImportError:
    pass
else:
    sys.path.insert(0, str(support.ROOT / 'python/examples'))
    import battle_vector as PERF
    from fheroes2_env.battle_env import BattleEnv, BATTLE_KEYS
    from fheroes2_env.gym_env import HeroesEnv


@unittest.skipIf(PERF is None, 'Install optional battle-rl extra')
class PerformanceTests(unittest.TestCase):
    def test_official_gym_checker_accepts_the_small_profile(self):
        from gymnasium.utils.env_checker import check_env
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with BattleEnv(executable=support.EXECUTABLE, battle_config=PERF.advanced.configuration('field'),
                           env=PERF.advanced.base.engine_environment(directory)) as env:
                check_env(env, skip_render_check=True)

    def test_full_info_is_still_a_complete_isolated_world(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with PERF.advanced.AdvancedTask(support.EXECUTABLE, directory) as env:
                _, info = env.reset(seed=12, options={'battle_config': PERF.advanced.configuration('field')})
                self.assertEqual(info['state'], env.env._session.get_state(include_serialized=False))
                before = deepcopy(env.env._state)
                info['state']['map']['tiles'][0]['metadata'][0] = -999
                info['actions'].clear()
                self.assertEqual(env.env._state, before)
                self.assertGreater(env.env.action_masks().sum(), 0)

    def test_full_and_small_battle_profiles_have_identical_observations_rewards_and_native_traces(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with PERF.advanced.AdvancedTask(support.EXECUTABLE, directory) as full, PERF.TrainingTask(support.EXECUTABLE, directory) as small:
                for context in PERF.advanced.CONTEXTS:
                    options = {'battle_config': PERF.advanced.configuration(context)}
                    a, _ = full.reset(seed=17, options=options)
                    b, _ = small.reset(seed=17, options=options)
                    for _ in range(160):
                        np.testing.assert_array_equal(a, b)
                        for key in BATTLE_KEYS:
                            np.testing.assert_array_equal(full.raw_obs[key], small.raw_obs[key])
                        action = PERF.advanced.choose(full, a, 'rule', np.random.default_rng(2))
                        a, ra, ta, xa, ia = full.step(action)
                        b, rb, tb, xb, ib = small.step(action)
                        self.assertEqual((ra, ta, xa), (rb, tb, xb))
                        if ta or xa:
                            self.assertEqual(ia['state']['standalone_battle']['result'], ib['battle_result'])
                            break
                    else:
                        self.fail('Battle exceeded its task horizon')

    def test_process_reuse_aborts_live_battle_invalidates_token_and_recovers_dead_process(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with BattleEnv(executable=support.EXECUTABLE, battle_config=PERF.advanced.configuration('field'),
                           env=PERF.advanced.base.engine_environment(directory), reuse_process=True) as env:
                first, _ = env.reset(seed=44)
                process, token = env._session._process, env._decision['token']
                again, _ = env.reset(seed=44)
                self.assertEqual(process.pid, env._session.pid)
                for key in BATTLE_KEYS:
                    np.testing.assert_array_equal(first[key], again[key])
                with self.assertRaises(EngineError) as error:
                    env._session.step('battle.act', token=token, params={'action_id': 0})
                self.assertEqual(error.exception.code, 'stale_decision')
                process.kill()
                process.wait()
                recovered, _ = env.reset(seed=44)
                self.assertNotEqual(process.pid, env._session.pid)
                for key in BATTLE_KEYS:
                    np.testing.assert_array_equal(first[key], recovered[key])

    def test_small_profile_padding_rejection_and_capacity_failure_are_explicit(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            options = dict(executable=support.EXECUTABLE, battle_config=PERF.advanced.configuration('field'),
                           env=PERF.advanced.base.engine_environment(directory))
            with BattleEnv(**options, max_steps=1) as env:
                env.reset(seed=44)
                _, reward, terminated, truncated, info = env.step(511)
                self.assertEqual((reward, terminated, truncated, info['action_accepted']), (0., False, True, False))
                self.assertEqual(info['rejection']['code'], 'masked_action')
                self.assertNotIn('state', info)
            with BattleEnv(**options, max_actions=1) as env:
                with self.assertRaises(ProfileLimitError) as error:
                    env.reset(seed=44)
                self.assertIn('max_actions', str(error.exception))

    def test_small_profile_full_world_query_is_real_and_read_only(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with BattleEnv(executable=support.EXECUTABLE, battle_config=PERF.advanced.configuration('defense'),
                           env=PERF.advanced.base.engine_environment(directory)) as env:
                obs, _ = env.reset(seed=44)
                world = env.world_snapshot()
                self.assertGreater(len(world['heroes']), 0)
                self.assertEqual(len(world['battle']['units']), 6)
                for key in BATTLE_KEYS:
                    np.testing.assert_array_equal(obs[key], env._observation[key])

    def test_real_spawn_parallel_ppo_uses_independent_engines_and_reaps_them(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            report = PERF.train(support.EXECUTABLE, Path(directory), workers=2, steps=256)
            self.assertEqual(report['timesteps'], 256)
            self.assertEqual(report['rollout_batch'], 256)
            self.assertEqual(len({r['python_pid'] for r in report['workers_status']}), 2)
            self.assertEqual(len({r['native_pid'] for r in report['workers_status']}), 2)
            self.assertTrue(all(r['native_spawns'] == 1 for r in report['workers_status']))
            self.assertTrue(all(r['closed_native']['returncode'] is not None for r in report['closed_workers']))

    def test_reuse_is_not_silently_applied_to_adventure(self):
        with self.assertRaises(ValueError):
            HeroesEnv(executable=support.EXECUTABLE, map_path=support.ROOT / 'maps/THEOTHER.MP2', reuse_process=True)


if __name__ == '__main__':
    unittest.main()
