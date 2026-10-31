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

"""Exercise restart lifecycle and native seeded episodes with actual engine processes."""

from copy import deepcopy
import queue
import unittest
from unittest import mock

from fheroes2_env import EngineError, EngineTimeoutError
import test_world_state as support
import test_battle as battle_support

ROOT = support.ROOT
SAVE = ROOT / "build/python-env-baseline/fixtures/other-side-day1.sav"
MAP = ROOT / "maps/THEOTHER.MP2"


def semantic(state):
    state = deepcopy(state)
    state.pop("state_version", None)
    return state


class ResetTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()

    def test_repeated_saved_reset_reaps_process_and_invalidates_tokens(self):
        with self.session() as (game, directory):
            episode = game.reset(save=SAVE, seed=123)
            initial = game.get_state()
            for _ in range(3):
                old_process, old_token = game._process, episode["decision"]["token"]
                game.end_turn(token=old_token)
                episode = game.reset(seed=123)
                self.assertIsNotNone(old_process.poll())
                self.assertNotEqual(old_token["session_id"], episode["decision"]["token"]["session_id"])
                self.assertEqual(game.get_state(), initial)
                with self.assertRaises(EngineError) as error:
                    game.end_turn(token=old_token)
                self.assertEqual(error.exception.code, "wrong_session")
            self.assertEqual(list(directory.iterdir()), [])

    def test_saved_seed_preserves_entire_loaded_payload(self):
        with self.session() as (game, _):
            game.load_save(SAVE)
            original = game.get_state()
            for seed in (0, 1, 0xFFFFFFFF):
                game.load_save(SAVE, seed=seed)
                self.assertEqual(semantic(game.get_state()), semantic(original))

    def test_same_save_seed_and_ai_turns_replay_across_processes(self):
        def play(game, seed, render=False):
            episode = game.reset(save=SAVE, seed=seed)
            decision = episode["decision"]
            trace = [game.get_state()]
            for _ in range(3):
                if render:
                    game.render(view="hero", hero_id=52, width=64, height=64)
                decision = game.end_turn(token=decision["token"])["decision"]
                trace.append(game.get_state())
            return trace
        with self.session() as (a, _), self.session() as (b, _):
            expected = play(a, 92)
            self.assertEqual(play(b, 92, render=True), expected)
            self.assertEqual(play(a, 92), expected)

    def test_seeded_new_map_repeat_difference_and_native_first_day(self):
        with self.session() as (game, _):
            game.reset(map_path=MAP, seed=73, player_id=1, difficulty=1)
            initial = game.get_state()
            self.assertEqual(initial["date"]["total_days"], 1)
            human = next(p for p in initial["players"] if p["is_human"])
            self.assertEqual(human["id"], 1)
            self.assertTrue(human["hero_ids"])
            self.assertTrue(human["castle_ids"])
            game.end_turn(token=game.get_decision()["token"])
            next_day = game.get_state()
            self.assertEqual(next_day["date"]["total_days"], 2)
            game.reset(seed=73)
            self.assertEqual(game.get_state(), initial)
            game.end_turn(token=game.get_decision()["token"])
            self.assertEqual(game.get_state(), next_day)
            game.reset(seed=74)
            self.assertNotEqual(game.get_state()["map"]["seed"], initial["map"]["seed"])
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_reset_from_pending_choice_and_battle(self):
        for profile, phase in (("choices-chest", "choice"), ("battles-melee", "battle")):
            with self.subTest(phase=phase), self.session() as (game, _):
                path = ROOT / f"build/python-env-baseline/fixtures/{profile}-day1.sav"
                episode = game.reset(save=path, seed=50)
                initial = game.get_state()
                decision = game.move_hero(52, 32, 25, token=episode["decision"]["token"])["decision"]
                if phase == "battle":
                    while decision["phase"] == "choice":
                        choice = decision["pending_choice"]
                        decision = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])["decision"]
                self.assertEqual(decision["phase"], phase)
                old_process = game._process
                game.reset(seed=50)
                self.assertIsNotNone(old_process.poll())
                self.assertEqual(game.get_state(), initial)
                self.assertEqual(game.get_decision()["phase"], "adventure")

    def test_reset_recovers_crash_timeout_close_and_failed_load(self):
        with self.session() as (game, _):
            game.reset(save=SAVE, seed=8)
            initial = game.get_state()
            game._process.kill()
            game._process.wait(timeout=5)
            game.reset(seed=8)
            self.assertEqual(game.get_state(), initial)
            old_process = game._process
            with mock.patch.object(game._incoming, "get", side_effect=queue.Empty):
                with self.assertRaises(EngineTimeoutError):
                    game.runtime_info()
            self.assertIsNotNone(old_process.poll())
            self.assertTrue(game.closed)
            game.reset(seed=8)
            self.assertEqual(game.get_state(), initial)
            game.close()
            game.reset(seed=8)
            self.assertEqual(game.get_state(), initial)
            with self.assertRaises(EngineError):
                game.reset(save=ROOT / "build/nonexistent-reset.sav", seed=8)
            self.assertTrue(game.closed)
            game.reset(seed=8)
            self.assertEqual(game.get_state(), initial)

    def test_terminal_battle_reset_and_seeded_battle_replay(self):
        with self.session() as (game, _):
            path = ROOT / "build/python-env-baseline/fixtures/battles-loss-day1.sav"
            expected = None
            for _ in range(2):
                episode = game.reset(save=path, seed=99)
                result = game.move_hero(52, 32, 25, token=episode["decision"]["token"])
                result = battle_support.BattleTests.finish(self, game, result, passive=True)
                for _ in range(80):
                    if result["decision"]["phase"] == "terminal":
                        break
                    result = game.end_turn(token=result["decision"]["token"])
                    result = battle_support.BattleTests.finish(self, game, result, passive=True)
                self.assertEqual(result["decision"]["phase"], "terminal")
                state = game.get_state()
                if expected is None:
                    expected = state
                else:
                    self.assertEqual(state, expected)

    def test_invalid_reset_arguments_preserve_current_process_and_decision(self):
        with self.session() as (game, _):
            with self.assertRaises(ValueError):
                game.reset(seed=1)
            game.reset(save=SAVE, seed=1)
            before, decision, pid = game.get_state(), game.get_decision(), game.pid
            for params in ({"seed": -1}, {"seed": True}, {"seed": 1 << 32}, {"seed": 1.5},
                           {"save": SAVE, "map_path": MAP}, {"player_id": 3}, {"difficulty": True}):
                with self.assertRaises(ValueError):
                    game.reset(**params)
                self.assertEqual(game.pid, pid)
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)

    def test_generated_seed_can_be_replayed_and_other_session_is_unchanged(self):
        with self.session() as (a, _), self.session() as (b, _):
            a.reset(save=SAVE, seed=1)
            before, decision, pid = a.get_state(), a.get_decision(), a.pid
            episode = b.reset(map_path=MAP)
            expected = b.get_state()
            self.assertIs(type(episode["seed"]), int)
            b.reset(seed=episode["seed"])
            self.assertEqual(b.get_state(), expected)
            self.assertEqual((a.pid, a.get_state(), a.get_decision()), (pid, before, decision))

    def test_raw_seed_and_map_validation_does_not_discard_live_world(self):
        with self.session() as (game, _):
            game.reset(save=SAVE, seed=1)
            before, decision = game.get_state(), game.get_decision()
            for method, params in (("load_save", {"path": str(SAVE), "seed": True}),
                                   ("load_save", {"path": str(SAVE), "seed": -1}),
                                   ("load_save", {"path": str(SAVE), "seed": 1 << 32}),
                                   ("new_game", {"path": str(MAP), "seed": 1, "player_id": 3, "difficulty": 1}),
                                   ("new_game", {"path": str(MAP), "seed": 1, "player_id": 1, "difficulty": 5})):
                with self.assertRaises(EngineError) as error:
                    game.request(method, params)
                self.assertEqual(error.exception.code, "invalid_request")
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)

    def test_resurrection_and_expansion_map_seeded_setup(self):
        for name in ("7_deserts.fh2m", "ARRAX.MX2"):
            with self.subTest(map=name), self.session() as (game, _):
                game.reset(map_path=ROOT / "maps" / name, seed=101)
                expected = game.get_state()
                game.render(width=64, height=64)
                game.reset(seed=101)
                self.assertEqual(game.get_state(), expected)

    def test_new_map_rendering_does_not_change_seeded_transition(self):
        with self.session() as (a, _), self.session() as (b, _):
            a.reset(map_path=MAP, seed=10)
            b.reset(map_path=MAP, seed=10)
            for _ in range(2):
                state = a.get_state()
                hero_id = next(p for p in state["players"] if p["is_human"])["hero_ids"][0]
                a.render(view="hero", hero_id=hero_id, width=64, height=64)
                a.end_turn(token=a.get_decision()["token"])
                b.end_turn(token=b.get_decision()["token"])
                self.assertEqual(a.get_state(), b.get_state())


if __name__ == "__main__":
    unittest.main()
