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

"""Exercise native adventure rules through the actual isolated engine process."""

import unittest

from fheroes2_env import EngineError
import test_world_state as support

ROOT = support.ROOT


class AdventureTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        cls.fixtures = support.WorldStateTests.fixtures

    def start(self, game, fixture=0):
        game.load_save(ROOT / self.fixtures[fixture]["path"])
        state = game.get_state(include_serialized=False)
        human = next(player for player in state["players"] if player["is_human"])
        return game.start_session(human["id"]), human

    def test_native_land_steps_spend_movement_and_invalidate_old_tokens(self):
        with self.session() as (game, directory):
            decision, _ = self.start(game)
            before = game.get_state()
            frame = game.render(width=192, height=160, center=(32, 25))
            result = game.move_hero(52, 32, 25, token=decision["token"])
            after = game.get_state()
            hero = next(hero for hero in after["heroes"] if hero["id"] == 52)
            self.assertEqual(hero["position"], {"index": 932, "x": 32, "y": 25})
            self.assertEqual(hero["move_points"], 900)
            self.assertEqual(result["events"][0]["movement_spent"], 100)
            self.assertEqual(after["date"], before["date"])
            self.assertEqual(after["players"][0]["funds"], before["players"][0]["funds"])
            self.assertEqual(after["state_version"], before["state_version"] + 1)
            self.assertEqual(result["decision"]["token"]["episode_id"], decision["token"]["episode_id"])
            self.assertEqual(game.get_decision(), result["decision"])
            self.assertNotEqual(game.render(width=192, height=160, center=(32, 25)).pixels, frame.pixels)
            self.assertEqual(game.get_state(), after)
            with self.assertRaises(EngineError) as failed:
                game.move_hero(52, 32, 26, token=decision["token"])
            self.assertEqual(failed.exception.code, "stale_decision")
            self.assertEqual(game.get_state(), after)
            self.assertFalse(game.runtime_info()["video_initialized"])
            self.assertFalse(game.runtime_info()["audio_initialized"])
            self.assertEqual(list(directory.iterdir()), [])

    def test_multi_tile_route_uses_native_path_and_stops_on_destination(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            result = game.move_hero(52, 32, 26, token=decision["token"])
            hero = next(hero for hero in game.get_state()["heroes"] if hero["id"] == 52)
            self.assertEqual(hero["position"]["index"], 968)
            self.assertEqual(result["events"][0]["movement_spent"], 200)
            self.assertEqual(hero["move_points"], 800)

    def test_resource_pickup_uses_engine_funds_and_removes_object_exactly_once(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            for x, y in ((32, 25), (32, 26), (31, 27), (30, 28), (29, 29)):
                decision = game.move_hero(52, x, y, token=decision["token"])["decision"]
            decision = game.end_turn(token=decision["token"])["decision"]
            before = game.get_state(include_serialized=False)
            self.assertEqual(before["map"]["tiles"][1179]["metadata"], [1, 7, 0])
            result = game.move_hero(52, 27, 32, token=decision["token"])
            pickup = next(event for event in result["events"] if event["type"] == "resource_collected")
            self.assertEqual(pickup["funds"]["wood"], 7)
            after = game.get_state(include_serialized=False)
            own_before = next(player for player in before["players"] if player["id"] == 1)
            own_after = next(player for player in after["players"] if player["id"] == 1)
            self.assertEqual(own_after["funds"]["wood"], own_before["funds"]["wood"] + 7)
            self.assertEqual(after["map"]["tiles"][1179]["metadata"], [0, 0, 0])
            self.assertEqual(after["map"]["tiles"][1179]["object_type"], 0)
            hero = next(hero for hero in after["heroes"] if hero["id"] == 52)
            self.assertEqual(hero["position"]["index"], 1180)  # Native pickup stands in front of the pile.
            again = game.move_hero(52, 27, 32, token=result["decision"]["token"])
            self.assertFalse(any(event["type"] == "resource_collected" for event in again["events"]))
            self.assertEqual(next(p for p in game.get_state()["players"] if p["id"] == 1)["funds"], own_after["funds"])

    def test_illegal_routes_and_ownership_never_change_world_or_decision(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            before = game.get_state()
            for params, codes in (
                ({"hero_id": 42, "x": 32, "y": 25}, {"illegal_action"}),
                ({"hero_id": 0, "x": 32, "y": 25}, {"illegal_action"}),
                ({"hero_id": True, "x": 32, "y": 25}, {"invalid_request"}),
                ({"hero_id": 52, "x": -1, "y": 25}, {"invalid_request"}),
                ({"hero_id": 52, "x": 36, "y": 25}, {"invalid_request"}),
                ({"hero_id": 52, "x": 32, "y": 24}, {"illegal_action"}),
                ({"hero_id": 52, "x": 3, "y": 24}, {"illegal_action", "unsupported_action"}),
                ({"hero_id": 52, "x": 10, "y": 10}, {"illegal_action", "unsupported_action"}),
            ):
                with self.subTest(params=params):
                    with self.assertRaises(EngineError) as failed:
                        game.step("hero.move", token=decision["token"], params=params)
                    self.assertIn(failed.exception.code, codes)
                    self.assertEqual(game.get_state(), before)
                    self.assertEqual(game.get_decision(), decision)
            # Rejected initial preparations must not prevent the next valid native move.
            self.assertEqual(game.move_hero(52, 32, 25, token=decision["token"])["events"][0]["to"], 932)

    def test_end_turn_runs_all_native_ai_players_and_applies_human_income_once(self):
        for fixture in (0, 1):
            with self.subTest(fixture=fixture), self.session() as (game, _):
                decision, human = self.start(game, fixture)
                before = game.get_state(include_serialized=False)
                before_ai = {h["id"]: h["position"] for h in before["heroes"] if h["active"] and h["owner"] != human["id"]}
                result = game.end_turn(token=decision["token"])
                after = game.get_state()
                own = next(p for p in after["players"] if p["id"] == human["id"])
                own_before = next(p for p in before["players"] if p["id"] == human["id"])
                for resource, value in own_before["funds"].items():
                    event_delta = sum(e["funds"][resource] for e in result["events"] if e["type"] == "daily_event")
                    self.assertEqual(own["funds"][resource], value + own_before["daily_income"][resource] + event_delta, resource)
                self.assertEqual(after["date"]["total_days"], before["date"]["total_days"] + 1)
                self.assertEqual(after["current_player"], human["id"])
                expected_ai = [p["id"] for p in sorted(before["players"], key=lambda p: p["id"]) if p["is_ai"] and p["in_play"]]
                self.assertEqual([e["player_id"] for e in result["events"] if e["type"] == "ai_turn_completed"], expected_ai)
                after_ai = {h["id"]: h["position"] for h in after["heroes"] if h["active"] and h["owner"] != human["id"]}
                self.assertNotEqual(before_ai, after_ai)
                self.assertEqual([(p["id"], p["control"]) for p in after["players"]], [(p["id"], p["control"]) for p in before["players"]])
                self.assertEqual(game.get_state(), after)
                self.assertEqual(game.get_decision(), result["decision"])

    def test_week_boundary_uses_native_dwelling_growth(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            before = next(c for c in game.get_state()["castles"] if c["name"] == "Timberhill")
            for _ in range(7):
                result = game.end_turn(token=decision["token"])
                decision = result["decision"]
            state = game.get_state()
            self.assertEqual(state["date"]["total_days"], 8)
            self.assertEqual(state["date"]["week"], 2)
            self.assertTrue(any(e["type"] == "new_week" for e in result["events"]))
            after = next(c for c in state["castles"] if c["name"] == "Timberhill")
            self.assertGreater(sum(d["count"] for d in after["dwellings"]), sum(d["count"] for d in before["dwellings"]))

    def test_stop_and_reattach_do_not_repeat_daily_updates(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            before = game.get_state()
            game.step("session.stop", token=decision["token"])
            attached = game.start_session(1)
            self.assertEqual(game.get_state(), before)
            self.assertGreater(attached["token"]["decision_id"], decision["token"]["decision_id"])
            self.assertEqual(attached["token"]["episode_id"], decision["token"]["episode_id"])
            after_turn = game.end_turn(token=attached["token"])["decision"]
            self.assertEqual(game.get_state()["date"]["total_days"], 2)
            self.assertEqual(after_turn["token"]["episode_id"], attached["token"]["episode_id"])
            self.assertEqual(after_turn["token"]["state_version"], before["state_version"] + 1)

    def test_native_ai_attack_suspends_for_external_defense_and_can_roll_back(self):
        with self.session() as (game, _):
            decision, _ = self.start(game)
            for _ in range(60):
                before = game.get_state()
                result = game.end_turn(token=decision["token"])
                decision = result["decision"]
                if decision["phase"] == "terminal":
                    self.assertTrue(any(e["type"] == "battle_completed" for e in result["events"]))
                    self.assertNotEqual(game.get_state()["game_result"], 0)
                    game.step("session.stop", token=decision["token"])
                    self.start(game)
                    break
                if decision["phase"] == "battle":
                    battle = decision["battle"]
                    self.assertEqual(battle["defender_color"], 1)
                    game.step("session.stop", token=decision["token"])
                    self.assertEqual(game.get_state(), before)
                    decision = game.start_session(1)
                    result = game.end_turn(token=decision["token"])
                    self.assertEqual(result["decision"]["battle"], battle)
                    for _ in range(500):
                        decision = result["decision"]
                        if decision["phase"] == "battle":
                            action = next(a for a in decision["battle"]["actions"] if a["kind"] == "skip")
                            result = game.battle_action(action["action_id"], token=decision["token"])
                        elif decision["phase"] == "choice":
                            choice = decision["pending_choice"]
                            result = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])
                        else:
                            break
                    else:
                        self.fail("Native AI defense battle did not complete")
                    self.assertTrue(any(e["type"] == "battle_completed" for e in result["events"]))
                    self.assertIn(result["decision"]["phase"], ("adventure", "terminal"))
                    game.step("session.stop", token=result["decision"]["token"])
                    self.start(game)
                    self.assertEqual(game.get_state()["date"]["total_days"], 1)
                    break
            else:
                self.fail("Reference scenario did not exercise external battle defense within 60 turns")


if __name__ == "__main__":
    unittest.main()
