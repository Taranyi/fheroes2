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

"""Verify the complete bounded Gym contract against native adventure/choice/battle sessions."""

from contextlib import contextmanager
import os
import unittest
from unittest import mock

import test_world_state as support
import test_battle as battle_support
from fheroes2_env import EngineError, EngineTimeoutError

try:
    import numpy as np
    import gymnasium as gym
    from gymnasium.utils.env_checker import check_env
    from fheroes2_env.gym_env import HeroesEnv, make_env
    from fheroes2_env.gym_candidates import ProfileLimitError
except ImportError:
    gym = None

ROOT = support.ROOT
SAVE = ROOT / "build/python-env-baseline/fixtures/other-side-day1.sav"


@unittest.skipIf(gym is None, "Install the optional gym extra")
class HeroesEnvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        for profile in ("choices-chest", "choices-recruit", "artifacts", "battles-heroes", "battles-loss", "gym-victory"):
            if not (ROOT / f"build/python-env-baseline/fixtures/{profile}-day1.sav").is_file():
                raise unittest.SkipTest("Prepare native fixtures with script/windows/python-env-artifact-fixture.ps1; see docs/PYTHON_ENV_GYM.md")

    @contextmanager
    def environment(self, *, profile=None, save=None, **kwargs):
        path = ROOT / f"build/python-env-baseline/fixtures/{profile}-day1.sav" if profile else (save or SAVE)
        with support.WorldStateTests().session() as (parent, directory):
            with HeroesEnv(executable=support.EXECUTABLE, save=path, env=parent._env, **kwargs) as env:
                yield env, directory

    def select(self, env, name, **params):
        for index, cmd in enumerate(env._commands):
            if cmd["action"] == name and all(cmd["params"].get(k) == v for k, v in params.items()):
                return index
        self.fail(f"No legal {name} candidate for {params}")

    def move(self, env):
        return env.step(self.select(env, "hero.move", hero_id=52, x=32, y=25))

    def finish(self, env, *, passive=False):
        for _ in range(600):
            phase = env._decision["phase"]
            if phase == "battle":
                battle = env._decision["battle"]
                choice = next(a for a in battle["actions"] if a["kind"] == "skip") if passive else battle_support._example.select_action(battle, use_spells=True)
                result = env.step(self.select(env, "battle.act", action_id=choice["action_id"]))
            elif phase == "choice":
                result = env.step(0)
            else:
                return
            self.assertTrue(env.observation_space.contains(result[0]))
            self.assertEqual(result[3], False)
            if result[2]:
                return result
        self.fail("Gym policy failed to finish battle/choices")

    def test_official_checker_registration_and_seeded_transitions(self):
        with self.environment(max_steps=10) as (env, _):
            check_env(env, skip_render_check=True)
            expected = []
            for episode in range(2):
                obs, info = env.reset(seed=81)
                trace = []
                for _ in range(3):
                    obs, reward, term, trunc, info = env.step(0)
                    trace.append(info)
                    self.assertTrue(env.observation_space.contains(obs))
                    self.assertEqual((reward, term, trunc), (0, False, False))
                if episode:
                    self.assertEqual(trace, expected)
                expected = trace
        with make_env(executable=support.EXECUTABLE, save=SAVE, max_steps=1) as wrapped:
            self.assertEqual(wrapped.spec.id, "Fheroes2-v0")
            obs, _ = wrapped.reset(seed=1)
            self.assertTrue(wrapped.step(wrapped.action_space.sample(mask=obs["action_mask"]))[3])

    def test_no_render_calls_omniscient_fixed_shapes_and_independent_storage(self):
        with self.environment(max_steps=4) as (env, directory):
            with mock.patch("fheroes2_env.session.HeroesSession.render", side_effect=AssertionError("Unexpected render")):
                obs, info = env.reset(seed=6)
                self.assertEqual(env.render(), None)
                self.assertTrue(any(p["is_ai"] for p in info["state"]["players"]))
                self.assertEqual(int(obs["hero_mask"].sum()), len(info["state"]["heroes"]))
                self.assertEqual(int(obs["castle_mask"].sum()), len(info["state"]["castles"]))
                self.assertEqual(int(obs["action_mask"].sum()), len(info["actions"]))
                mask = env.action_masks()
                mask[:] = False
                obs["action_mask"][:] = 0
                info["actions"].clear()
                info["state"]["players"].clear()
                result = env.step(0)
                self.assertTrue(result[0]["action_mask"].any())
                self.assertTrue(result[4]["state"]["players"])
                self.assertFalse(env._session.runtime_info()["video_initialized"])
            self.assertEqual(list(directory.iterdir()), [])

    def test_masked_bad_actions_do_not_advance_and_time_limit_is_separate(self):
        with self.environment(max_steps=2) as (env, _):
            obs, _ = env.reset(seed=1)
            before, decision = env._session.get_state(), env._session.get_decision()
            for action in (True, -1, env.max_actions, 1.5):
                with self.assertRaises(ValueError):
                    env.step(action)
                self.assertEqual(env._session.get_state(), before)
                self.assertEqual(env._session.get_decision(), decision)
            rejected = env.step(len(env._commands))
            self.assertFalse(rejected[4]["action_accepted"])
            self.assertEqual(rejected[4]["rejection"]["code"], "masked_action")
            self.assertEqual(env._session.get_state(), before)
            self.assertEqual(env._session.get_decision(), decision)
            env.reset(seed=1)
            self.assertEqual(env.step(0)[1:4], (0.0, False, False))
            self.assertEqual(env.step(0)[1:4], (0.0, False, True))
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(0)
            env.reset(seed=1)
            self.assertEqual(env._steps, 0)

    def test_native_mask_validation_preserves_payload_decision_and_rng(self):
        with self.environment() as (env, _), support.WorldStateTests().session() as (reference, _):
            env.reset(seed=27)
            reference.reset(save=SAVE, seed=27)
            before, decision = env._session.get_state(), env._session.get_decision()
            for _ in range(2):
                env._refresh()
                self.assertEqual(env._session.get_state(), before)
                self.assertEqual(env._session.get_decision(), decision)
            env.step(0)
            reference.end_turn(token=reference.get_decision()["token"])
            self.assertEqual(env._session.get_state(), reference.get_state())

    def test_every_advertised_initial_command_executes_from_same_state(self):
        with self.environment() as (env, _):
            _, info = env.reset(seed=11)
            commands = info["actions"]
            for cmd in commands:
                with self.subTest(command=cmd):
                    # This checks the entire initial mask, including all exact split/recruit quantities.
                    episode = env._session.reset(save=SAVE, seed=11)
                    env._session.step(cmd["action"], params=cmd["params"], token=episode["decision"]["token"])

    def test_chest_and_level_up_choices_stay_inside_episode(self):
        with self.environment(profile="choices-chest", max_steps=100) as (env, _):
            env.reset(seed=2)
            obs, reward, term, trunc, info = self.move(env)
            self.assertEqual((info["phase"], reward, term, trunc), ("choice", 0, False, False))
            self.assertTrue(obs["choice"][0])
            self.assertEqual({c["params"]["value"] for c in info["actions"]}, set(env._decision["pending_choice"]["options"]))
            env.step(self.select(env, "choice.answer", value=0))
            self.finish(env)
            self.assertEqual(env._decision["phase"], "adventure")
            self.assertGreater(next(h for h in env._state["heroes"] if h["id"] == 52)["experience"], 49)

    def test_live_battle_mask_contains_every_native_candidate_and_returns_to_adventure(self):
        with self.environment(profile="battles-heroes", max_steps=1000) as (env, _):
            env.reset(seed=9)
            self.move(env)
            while env._decision["phase"] == "choice":
                env.step(0)
            self.assertEqual(env._decision["phase"], "battle")
            self.assertEqual(len(env._commands), len(env._decision["battle"]["actions"]))
            self.assertEqual([c["params"]["action_id"] for c in env._commands], list(range(len(env._commands))))
            self.assertTrue(env._observation["battle_unit_mask"].any())
            self.finish(env)
            self.assertEqual(env._decision["phase"], "adventure")
            self.assertTrue(any(e["type"] == "battle_completed" for e in env._decision["events"]))

    def test_terminal_loss_reward_once_and_reset_from_terminal(self):
        with self.environment(profile="battles-loss", max_steps=1000) as (env, _):
            env.reset(seed=99)
            self.move(env)
            self.finish(env, passive=True)
            last = None
            for _ in range(80):
                if env._decision["phase"] == "terminal":
                    break
                last = env.step(0)
                if env._decision["phase"] in ("choice", "battle"):
                    finished = self.finish(env, passive=True)
                    if finished is not None:
                        last = finished
            self.assertEqual(env._decision["phase"], "terminal")
            self.assertEqual(last[1:4], (-1.0, True, False))
            self.assertFalse(last[0]["action_mask"].any())
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(0)
            obs, _ = env.reset(seed=99)
            self.assertTrue(obs["action_mask"].any())

    def test_limits_raise_instead_of_truncating_valid_entities_or_actions(self):
        for options in ({"max_map_size": 35}, {"max_heroes": 1}, {"max_castles": 1}, {"max_actions": 2}):
            with self.subTest(options=options), self.environment(**options) as (env, _):
                with self.assertRaises(ProfileLimitError):
                    env.reset(seed=1)
                self.assertIsNone(env._session)
        with self.environment(profile="battles-heroes", max_battle_units=1) as (env, _):
            env.reset(seed=9)
            with self.assertRaises(ProfileLimitError):
                self.move(env)
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(0)

    def test_native_victory_reward_and_terminal_wins_over_time_limit(self):
        with self.environment(profile="gym-victory", max_steps=1) as (env, _):
            env.reset(seed=5)
            obs, reward, terminated, truncated, info = env.step(0)
            self.assertEqual((reward, terminated, truncated), (1.0, True, False))
            self.assertTrue(info["state"]["game_result"] & 0x20)
            self.assertFalse(obs["action_mask"].any())
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(0)

    def test_render_views_are_optional_read_only_and_return_rgb(self):
        for view in ("adventure", "hero", "castle", "auto"):
            with self.subTest(view=view), self.environment(render_mode="rgb_array", render_view=view, width=64, height=64) as (env, _):
                env.reset(seed=4)
                before, decision = env._session.get_state(), env._session.get_decision()
                image = env.render()
                self.assertEqual((image.shape, image.dtype), ((64, 64, 3), np.dtype("uint8")))
                self.assertTrue(np.array_equal(env.render(), image))
                self.assertEqual(env._session.get_state(), before)
                self.assertEqual(env._session.get_decision(), decision)
        with self.environment(profile="battles-heroes", render_mode="rgb_array", width=64, height=64) as (env, _):
            env.reset(seed=9)
            self.move(env)
            self.assertEqual(env._decision["phase"], "battle")
            self.assertEqual(env.render().shape, (64, 64, 3))

    def test_two_episodes_mask_sampling_and_engine_failures_are_not_episode_results(self):
        with self.environment(max_steps=20) as (env, _):
            for episode in range(2):
                obs, _ = env.reset(seed=episode + 1)
                for step in range(20):
                    action = env.action_space.sample(mask=obs["action_mask"])
                    obs, reward, term, trunc, _ = env.step(action)
                    self.assertTrue(env.observation_space.contains(obs))
                    if term or trunc:
                        break
                self.assertTrue(term or trunc)
            env.reset(seed=1)
            with mock.patch.object(env._session, "step", side_effect=EngineTimeoutError("deadline")):
                with self.assertRaises(EngineTimeoutError):
                    env.step(0)
            with self.assertRaises(gym.error.ResetNeeded):
                env.step(0)
            env.reset(seed=1)
            self.assertEqual(env.step(0)[1], 0)

    def test_native_batch_rejects_stale_tokens_and_non_adventure_without_mutation(self):
        with self.environment(profile="choices-chest") as (env, _):
            env.reset(seed=1)
            token = env._decision["token"]
            env.step(0)
            before = env._session.get_state()
            with self.assertRaises(EngineError) as error:
                env._session.check_actions([{"action": "turn.end", "params": {}}], token=token)
            self.assertEqual(error.exception.code, "stale_decision")
            self.assertEqual(env._session.get_state(), before)

            env.reset(seed=1)
            self.move(env)
            before = env._session.get_state()
            with self.assertRaises(EngineError) as error:
                env._session.check_actions([], token=env._decision["token"])
            self.assertEqual(error.exception.code, "unsupported_state")
            self.assertEqual(env._session.get_state(), before)

    def test_inventory_meeting_and_market_categories_use_native_masks(self):
        with self.environment(profile="artifacts") as (env, _):
            env.reset(seed=2)
            env.step(self.select(env, "castle.refresh_heroes", castle_id=896))
            self.move(env)
            env.step(self.select(env, "castle.hire", castle_id=896, hero_id=46))
            env.step(self.select(env, "hero.meet", hero_id=52, other_hero_id=46))
            before, decision = env._session.get_state(), env._session.get_decision()
            env._refresh()
            self.assertEqual(env._session.get_state(), before)
            self.assertEqual(env._session.get_decision(), decision)
            self.assertTrue(any(c["action"] == "artifact.swap" for c in env._commands))
            env.step(self.select(env, "artifact.transfer", source={"hero_id": 52, "slot": 3}, target={"hero_id": 46, "slot": 5}))
            env.step(self.select(env, "hero.end_meeting"))
            if env._session.get_castle_options(896)["market"]["marketplace_count"] == 0:
                env.step(self.select(env, "castle.build", castle_id=896, building_id=128))
            options = env._session.get_castle_options(896)
            for trade in options["market"]["trades"]:
                lots = {c["params"]["lots"] for c in env._commands if c["action"] == "market.trade"
                        and c["params"]["resource_from"] == trade["resource_from"] and c["params"]["resource_to"] == trade["resource_to"]}
                self.assertEqual(lots, set(range(1, trade["max_lots"] + 1)))
            env.step(next(i for i, c in enumerate(env._commands) if c["action"] == "market.trade"))

    def test_quantity_choice_and_new_map_reset_options(self):
        with self.environment(profile="choices-recruit") as (env, _):
            env.reset(seed=7)
            self.move(env)
            while env._decision["phase"] == "choice" and env._decision["pending_choice"]["kind"] != "army.recruit_count":
                env.step(0)
            self.assertEqual({c["params"]["value"] for c in env._commands}, set(range(5)))
            monster = env._decision["pending_choice"]["values"]["monster_id"]
            env.step(self.select(env, "choice.answer", value=2))
            hero = next(h for h in env._state["heroes"] if h["id"] == 52)
            self.assertEqual(sum(t["count"] for t in hero["army"] if t and t["monster_id"] == monster), 2)
            _, info = env.reset(seed=4, options={"map_path": ROOT / "maps/THEOTHER.MP2"})
            initial = info["state"]
            env.step(0)
            _, info = env.reset(seed=4)
            self.assertEqual(info["state"], initial)


if __name__ == "__main__":
    unittest.main()
