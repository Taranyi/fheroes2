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

"""Exercise native upgrade, dismissal and mage-guild purchase rules through the real engine."""

import unittest

from fheroes2_env import EngineError
import test_castle as support

ROOT = support.ROOT


def slot(kind, entity_id, index):
    return {"kind": kind, "id": entity_id, "slot": index}


class HeroOperationTests(unittest.TestCase):
    session = support.CastleTests.session
    start = support.CastleTests.start
    assert_rejected = support.CastleTests.assert_rejected
    player = support.CastleTests.player
    assert_spent = support.CastleTests.assert_spent

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        cls.fixtures = support.CastleTests.fixtures

    def hero(self, state, hero_id=52):
        return next(h for h in state["heroes"] if h["id"] == hero_id)

    def hire_bookless(self, game, *, save=None):
        if save:
            game.load_save(save)
            decision = game.start_session(1)
            castle_id = 896
        else:
            decision, _, castle_id = self.start(game)
        decision = game.refresh_hero_offers(castle_id, token=decision["token"])["decision"]
        decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
        decision = game.hire_hero(castle_id, 12, token=decision["token"])["decision"]
        return decision, castle_id

    def test_army_options_are_read_only_and_include_ai_sides(self):
        with self.session() as (game, _):
            with self.assertRaises(EngineError) as error:
                game.get_army_options("hero", 52)
            self.assertEqual(error.exception.code, "no_game_loaded")
            decision, _, _ = self.start(game)
            before = game.get_state()
            for kind, entities in (("hero", [h for h in before["heroes"] if h["active"]]), ("castle", before["castles"])):
                for entity in entities:
                    options = game.get_army_options(kind, entity["id"])
                    self.assertEqual(options["owner"], entity["owner"])
                    self.assertEqual(options["perspective"], "omniscient")
                    self.assertEqual(len(options["slots"]), 5)
                    self.assertEqual(game.get_army_options(kind, entity["id"]), options)
            self.assertEqual(game.get_state(), before)
            self.assertEqual(game.get_decision(), decision)
            for params in ({}, {"kind": "other", "id": 52}, {"kind": "hero", "id": True}, {"kind": "hero", "id": 1 << 40},
                           {"kind": "castle", "id": 0xFFFFFFFF}, {"kind": "hero", "id": 52, "extra": 0}):
                self.assert_rejected(game, lambda: game.request("get_army_options", params))

    def test_native_hero_stack_upgrade_has_exact_price_and_keeps_count(self):
        with self.session() as (game, _):
            decision, human, castle_id = self.start(game)
            source = slot("hero", 52, 1)
            self.assertFalse(game.get_army_options("hero", 52)["slots"][1]["can_upgrade"])
            self.assert_rejected(game, lambda: game.upgrade_troop(source, token=decision["token"]), "illegal_action")
            decision = game.build_castle(castle_id, 1 << 26, token=decision["token"])["decision"]
            quote = game.get_army_options("hero", 52)["slots"][1]
            self.assertTrue(quote["can_upgrade"])
            self.assertEqual(quote["upgrade_cost"]["gold"], 400)
            before = game.get_state()
            result = game.upgrade_troop(source, token=decision["token"])
            after = game.get_state()
            self.assert_spent(before, after, human["id"], quote["upgrade_cost"])
            troop = self.hero(after)["army"][1]
            self.assertEqual((troop["monster_id"], troop["count"]), (quote["upgrade_monster_id"], 4))
            self.assertEqual(before["date"], after["date"])
            self.assertEqual(self.hero(before)["move_points"], self.hero(after)["move_points"])
            self.assert_rejected(game, lambda: game.upgrade_troop(source, token=result["decision"]["token"]), "illegal_action")

    def test_garrison_upgrade_and_funds_or_location_rejections(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            decision = game.recruit_castle(castle_id, 1 << 21, 2, token=decision["token"])["decision"]
            decision = game.build_castle(castle_id, 1 << 26, token=decision["token"])["decision"]
            source = slot("castle", castle_id, 0)
            quote = game.get_army_options("castle", castle_id)["slots"][0]
            self.assertTrue(quote["can_upgrade"])
            self.assertEqual(quote["upgrade_cost"]["gold"], 200)
            decision = game.upgrade_troop(source, token=decision["token"])["decision"]
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            self.assert_rejected(game, lambda: game.upgrade_troop(slot("hero", 52, 1), token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.upgrade_troop(slot("hero", 42, 1), token=decision["token"]), "illegal_action")
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            decision = game.build_castle(castle_id, 1 << 26, token=decision["token"])["decision"]
            decision = game.trade_resources(castle_id, 64, 2, 1, token=decision["token"])["decision"]
            decision = game.recruit_castle(castle_id, 1 << 20, 8, token=decision["token"])["decision"]
            decision = game.recruit_castle(castle_id, 1 << 21, 4, token=decision["token"])["decision"]
            self.assertEqual(self.player(game.get_state(), 1)["funds"]["gold"], 100)
            self.assertFalse(game.get_army_options("hero", 52)["slots"][1]["can_upgrade"])
            self.assert_rejected(game, lambda: game.upgrade_troop(slot("hero", 52, 1), token=decision["token"]), "illegal_action")

    def test_troop_dismissal_is_whole_stack_and_protects_last_hero_stack(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            before = game.get_state()
            result = game.dismiss_troop(slot("hero", 52, 0), token=decision["token"])
            decision = result["decision"]
            after = game.get_state()
            self.assertIsNone(self.hero(after)["army"][0])
            self.assertEqual(result["events"][-1]["count"], 9)
            self.assertEqual(after["players"], before["players"])
            self.assertEqual(after["date"], before["date"])
            self.assertFalse(game.get_army_options("hero", 52)["slots"][1]["can_dismiss"])
            self.assert_rejected(game, lambda: game.dismiss_troop(slot("hero", 52, 1), token=decision["token"]), "illegal_action")
            decision = game.recruit_castle(castle_id, 1 << 20, 1, token=decision["token"])["decision"]
            decision = game.dismiss_troop(slot("castle", castle_id, 0), token=decision["token"])["decision"]
            self.assert_rejected(game, lambda: game.dismiss_troop(slot("castle", castle_id, 0), token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.dismiss_troop(slot("hero", 42, 0), token=decision["token"]), "illegal_action")

    def test_hero_dismissal_respects_castle_and_preserves_native_free_hero_state(self):
        with self.session() as (game, _):
            decision, _, _ = self.start(game)
            self.assert_rejected(game, lambda: game.dismiss_hero(52, token=decision["token"]), "illegal_action")
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            before = game.get_state()
            self.assertTrue(self.hero(before)["can_dismiss"])
            result = game.dismiss_hero(52, token=decision["token"])
            after = game.get_state()
            self.assertFalse(self.hero(after)["active"])
            self.assertIsNone(self.hero(after)["position"])
            self.assertNotIn(52, self.player(after, 1)["hero_ids"])
            self.assertEqual(self.hero(after)["artifacts"], self.hero(before)["artifacts"])
            self.assertEqual(self.player(after, 1)["funds"], self.player(before, 1)["funds"])
            self.assertEqual(result["events"][-1]["type"], "hero_dismissed")
            self.assert_rejected(game, lambda: game.dismiss_hero(52, token=result["decision"]["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.dismiss_hero(42, token=result["decision"]["token"]), "illegal_action")

    def test_spell_book_purchase_uses_native_price_and_teaches_mage_guild_spells(self):
        with self.session() as (game, _):
            decision, _ = self.hire_bookless(game)
            before = game.get_state()
            self.assertFalse(self.hero(before, 12)["has_spell_book"])
            self.assertTrue(self.hero(before, 12)["can_buy_spell_book"])
            result = game.buy_spell_book(12, token=decision["token"])
            after = game.get_state()
            self.assert_spent(before, after, 1, self.hero(before, 12)["spell_book_cost"])
            self.assertEqual(result["events"][-1]["cost"]["gold"], 500)
            self.assertTrue(self.hero(after, 12)["has_spell_book"])
            self.assertEqual(self.hero(after, 12)["artifacts"][0]["id"], 82)
            self.assertTrue(self.hero(after, 12)["spells"])
            self.assertEqual(self.hero(after, 12)["move_points"], self.hero(before, 12)["move_points"])
            self.assert_rejected(game, lambda: game.buy_spell_book(12, token=result["decision"]["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.buy_spell_book(52, token=result["decision"]["token"]), "illegal_action")
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_book_funds_and_malformed_operation_requests_are_atomic(self):
        with self.session() as (game, _):
            decision, castle_id = self.hire_bookless(game)
            decision = game.trade_resources(castle_id, 64, 2, 1, token=decision["token"])["decision"]
            self.assert_rejected(game, lambda: game.buy_spell_book(12, token=decision["token"]), "illegal_action")
            for hero_id in (True, -1, 1 << 40, "hero"):
                self.assert_rejected(game, lambda: game.buy_spell_book(hero_id, token=decision["token"]), "invalid_request")
                self.assert_rejected(game, lambda: game.dismiss_hero(hero_id, token=decision["token"]), "invalid_request")
            for action in ("army.upgrade", "army.dismiss"):
                for params in ({}, {"source": slot("hero", 52, 5)}, {"source": slot("hero", 52, 0), "extra": 1}):
                    self.assert_rejected(game, lambda: game.step(action, token=decision["token"], params=params), "invalid_request")

    def test_native_full_bag_and_scenario_protection_fixtures(self):
        full = ROOT / "build/python-env-baseline/fixtures/heroes-full-day1.sav"
        protected = ROOT / "build/python-env-baseline/fixtures/heroes-protected-day1.sav"
        if not full.is_file() or not protected.is_file():
            self.skipTest("Prepare native hero-operation fixtures; see docs/PYTHON_ENV_HERO_OPERATIONS.md")
        with self.session() as (game, _):
            decision, _ = self.hire_bookless(game, save=full)
            hero = self.hero(game.get_state(), 12)
            self.assertFalse(hero["has_spell_book"])
            self.assertTrue(all(hero["artifacts"]))
            self.assert_rejected(game, lambda: game.buy_spell_book(12, token=decision["token"]), "illegal_action")
        with self.session() as (game, _):
            game.load_save(protected)
            decision = game.start_session(1)
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            self.assertTrue(self.hero(game.get_state())["dismissal_prohibited"])
            self.assert_rejected(game, lambda: game.dismiss_hero(52, token=decision["token"]), "illegal_action")


if __name__ == "__main__":
    unittest.main()
