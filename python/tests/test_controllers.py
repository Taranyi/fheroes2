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

"""Exercise per-side control routing without changing native rule-profile flags."""

from copy import deepcopy
import unittest

from fheroes2_env import EngineError
import test_world_state as support
import test_battle as battle_support

ROOT = support.ROOT
SAVE = ROOT / "build/python-env-baseline/fixtures/other-side-day1.sav"
MAP = ROOT / "maps/THEOTHER.MP2"
PYTHON = {1: "python", 2: "python"}
NATIVE = {1: "builtin_ai", 2: "builtin_ai"}


class ControllerTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        for name in ("battles-heroes-day1.sav", "battles-siege-day1.sav", "controllers-ai-boss-day1.sav"):
            if not (ROOT / "build/python-env-baseline/fixtures" / name).is_file():
                raise unittest.SkipTest("Prepare native controller fixtures; see docs/PYTHON_ENV_CONTROLLERS.md")

    def reject(self, game, call, code):
        state, decision = game.get_state(), game.get_decision()
        with self.assertRaises(EngineError) as error:
            call()
        self.assertEqual(error.exception.code, code)
        self.assertEqual(game.get_state(), state)
        self.assertEqual(game.get_decision(), decision)

    def finish(self, game, decision, seen=None):
        for _ in range(600):
            if decision["phase"] == "battle":
                if seen is not None:
                    seen.add(decision["player_id"])
                selected = battle_support._example.select_action(decision["battle"], use_spells=True)
                decision = game.battle_action(selected["action_id"], token=decision["token"])["decision"]
            elif decision["phase"] == "choice":
                if seen is not None:
                    seen.add(decision["player_id"])
                choice = decision["pending_choice"]
                value = choice["options"][0] if choice["options"] else choice["minimum"]
                decision = game.answer_choice(choice["choice_id"], value, token=decision["token"])["decision"]
            else:
                return decision
        self.fail("Native interaction policy exceeded its decision budget")

    def test_assignment_preserves_saved_flags_world_and_rejects_unknown_participants(self):
        with self.session() as (game, _):
            game.load_save(SAVE, seed=3)
            before = game.get_state()
            for assignment in ({1: "python"}, {1: "python", 2: "python", 4: "python"}):
                with self.assertRaises(EngineError) as error:
                    game.start_session(controllers=assignment)
                self.assertEqual(error.exception.code, "invalid_request")
                self.assertEqual(game.get_state(), before)
            decision = game.start_session(controllers=PYTHON)
            after = game.get_state()
            self.assertEqual(after["serialized_state"], before["serialized_state"])
            self.assertEqual([(p["id"], p["control"]) for p in after["players"]], [(1, 1), (2, 4)])
            self.assertEqual(decision["player_id"], 1)
            self.assertEqual(after["simulation"]["controllers"], {"1": "python", "2": "python"})

    def test_two_external_sides_turn_order_income_and_permissions(self):
        with self.session() as (game, _):
            decision = game.reset(save=SAVE, seed=1, controllers=PYTHON)["decision"]
            original = game.get_state(include_serialized=False)
            wrong = deepcopy(decision["token"])
            wrong["player_id"] = 2
            self.reject(game, lambda: game.end_turn(token=wrong), "wrong_player")
            self.reject(game, lambda: game.move_hero(42, 4, 24, token=decision["token"]), "illegal_action")
            first = game.end_turn(token=decision["token"])
            decision = first["decision"]
            self.assertEqual((decision["player_id"], game.get_state()["date"]["total_days"]), (2, 1))
            self.assertFalse(any(e["type"] == "ai_turn_completed" for e in first["events"]))
            state = game.get_state(include_serialized=False)
            hero = next(h for h in state["heroes"] if h["active"] and h["owner"] == 2)
            self.assertTrue(next(p for p in state["players"] if p["id"] == 2)["is_ai"])
            # AI-rule side gets Python actions, not the AI adventure action handler.
            x, y = hero["position"]["x"], hero["position"]["y"]
            commands = [{"action": "hero.move", "params": {"hero_id": hero["id"], "x": x+dx, "y": y+dy}}
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if x+dx >= 0 and y+dy >= 0]
            valid = game.check_actions(commands, token=decision["token"])
            cmd = next(c for c, allowed in zip(commands, valid) if allowed)
            decision = game.step(cmd["action"], params=cmd["params"], token=decision["token"])["decision"]
            self.assertEqual(decision["player_id"], 2)
            decision = game.end_turn(token=decision["token"])["decision"]
            self.assertEqual((decision["player_id"], game.get_state()["date"]["total_days"]), (1, 2))
            after = game.get_state(include_serialized=False)
            blue_before = next(p for p in original["players"] if p["id"] == 1)
            blue_after = next(p for p in after["players"] if p["id"] == 1)
            self.assertEqual(blue_after["funds"]["gold"], blue_before["funds"]["gold"] + blue_before["daily_income"]["gold"])
            self.assertEqual(blue_after["control"], blue_before["control"])

    def test_ai_only_no_human_rule_flags_bounded_queries_and_native_terminal(self):
        with self.session() as (game, directory):
            decision = game.reset(map_path=MAP, seed=123, controllers=NATIVE, rule_profiles={1: "ai", 2: "ai"})["decision"]
            self.assertEqual(decision["phase"], "simulation")
            self.assertEqual(decision["player_id"], 0)
            state = game.get_state()
            self.assertTrue(all(p["is_ai"] and not p["is_human"] for p in state["players"]))
            self.reject(game, lambda: game.end_turn(token=decision["token"]), "simulation_advance_required")
            for count in (0, 65, -1, True):
                with self.assertRaises(ValueError):
                    game.advance_simulation(count, token=decision["token"])
                self.assertEqual(game.get_state(), state)
            turns = []
            for _ in range(160):
                previous_day = game.get_state(include_serialized=False)["date"]["total_days"]
                result = game.advance_simulation(1, token=decision["token"])
                decision = result["decision"]
                events = [e for e in result["events"] if e["type"] == "ai_turn_completed"]
                self.assertLessEqual(len(events), 1)
                turns += [e["player_id"] for e in events]
                before, pending = game.get_state(), game.get_decision()
                if decision["phase"] == "terminal":
                    break
                self.assertLessEqual(before["date"]["total_days"] - previous_day, 1)
                if len(turns) == 2:
                    for view, ids in (("adventure", {}), ("hero", {"hero_id": next(h["id"] for h in before["heroes"] if h["active"])}),
                                      ("castle", {"castle_id": before["castles"][0]["id"]})):
                        game.render(view=view, width=64, height=64, **ids)
                    self.assertEqual(game.get_state(), before)
                    self.assertEqual(game.get_decision(), pending)
            self.assertEqual(decision["phase"], "terminal")
            outcomes = list(decision["simulation"]["outcomes"].values())
            self.assertTrue(any(value & 0x3F for value in outcomes))
            self.assertTrue(any(value & 0x70F00 for value in outcomes))
            self.assertEqual(turns[:4], [1, 2, 1, 2])
            self.reject(game, lambda: game.advance_simulation(1, token=decision["token"]), "episode_finished")
            self.assertFalse(game.runtime_info()["video_initialized"])
            self.assertEqual(list(directory.iterdir()), [])

    def test_ai_only_preserves_saved_human_rule_profile_and_seeded_replay(self):
        with self.session() as (a, _), self.session() as (b, _):
            for game in (a, b):
                game.reset(save=SAVE, seed=72, controllers=NATIVE)
            expected = []
            for _ in range(8):
                a.advance_simulation(1, token=a.get_decision()["token"])
                expected.append(a.get_state())
            for state in expected:
                b.advance_simulation(1, token=b.get_decision()["token"])
                self.assertEqual(b.get_state(), state)
            self.assertTrue(next(p for p in b.get_state()["players"] if p["id"] == 1)["is_human"])
            b.reset(seed=72)
            for state in expected:
                b.advance_simulation(1, token=b.get_decision()["token"])
                self.assertEqual(b.get_state(), state)

    def test_all_native_batch_matches_single_turn_steps_and_stops_at_python(self):
        with self.session() as (a, _), self.session() as (b, _):
            for game in (a, b):
                game.reset(map_path=MAP, seed=10, controllers=NATIVE, rule_profiles={1: "ai", 2: "ai"})
            result = a.advance_simulation(8, token=a.get_decision()["token"])
            for _ in range(8):
                b.advance_simulation(1, token=b.get_decision()["token"])
            before, after = a.get_state(), b.get_state()
            before.pop("state_version"); after.pop("state_version")
            self.assertEqual(before, after)
            self.assertEqual(len([e for e in result["events"] if e["type"] == "ai_turn_completed"]), 8)
            decision = a.reset(save=SAVE, seed=5, controllers={1: "builtin_ai", 2: "python"})["decision"]
            decision = a.advance_simulation(64, token=decision["token"])["decision"]
            self.assertEqual((decision["phase"], decision["player_id"]), ("adventure", 2))
            self.reject(a, lambda: a.advance_simulation(1, token=decision["token"]), "external_decision_required")

    def test_battle_routes_both_external_sides_and_wrong_owner_is_atomic(self):
        with self.session() as (game, _):
            decision = game.reset(save=ROOT / "build/python-env-baseline/fixtures/battles-heroes-day1.sav", seed=1, controllers=PYTHON)["decision"]
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            seen = set()
            for _ in range(4):
                self.assertEqual(decision["phase"], "battle")
                seen.add(decision["player_id"])
                wrong = deepcopy(decision["token"]); wrong["player_id"] = 2 if decision["player_id"] == 1 else 1
                action = next(a for a in decision["battle"]["actions"] if a["kind"] == "skip")
                self.reject(game, lambda: game.battle_action(action["action_id"], token=wrong), "wrong_player")
                before = game.get_state()
                game.render(view="battle", width=64, height=64)
                self.assertEqual(game.get_state(), before)
                decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
            self.assertEqual(seen, {1, 2})
            decision = self.finish(game, decision, seen)
            self.assertIn(decision["phase"], ("adventure", "terminal"))

    def test_defender_external_suspends_inside_native_ai_turn_and_stop_rolls_back(self):
        with self.session() as (game, _):
            path = ROOT / "build/python-env-baseline/fixtures/battles-heroes-day1.sav"
            decision = game.reset(save=path, seed=2, controllers={1: "builtin_ai", 2: "python"})["decision"]
            for _ in range(60):
                before = game.get_state()
                if decision["phase"] == "simulation":
                    result = game.advance_simulation(1, token=decision["token"])
                else:
                    result = game.end_turn(token=decision["token"])
                decision = result["decision"]
                if decision["phase"] in ("battle", "choice"):
                    self.assertEqual(decision["player_id"], 2)
                    game.step("session.stop", token=decision["token"])
                    self.assertEqual(game.get_state(), before)
                    return
            self.fail("Expected native attacker to reach the Python defender")

    def test_siege_routes_ai_rule_castle_defender_to_python(self):
        with self.session() as (game, _):
            decision = game.reset(save=ROOT / "build/python-env-baseline/fixtures/battles-siege-day1.sav", seed=2, controllers=PYTHON)["decision"]
            decision = game.move_hero(52, 3, 24, token=decision["token"])["decision"]
            self.assertEqual(decision["phase"], "battle")
            self.assertTrue(decision["battle"]["siege"])
            seen = set()
            self.finish(game, decision, seen)
            self.assertEqual(seen, {1, 2})
            castle = next(c for c in game.get_state()["castles"] if c["id"] == 867)
            self.assertEqual(castle["owner"], 1)

    def test_choice_uses_owner_of_ai_rule_external_hero(self):
        with self.session() as (game, _):
            # New-map explicit AI profiles do not cause Python's hero choices to be auto-selected.
            decision = game.reset(map_path=MAP, seed=123, controllers=PYTHON, rule_profiles={1: "ai", 2: "ai"})["decision"]
            self.assertEqual(decision["player_id"], 1)
            self.assertTrue(all(p["control"] == 4 for p in game.get_state()["players"]))
            # Existing boss fixture supplies a reproducible multi-level-up sequence for the assigned side.
            decision = game.reset(save=ROOT / "build/python-env-baseline/fixtures/controllers-ai-boss-day1.sav", seed=2, controllers=PYTHON)["decision"]
            self.assertTrue(all(p["is_ai"] for p in game.get_state()["players"]))
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            seen_choice = False
            for _ in range(100):
                if decision["phase"] == "battle":
                    action = battle_support._example.select_action(decision["battle"], use_spells=True)
                    decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
                elif decision["phase"] == "choice":
                    seen_choice = True
                    self.assertEqual(decision["player_id"], 1)
                    choice = decision["pending_choice"]
                    decision = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])["decision"]
                else: break
            self.assertTrue(seen_choice)

    def test_rule_profiles_affect_native_difficulty_not_controller_assignment(self):
        with self.session() as (game, _):
            game.reset(map_path=MAP, seed=3, difficulty=3, rule_profiles={1: "human", 2: "ai"}, controllers=PYTHON)
            players = {p["id"]: p for p in game.get_state()["players"]}
            self.assertGreater(players[2]["funds"]["gold"], players[1]["funds"]["gold"])
            initial = [(p["id"],p["control"],p["funds"]) for p in game.get_state()["players"]]
            game.reset(seed=3, controllers=NATIVE)
            self.assertEqual([(p["id"],p["control"],p["funds"]) for p in game.get_state()["players"]], initial)
            with self.assertRaises(ValueError):
                game.reset(save=SAVE, rule_profiles={1:"ai",2:"ai"})

    def test_invalid_configurations_and_advance_keep_existing_world(self):
        with self.session() as (game, _):
            decision = game.reset(save=SAVE, seed=3, controllers=NATIVE)["decision"]
            state, pid = game.get_state(), game.pid
            for assignment in ({}, {True:"python"}, {3:"python"}, {1:"human"}, {1:"python","blue":"builtin_ai"}):
                with self.assertRaises(ValueError):
                    game.reset(controllers=assignment)
                self.assertEqual(game.pid,pid)
                self.assertEqual(game.get_state(),state)
            for params in ({"max_turns":0},{"max_turns":65},{"max_turns":True},{"max_turns":-1},{"max_turns":1,"x":1}):
                self.reject(game, lambda:game.step("simulation.advance",params=params,token=decision["token"]),"invalid_request")
            first = game.advance_simulation(1,token=decision["token"])["decision"]
            self.reject(game,lambda:game.advance_simulation(1,token=decision["token"]),"stale_decision")
            self.assertEqual(first["player_id"],0)


if __name__ == "__main__":
    unittest.main()
