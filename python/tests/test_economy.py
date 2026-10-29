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

"""Exercise hero hiring and the shared marketplace operation on actual saves."""

import unittest

from fheroes2_env import EngineError
import test_castle as support


class EconomyTests(unittest.TestCase):
    session = support.CastleTests.session
    start = support.CastleTests.start
    assert_rejected = support.CastleTests.assert_rejected
    player = support.CastleTests.player
    castle = support.CastleTests.castle
    assert_spent = support.CastleTests.assert_spent

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        cls.fixtures = support.CastleTests.fixtures

    def ready(self, game, *, empty_castle=True):
        decision, human, castle_id = self.start(game)
        decision = game.refresh_hero_offers(castle_id, token=decision["token"])["decision"]
        if empty_castle:
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
        return decision, human, castle_id

    def test_cached_offers_and_market_quotes_are_read_only_for_all_sides(self):
        with self.session() as (game, _):
            decision, _, _ = self.start(game)
            before = game.get_state()
            for castle in before["castles"]:
                options = game.get_castle_options(castle["id"])
                self.assertEqual(game.get_castle_options(castle["id"]), options)
                self.assertEqual(len(options["hero_hiring"]["offers"]), 2)
                self.assertEqual(len(options["market"]["trades"]), 42)
            self.assertEqual(game.get_state(), before)
            self.assertEqual(game.get_decision(), decision)

    def test_explicit_refresh_and_native_hire_apply_payment_and_visitor_state(self):
        with self.session() as (game, _):
            decision, human, castle_id = self.ready(game)
            options = game.get_castle_options(castle_id)["hero_hiring"]
            self.assertTrue(options["can_hire"])
            offer = next(h for h in options["offers"] if h["available"])
            before = game.get_state()
            result = game.hire_hero(castle_id, offer["hero_id"], token=decision["token"])
            after = game.get_state()
            self.assert_spent(before, after, human["id"], options["cost"])
            self.assertIn(offer["hero_id"], self.player(after, human["id"])["hero_ids"])
            self.assertEqual(self.castle(after, castle_id)["visiting_hero_id"], offer["hero_id"])
            hero = next(h for h in after["heroes"] if h["id"] == offer["hero_id"])
            self.assertTrue(hero["active"])
            self.assertEqual(hero["owner"], human["id"])
            self.assertEqual(hero["position"]["index"], castle_id)
            self.assertTrue(any(t for t in hero["army"]))
            self.assertEqual(after["date"], before["date"])
            self.assertEqual(result["events"][0]["type"], "hero_hired")
            self.assertFalse(game.get_castle_options(castle_id)["hero_hiring"]["can_hire"])
            self.assert_rejected(game, lambda: game.hire_hero(castle_id, offer["hero_id"], token=decision["token"]), "stale_decision")
            self.assertFalse(game.runtime_info()["video_initialized"])
            self.assertFalse(game.runtime_info()["audio_initialized"])

    def test_hire_rejects_occupied_castle_nonoffered_and_foreign_heroes(self):
        with self.session() as (game, _):
            decision, human, castle_id = self.ready(game, empty_castle=False)
            token = decision["token"]
            offer = next(h for h in game.get_castle_options(castle_id)["hero_hiring"]["offers"] if h["available"])
            self.assert_rejected(game, lambda: game.hire_hero(castle_id, offer["hero_id"], token=token), "illegal_action")
            decision = game.move_hero(52, 32, 25, token=token)["decision"]
            token = decision["token"]
            state = game.get_state()
            foreign_castle = next(c["id"] for c in state["castles"] if c["owner"] != human["id"])
            for hero_id in (52, 42):
                self.assert_rejected(game, lambda: game.hire_hero(castle_id, hero_id, token=token), "illegal_action")
            offered_ids = {h["hero_id"] for h in game.get_castle_options(castle_id)["hero_hiring"]["offers"]}
            nonoffered = next(h["id"] for h in state["heroes"] if not h["active"] and h["id"] not in offered_ids)
            self.assert_rejected(game, lambda: game.hire_hero(castle_id, nonoffered, token=token), "illegal_action")
            for hero_id in (-1, True, 0xFFFFFFFF, "hero"):
                self.assert_rejected(game, lambda: game.hire_hero(castle_id, hero_id, token=token), "invalid_request")
            self.assert_rejected(game, lambda: game.hire_hero(foreign_castle, offer["hero_id"], token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.refresh_hero_offers(foreign_castle, token=token), "illegal_action")

    def test_native_market_lots_cover_gold_and_resource_directions(self):
        for source, target, lots, expected_sell, expected_buy in ((1, 64, 2, 2, 50), (64, 4, 1, 2500, 1),
                                                               (1, 2, 1, 20, 1), (2, 4, 1, 5, 1), (4, 1, 1, 10, 1),
                                                               (64, 2, 1, 5000, 1), (2, 64, 1, 1, 50)):
            with self.subTest(source=source, target=target), self.session() as (game, _):
                decision, human, castle_id = self.start(game)
                before = game.get_state()
                result = game.trade_resources(castle_id, source, target, lots, token=decision["token"])
                decision = result["decision"]
                event = result["events"][0]
                self.assertEqual((event["sold"], event["bought"]), (expected_sell, expected_buy))
                after = game.get_state()
                keys = {1: "wood", 2: "mercury", 4: "ore", 64: "gold"}
                cost = {key: 0 for key in human["funds"]}
                cost[keys[source]], cost[keys[target]] = expected_sell, -expected_buy
                self.assert_spent(before, after, human["id"], cost)
                self.assertEqual(before["date"], after["date"])

    def test_market_limits_rates_and_validation_are_atomic(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game, fixture=1)
            self.assertEqual(game.get_castle_options(castle_id)["market"]["marketplace_count"], 0)
            self.assert_rejected(game, lambda: game.trade_resources(castle_id, 1, 64, 1, token=decision["token"]), "illegal_action")
            decision = game.build_castle(castle_id, 128, token=decision["token"])["decision"]
            quote = next(q for q in game.get_castle_options(castle_id)["market"]["trades"] if q["resource_from"] == 1 and q["resource_to"] == 64)
            self.assertEqual((quote["sell_per_lot"], quote["buy_per_lot"]), (1, 25))
            token = decision["token"]
            for source, target, lots in ((0, 64, 1), (3, 64, 1), (1, 1, 1), (128, 1, 1), (-1, 1, 1),
                                         (True, 64, 1), (1, 64, 0), (1, 64, -1), (1, 64, True), (1, 64, 1.5), (1, 64, 1 << 40)):
                self.assert_rejected(game, lambda: game.trade_resources(castle_id, source, target, lots, token=token), "invalid_request")
            self.assert_rejected(game, lambda: game.trade_resources(castle_id, 1, 64, quote["max_lots"] + 1, token=token), "illegal_action")
            enemy = next(c["id"] for c in game.get_state()["castles"] if c["owner"] != 2)
            self.assert_rejected(game, lambda: game.trade_resources(enemy, 1, 64, 1, token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.request("step", {"action": "market.trade", "token": token,
                                "params": {"castle_id": castle_id, "resource_from": 1, "resource_to": 64, "lots": 1, "trading_post": True}}), "invalid_request")

    def test_hire_requires_payment_even_when_offer_and_castle_are_available(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.ready(game)
            decision = game.trade_resources(castle_id, 64, 1, 3, token=decision["token"])["decision"]
            options = game.get_castle_options(castle_id)["hero_hiring"]
            self.assertFalse(options["can_hire"])
            offer = next(h for h in options["offers"] if h["available"])
            self.assert_rejected(game, lambda: game.hire_hero(castle_id, offer["hero_id"], token=decision["token"]), "illegal_action")


if __name__ == "__main__":
    unittest.main()
