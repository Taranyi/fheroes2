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

"""Validate native castle economics and atomic rejection through the real engine."""

import unittest

from fheroes2_env import EngineError
import test_world_state as support

ROOT = support.ROOT


class CastleTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        cls.fixtures = support.WorldStateTests.fixtures

    def start(self, game, fixture=0):
        game.load_save(ROOT / self.fixtures[fixture]["path"])
        state = game.get_state(include_serialized=False)
        human = next(player for player in state["players"] if player["is_human"])
        return game.start_session(human["id"]), human, human["castle_ids"][0]

    def assert_rejected(self, game, call, code=None):
        before, decision = game.get_state(), game.get_decision()
        with self.assertRaises(EngineError) as failed:
            call()
        if code:
            self.assertEqual(failed.exception.code, code)
        self.assertEqual(game.get_state(), before)
        self.assertEqual(game.get_decision(), decision)

    def player(self, state, player_id):
        return next(player for player in state["players"] if player["id"] == player_id)

    def castle(self, state, castle_id):
        return next(castle for castle in state["castles"] if castle["id"] == castle_id)

    def assert_spent(self, before, after, player_id, cost):
        a, b = self.player(before, player_id)["funds"], self.player(after, player_id)["funds"]
        self.assertEqual({key: a[key] - b[key] for key in a}, cost)

    def test_options_are_omniscient_and_read_only_on_both_references(self):
        for fixture in range(2):
            with self.subTest(fixture=fixture), self.session() as (game, directory):
                with self.assertRaises(EngineError) as error:
                    game.get_castle_options(0)
                self.assertEqual(error.exception.code, "no_game_loaded")
                decision, _, _ = self.start(game, fixture)
                before = game.get_state()
                for castle in before["castles"]:
                    options = game.get_castle_options(castle["id"])
                    self.assertEqual(game.get_castle_options(castle["id"]), options)
                    self.assertEqual(options["owner"], castle["owner"])
                    self.assertEqual(options["perspective"], "omniscient")
                    self.assertEqual(len(options["dwellings"]), 6)
                    ids = [building["building_id"] for building in options["buildings"]]
                    self.assertEqual(ids, sorted(set(ids)))
                    self.assertNotIn(0x80000, ids)
                    for building in options["buildings"]:
                        self.assertEqual(building["built"], building["building_id"] in castle["buildings"])
                        self.assertEqual(building["can_build"], building["status"] == "allow_build")
                    for dwelling, stock in zip(options["dwellings"], castle["dwellings"]):
                        self.assertEqual(dwelling["available"], stock["count"])
                        self.assertLessEqual(dwelling["max_recruitable"], dwelling["available"])
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)
                for params in ({}, {"castle_id": -1}, {"castle_id": True}, {"castle_id": 1 << 40},
                               {"castle_id": 0xFFFFFFFF}, {"castle_id": options["castle_id"], "extra": 1}):
                    self.assert_rejected(game, lambda: game.request("get_castle_options", params), "invalid_request")
                self.assertEqual(list(directory.iterdir()), [])

    def test_build_uses_native_cost_and_daily_limit_and_stale_token(self):
        with self.session() as (game, _):
            decision, human, castle_id = self.start(game)
            option = next(b for b in game.get_castle_options(castle_id)["buildings"] if b["building_id"] == 1 << 22)
            self.assertTrue(option["can_build"])
            before = game.get_state()
            result = game.build_castle(castle_id, 1 << 22, token=decision["token"])
            after = game.get_state()
            self.assertIn(1 << 22, self.castle(after, castle_id)["buildings"])
            self.assert_spent(before, after, human["id"], option["cost"])
            self.assertEqual(after["date"], before["date"])
            self.assertEqual(after["state_version"], before["state_version"] + 1)
            self.assertEqual(result["events"][0]["type"], "castle_built")
            self.assert_rejected(game, lambda: game.build_castle(castle_id, 1 << 26, token=decision["token"]), "stale_decision")
            token = result["decision"]["token"]
            self.assert_rejected(game, lambda: game.build_castle(castle_id, 1 << 26, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.build_castle(castle_id, 1 << 22, token=token), "illegal_action")
            self.assertTrue(all(not b["can_build"] for b in game.get_castle_options(castle_id)["buildings"]))
            result = game.end_turn(token=token)
            self.assertTrue(any(b["can_build"] for b in game.get_castle_options(castle_id)["buildings"]))
            game.build_castle(castle_id, 1 << 26, token=result["decision"]["token"])
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_recruit_exact_count_stock_payment_and_army(self):
        for fixture in range(2):
            with self.subTest(fixture=fixture), self.session() as (game, _):
                decision, human, castle_id = self.start(game, fixture)
                if fixture == 1:
                    # This save has already recruited its stocks. A native well enables the next dwelling;
                    # constructing that dwelling on the next day creates its initial native stock.
                    decision = game.build_castle(castle_id, 8, token=decision["token"])["decision"]
                    decision = game.end_turn(token=decision["token"])["decision"]
                    decision = game.build_castle(castle_id, 1 << 22, token=decision["token"])["decision"]
                option = next(d for d in game.get_castle_options(castle_id)["dwellings"] if d["max_recruitable"] >= 3)
                before = game.get_state()
                result = game.recruit_castle(castle_id, option["dwelling_id"], 3, token=decision["token"])
                after = game.get_state()
                event = result["events"][0]
                self.assertEqual((event["type"], event["count"], event["monster_id"]), ("castle_recruited", 3, option["monster_id"]))
                self.assert_spent(before, after, human["id"], {key: value * 3 for key, value in option["unit_cost"].items()})
                old_castle, new_castle = self.castle(before, castle_id), self.castle(after, castle_id)
                old_stock = next(d for d in old_castle["dwellings"] if d["building_id"] == option["dwelling_id"])["count"]
                new_stock = next(d for d in new_castle["dwellings"] if d["building_id"] == option["dwelling_id"])["count"]
                self.assertEqual(old_stock - new_stock, 3)
                def total(castle):
                    return sum(t["count"] for t in castle["garrison"] if t and t["monster_id"] == option["monster_id"])
                self.assertEqual(total(new_castle) - total(old_castle), 3)
                self.assertEqual(after["date"], before["date"])
                self.assertEqual(event["destination"]["type"], "garrison")

    def test_bad_ids_counts_ownership_and_excess_stock_are_atomic(self):
        with self.session() as (game, _):
            decision, human, castle_id = self.start(game)
            token = decision["token"]
            enemy = next(c["id"] for c in game.get_state()["castles"] if c["owner"] != human["id"])
            for target in (enemy, 0xFFFFFFFF):
                self.assert_rejected(game, lambda: game.build_castle(target, 8, token=token))
                self.assert_rejected(game, lambda: game.recruit_castle(target, 1 << 20, 1, token=token))
            for building in (0, 3, 0x80000, 0x80000000, -1, 1 << 40, True, "well"):
                self.assert_rejected(game, lambda: game.build_castle(castle_id, building, token=token), "invalid_request")
            dwelling = game.get_castle_options(castle_id)["dwellings"][0]
            for count in (0, -1, True, 1.5, "3", 1 << 40, dwelling["available"] + 1, 0xFFFFFFFF):
                self.assert_rejected(game, lambda: game.recruit_castle(castle_id, dwelling["dwelling_id"], count, token=token))
            for dwelling_id in (0, 3, 1 << 26, -1, True, 1 << 40):
                self.assert_rejected(game, lambda: game.recruit_castle(castle_id, dwelling_id, 1, token=token), "invalid_request")
            missing = next(d for d in game.get_castle_options(castle_id)["dwellings"] if not d["built"])
            self.assert_rejected(game, lambda: game.recruit_castle(castle_id, missing["dwelling_id"], 1, token=token), "illegal_action")
            # Existing native prerequisites and insufficient resources are enforced too.
            self.assert_rejected(game, lambda: game.build_castle(castle_id, 1 << 23, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.build_castle(castle_id, 1024, token=token), "illegal_action")

    def test_full_garrison_falls_back_to_visitor_then_rejects_without_room(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            def recruit(dwelling):
                nonlocal decision
                result = game.recruit_castle(castle_id, dwelling, 1, token=decision["token"])
                decision = result["decision"]
                return result
            def build(building):
                nonlocal decision
                decision = game.build_castle(castle_id, building, token=decision["token"])["decision"]
            def tomorrow():
                nonlocal decision
                decision = game.end_turn(token=decision["token"])["decision"]
            recruit(1 << 20)  # Skeleton
            recruit(1 << 21)  # Zombie
            build(1 << 26)
            recruit(1 << 21)  # Mutant Zombie: a separate stack, no automatic army upgrade.
            tomorrow()
            build(1 << 22)
            recruit(1 << 22)  # Mummy
            tomorrow()
            build(1 << 27)
            recruit(1 << 22)  # Royal Mummy: garrison now has five distinct stacks.
            tomorrow()
            build(1 << 23)
            options = game.get_castle_options(castle_id)["dwellings"][3]
            self.assertEqual(options["destination"], {"type": "hero", "hero_id": 52})
            before = game.get_state()
            result = recruit(1 << 23)
            after = game.get_state()
            self.assertEqual(self.castle(after, castle_id)["garrison"], self.castle(before, castle_id)["garrison"])
            hero = next(h for h in after["heroes"] if h["id"] == 52)
            self.assertTrue(any(t and t["monster_id"] == options["monster_id"] and t["count"] == 1 for t in hero["army"]))
            self.assertEqual(result["events"][0]["destination"], options["destination"])
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            options = game.get_castle_options(castle_id)["dwellings"][3]
            self.assertEqual((options["max_recruitable"], options["status"]), (0, "no_army_room"))
            self.assert_rejected(game, lambda: game.recruit_castle(castle_id, 1 << 23, 1, token=decision["token"]), "illegal_action")
            # A matching stack can still grow in the full garrison.
            self.assertEqual(recruit(1 << 20)["events"][0]["destination"]["type"], "garrison")

    def test_dwelling_upgrade_selects_the_native_creature_and_preserves_stock(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            before = game.get_castle_options(castle_id)["dwellings"][1]
            result = game.build_castle(castle_id, 1 << 26, token=decision["token"])
            after = game.get_castle_options(castle_id)["dwellings"][1]
            self.assertEqual(after["available"], before["available"])
            self.assertNotEqual(after["monster_id"], before["monster_id"])
            self.assertEqual(after["actual_building_id"], 1 << 26)
            result = game.recruit_castle(castle_id, 1 << 21, 1, token=result["decision"]["token"])
            self.assertEqual(result["events"][0]["monster_id"], after["monster_id"])


if __name__ == "__main__":
    unittest.main()
