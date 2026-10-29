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

"""Check the optional Gym API against the actual native engine, not a fake world."""

from contextlib import contextmanager
import os
import tempfile
import unittest
from unittest import mock

import test_world_state as support
from fheroes2_env import EngineError

try:
    import gymnasium as gym
    from gymnasium.utils.env_checker import check_env
    import numpy as np
    from fheroes2_env.gym_preview import make_preview
except ImportError:
    gym = None


@unittest.skipIf(gym is None, "Install the optional gym or viewer extra")
class GymPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        cls.save = support.ROOT / support.WorldStateTests.fixtures[0]["path"]

    @contextmanager
    def preview(self, **kwargs):
        work = support.ROOT / "build/python-env-state-tests"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            with mock.patch.dict(os.environ, {"APPDATA": directory, "FHEROES2_DATA": str(support.ROOT)}):
                with make_preview(executable=support.EXECUTABLE, save=self.save, width=96, height=96, **kwargs) as env:
                    yield env
            self.assertEqual(os.listdir(directory), [])

    def hero(self, info):
        return next(h for h in info["state"]["heroes"] if h["id"] == info["hero_id"])

    def test_real_rgb_observation_and_omniscient_state(self):
        with self.preview(render_mode="rgb_array") as env:
            obs, info = env.reset(seed=123)
            self.assertEqual(obs.shape, (96, 96, 3))
            self.assertEqual(obs.dtype, np.uint8)
            self.assertTrue(env.observation_space.contains(obs))
            self.assertTrue(any(p["is_ai"] and p["hero_ids"] for p in info["state"]["players"]))
            self.assertEqual(info["state"]["perspective"], "omniscient")
            np.testing.assert_array_equal(env.render(), obs)
            obs[:] = 0
            self.assertTrue(env.render().any())
            runtime = env.unwrapped._session.runtime_info()
            self.assertTrue(runtime["headless"])
            self.assertFalse(runtime["video_initialized"])
            self.assertFalse(runtime["audio_initialized"])

    def test_movement_and_native_ai_turn(self):
        with self.preview() as env:
            env.reset()
            _, reward, terminated, truncated, info = env.step(4)
            self.assertEqual((reward, terminated, truncated), (0.0, False, False))
            self.assertTrue(info["action_accepted"])
            self.assertEqual(self.hero(info)["position"]["y"], 25)
            self.assertEqual(self.hero(info)["move_points"], 900)
            _, _, _, _, info = env.step(8)
            self.assertEqual(info["state"]["date"]["total_days"], 2)
            self.assertIn("ai_turn_completed", [event["type"] for event in info["events"]])

    def test_rejection_time_limit_and_fresh_reset(self):
        with self.preview(max_steps=2) as env:
            _, initial = env.reset(seed=42)
            old_process = env.unwrapped._session._process
            samples = [env.action_space.sample() for _ in range(20)]
            before = env.unwrapped._session.get_state()
            # The original castle north of Roxana is outside the current adventure_basic profile.
            _, _, terminated, truncated, info = env.step(0)
            self.assertFalse(info["action_accepted"])
            self.assertIsNotNone(info["rejection"])
            self.assertEqual(env.unwrapped._session.get_state(), before)
            self.assertFalse(terminated or truncated)
            _, _, terminated, truncated, _ = env.step(4)
            self.assertEqual((terminated, truncated), (False, True))
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(4)
            _, restored = env.reset(seed=42)
            self.assertIsNotNone(old_process.poll())
            self.assertEqual(restored["state"]["date"], initial["state"]["date"])
            self.assertEqual(self.hero(restored)["position"], self.hero(initial)["position"])
            self.assertEqual([env.action_space.sample() for _ in range(20)], samples)

    def test_bad_actions_do_not_reach_the_engine(self):
        with self.preview() as env:
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(4)
            env.reset()
            before = env.unwrapped._session.get_state()
            for action in (-1, 9, True, np.bool_(True), "south", 4.0):
                with self.subTest(action=action), self.assertRaises(ValueError):
                    env.step(action)
            self.assertEqual(env.unwrapped._session.get_state(), before)

    def test_native_ai_battle_yields_an_explicit_boundary_or_a_real_terminal_result(self):
        with self.preview(max_steps=100) as env:
            env.reset()
            for _ in range(60):
                try:
                    _, _, terminated, truncated, info = env.step(8)
                except EngineError as error:
                    self.assertEqual(error.code, "unsupported_battle")
                    self.assertEqual(env.unwrapped._session.get_decision()["phase"], "battle")
                    self.assertTrue(env.unwrapped._needs_reset)
                    break
                self.assertFalse(truncated)
                if terminated:
                    self.assertEqual(info["state"]["phase"], "terminal")
                    self.assertNotEqual(info["state"]["game_result"], 0)
                    self.assertTrue(any(e["type"] == "battle_completed" for e in info["events"]))
                    break
            else:
                self.fail("The reference scenario should reach a human battle boundary")

    def test_reference_walk_returns_near_castle_and_reaches_time_limit(self):
        with self.preview() as env:
            env.reset()
            for action in (4, 4, 5, 5, 5, 8, 1, 1, 1, 0, 8, 8):
                _, _, terminated, truncated, info = env.step(action)
                self.assertTrue(info["action_accepted"], info["rejection"])
            self.assertEqual((terminated, truncated), (False, True))
            self.assertEqual(self.hero(info)["position"], {"index": 932, "x": 32, "y": 25})
            self.assertEqual(info["state"]["date"]["total_days"], 4)

    def test_gymnasium_official_checker(self):
        with self.preview() as env:
            self.assertTrue(env.spec.nondeterministic)
            check_env(env.unwrapped, skip_render_check=True)

    def test_choice_boundary_is_an_explicit_error_and_can_reset(self):
        save = support.ROOT / "build/python-env-baseline/fixtures/choices-chest-day1.sav"
        if not save.is_file():
            self.skipTest("Prepare native choice fixtures")
        with self.preview(max_steps=1) as env:
            env.unwrapped.save = save
            env.reset()
            with self.assertRaises(EngineError) as failed:
                env.step(4)
            self.assertEqual(failed.exception.code, "unsupported_choice")
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(8)
            env.reset()
            self.assertEqual(env.unwrapped._decision["phase"], "adventure")

    def test_battle_boundary_is_an_explicit_error_and_can_reset(self):
        save = support.ROOT / "build/python-env-baseline/fixtures/battles-heroes-day1.sav"
        if not save.is_file():
            self.skipTest("Prepare native battle fixtures")
        with self.preview(max_steps=1) as env:
            env.unwrapped.save = save
            env.reset()
            with self.assertRaises(EngineError) as failed:
                env.step(4)
            self.assertEqual(failed.exception.code, "unsupported_battle")
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(8)
            env.reset()
            self.assertEqual(env.unwrapped._decision["phase"], "adventure")

    def test_optional_viewer_lifecycle_without_a_desktop(self):
        try:
            import pygame
        except ImportError:
            self.skipTest("Install the viewer extra")
        with mock.patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}):
            with self.preview(render_mode="human", fps=0) as env:
                env.reset()
                self.assertTrue(pygame.display.get_init())
                self.assertFalse(env.unwrapped._session.runtime_info()["video_initialized"])
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                _, _, terminated, truncated, _ = env.step(4)
                self.assertTrue(env.unwrapped.window_closed)
                self.assertFalse(terminated or truncated)
            self.assertFalse(pygame.display.get_init())


if __name__ == "__main__":
    unittest.main()
