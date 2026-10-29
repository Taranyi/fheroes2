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

"""Validate conservation, exact transfers, access and native meeting costs on actual saves."""

from collections import Counter
import unittest

import test_castle as support


def endpoint(kind, entity_id, slot):
    return {"kind": kind, "id": entity_id, "slot": slot}


class ArmyTests(unittest.TestCase):
    session = support.CastleTests.session
    start = support.CastleTests.start
    assert_rejected = support.CastleTests.assert_rejected
    castle = support.CastleTests.castle

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        cls.fixtures = support.CastleTests.fixtures

    def hero(self, state, hero_id=52):
        return next(h for h in state["heroes"] if h["id"] == hero_id)

    def totals(self, state):
        result = Counter()
        for army in [h["army"] for h in state["heroes"]] + [c["garrison"] for c in state["castles"]]:
            for troop in army:
                if troop:
                    result[troop["monster_id"]] += troop["count"]
        return result

    def two_heroes(self, game, *, far=False):
        decision, _, castle_id = self.start(game)
        decision = game.refresh_hero_offers(castle_id, token=decision["token"])["decision"]
        decision = game.move_hero(52, 32, 26 if far else 25, token=decision["token"])["decision"]
        offer = next(h for h in game.get_castle_options(castle_id)["hero_hiring"]["offers"] if h["available"])
        decision = game.hire_hero(castle_id, offer["hero_id"], token=decision["token"])["decision"]
        return decision, castle_id, offer["hero_id"]

    def test_same_army_split_merge_reorder_preserve_units_money_date_and_movement(self):
        with self.session() as (game, _):
            decision, _, _ = self.start(game)
            before = game.get_state()
            a, b = endpoint("hero", 52, 0), endpoint("hero", 52, 2)
            result = game.transfer_troops(a, b, 4, token=decision["token"])
            state = game.get_state()
            self.assertEqual([self.hero(state)["army"][i]["count"] for i in (0, 2)], [5, 4])
            self.assert_rejected(game, lambda: game.transfer_troops(b, a, 4, token=decision["token"]), "stale_decision")
            decision = game.transfer_troops(b, a, 4, token=result["decision"]["token"])["decision"]
            self.assertIsNone(self.hero(game.get_state())["army"][2])
            decision = game.swap_troops(a, endpoint("hero", 52, 1), token=decision["token"])["decision"]
            state = game.get_state()
            self.assertEqual(self.hero(state)["army"][0]["monster_id"], self.hero(before)["army"][1]["monster_id"])
            self.assertEqual(self.totals(state), self.totals(before))
            self.assertEqual(state["players"], before["players"])
            self.assertEqual(state["date"], before["date"])
            self.assertEqual(self.hero(state)["move_points"], self.hero(before)["move_points"])
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_castle_transfer_preserves_last_hero_unit_but_allows_empty_garrison(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            before = game.get_state()
            hero0, hero1 = endpoint("hero", 52, 0), endpoint("hero", 52, 1)
            guard0, guard1 = endpoint("castle", castle_id, 0), endpoint("castle", castle_id, 1)
            decision = game.transfer_troops(hero1, guard0, 4, token=decision["token"])["decision"]
            self.assert_rejected(game, lambda: game.transfer_troops(hero0, guard1, 9, token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.swap_troops(hero0, guard1, token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.swap_troops(guard1, hero0, token=decision["token"]), "illegal_action")
            decision = game.transfer_troops(hero0, guard1, 8, token=decision["token"])["decision"]
            self.assertEqual(self.hero(game.get_state())["army"][0]["count"], 1)
            # Moving the sole stack inside its own army is legal.
            decision = game.transfer_troops(hero0, hero1, 1, token=decision["token"])["decision"]
            decision = game.transfer_troops(guard1, hero1, 8, token=decision["token"])["decision"]
            decision = game.transfer_troops(guard0, hero0, 4, token=decision["token"])["decision"]
            state = game.get_state()
            self.assertTrue(all(t is None for t in self.castle(state, castle_id)["garrison"]))
            self.assertEqual(self.totals(state), self.totals(before))

    def test_native_meeting_pays_once_and_allows_bidirectional_transfers(self):
        with self.session() as (game, _):
            decision, _, other = self.two_heroes(game)
            source, target = endpoint("hero", 52, 0), endpoint("hero", other, 4)
            self.assert_rejected(game, lambda: game.transfer_troops(source, target, 2, token=decision["token"]), "illegal_action")
            before = game.get_state()
            result = game.meet_heroes(52, other, token=decision["token"])
            decision = result["decision"]
            spent = result["events"][0]["movement_spent"]
            self.assertGreater(spent, 0)
            state = game.get_state()
            self.assertEqual(self.hero(before)["position"], self.hero(state)["position"])
            self.assertEqual(self.hero(before)["move_points"] - self.hero(state)["move_points"], spent)
            meeting = state["army_meeting"]
            self.assertIsNotNone(meeting)
            self.assertEqual(decision["army_meeting"], meeting)
            self.assert_rejected(game, lambda: game.meet_heroes(52, other, token=decision["token"]), "illegal_action")
            decision = game.transfer_troops(source, target, 2, token=decision["token"])["decision"]
            decision = game.transfer_troops(target, source, 1, token=decision["token"])["decision"]
            after = game.get_state()
            self.assertEqual(self.hero(after)["move_points"], self.hero(state)["move_points"])
            self.assertEqual(self.totals(after), self.totals(before))
            self.assertEqual(after["army_meeting"], meeting)
            game.render(width=64, height=64)
            self.assertEqual(game.get_state(), after)
            self.assert_rejected(game, lambda: game.transfer_troops(source, target, 999, token=decision["token"]), "illegal_action")
            decision = game.end_turn(token=decision["token"])["decision"]
            self.assertIsNone(decision["army_meeting"])
            self.assert_rejected(game, lambda: game.transfer_troops(source, target, 1, token=decision["token"]), "illegal_action")

    def test_swapping_occupied_stacks_across_armies_keeps_the_hero_alive(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            decision = game.transfer_troops(endpoint("hero", 52, 1), endpoint("castle", castle_id, 0), 4, token=decision["token"])["decision"]
            before = game.get_state()
            game.swap_troops(endpoint("hero", 52, 0), endpoint("castle", castle_id, 0), token=decision["token"])
            after = game.get_state()
            self.assertEqual(self.hero(after)["army"][0]["count"], 4)
            self.assertEqual(self.castle(after, castle_id)["garrison"][0]["count"], 9)
            self.assertEqual(self.totals(after), self.totals(before))

    def test_remote_and_foreign_access_are_rejected_atomically(self):
        with self.session() as (game, _):
            decision, castle_id, other = self.two_heroes(game, far=True)
            token = decision["token"]
            self.assert_rejected(game, lambda: game.meet_heroes(52, other, token=token), "illegal_action")
            for target in (endpoint("castle", castle_id, 0), endpoint("hero", 42, 4), endpoint("castle", 867, 0)):
                self.assert_rejected(game, lambda: game.transfer_troops(endpoint("hero", 52, 0), target, 1, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.meet_heroes(52, 42, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.meet_heroes(52, 52, token=token), "illegal_action")

    def test_bad_slots_types_counts_and_incompatible_merges_preserve_world(self):
        with self.session() as (game, _):
            decision, _, _ = self.start(game)
            token = decision["token"]
            source, target = endpoint("hero", 52, 0), endpoint("hero", 52, 2)
            for bad in ({}, {"kind": "unknown", "id": 52, "slot": 0}, endpoint("hero", 52, 5), endpoint("hero", 52, -1),
                        endpoint("hero", 52, True), endpoint("hero", True, 0), endpoint("hero", 1 << 40, 0),
                        {"kind": "hero", "id": 52, "slot": 0, "extra": 1}):
                self.assert_rejected(game, lambda: game.step("army.transfer", token=token, params={"source": bad, "target": target, "count": 1}), "invalid_request")
            for count in (0, -1, True, "1", 1.5, 1 << 40):
                self.assert_rejected(game, lambda: game.transfer_troops(source, target, count, token=token), "invalid_request")
            self.assert_rejected(game, lambda: game.transfer_troops(source, target, 10, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.transfer_troops(source, endpoint("hero", 52, 1), 1, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.swap_troops(source, source, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.swap_troops(target, endpoint("hero", 52, 3), token=token), "illegal_action")

    def test_new_meeting_requires_movement_and_session_detach_discards_context(self):
        with self.session() as (game, _):
            decision, castle_id, other = self.two_heroes(game)
            for index in range(8):
                decision = game.move_hero(52, 32, 26 if index % 2 == 0 else 25, token=decision["token"])["decision"]
            decision = game.meet_heroes(52, other, token=decision["token"])["decision"]
            self.assertEqual(self.hero(game.get_state())["move_points"], 0)
            # A different successful gameplay action ends the encounter. It does not replenish movement.
            decision = game.trade_resources(castle_id, 1, 64, 1, token=decision["token"])["decision"]
            self.assertIsNone(decision["army_meeting"])
            self.assert_rejected(game, lambda: game.meet_heroes(52, other, token=decision["token"]), "illegal_action")
            decision = game.end_turn(token=decision["token"])["decision"]
            decision = game.meet_heroes(52, other, token=decision["token"])["decision"]
            game.step("session.stop", token=decision["token"])
            self.assertIsNone(game.get_state()["army_meeting"])
            self.assertIsNone(game.start_session(1)["army_meeting"])


if __name__ == "__main__":
    unittest.main()
