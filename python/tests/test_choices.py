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

"""Exercise suspended native choices and adventure spells through real engine processes."""

import unittest

from fheroes2_env import EngineError
import test_castle as support

ROOT = support.ROOT


class ChoiceTests(unittest.TestCase):
    session = support.CastleTests.session
    assert_rejected = support.CastleTests.assert_rejected
    player = support.CastleTests.player

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        cls.fixtures = support.CastleTests.fixtures
        for name in ("chest", "join", "pursue", "recruit", "spells", "paid-join"):
            if not (ROOT / f"build/python-env-baseline/fixtures/choices-{name}-day1.sav").is_file():
                raise unittest.SkipTest("Prepare native choice fixtures; see docs/PYTHON_ENV_CHOICES.md")

    def start(self, game, name="chest"):
        game.load_save(ROOT / f"build/python-env-baseline/fixtures/choices-{name}-day1.sav")
        return game.start_session(1)

    def hero(self, state):
        return next(h for h in state["heroes"] if h["id"] == 52)

    def answer(self, game, decision, value):
        return game.answer_choice(decision["pending_choice"]["choice_id"], value, token=decision["token"])

    def encounter(self, game, decision):
        result = game.move_hero(52, 32, 25, token=decision["token"])
        self.assertEqual(result["decision"]["phase"], "choice")
        return result["decision"]

    def test_chest_gold_and_pending_queries_do_not_apply_reward_early(self):
        with self.session() as (game, directory):
            decision = self.start(game)
            before = game.get_state()
            decision = self.encounter(game, decision)
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "treasure.gold_or_experience")
            self.assertEqual(choice["values"], {"gold": 2500, "experience": 2000})
            waiting = game.get_state()
            self.assertEqual(waiting["phase"], "choice")
            self.assertEqual(waiting["pending_choice"], choice)
            self.assertEqual(self.player(waiting, 1)["funds"], self.player(before, 1)["funds"])
            for _ in range(2):
                self.assertEqual(game.get_state(), waiting)
                self.assertEqual(game.get_decision(), decision)
                game.render(width=64, height=64, center=(32, 25))
                self.assertEqual(game.get_state(), waiting)
                game.get_army_options("hero", 42)
            result = self.answer(game, decision, 1)
            after = game.get_state()
            self.assertEqual(result["decision"]["phase"], "adventure")
            self.assertIsNone(after["pending_choice"])
            self.assertEqual(self.player(after, 1)["funds"]["gold"] - self.player(before, 1)["funds"]["gold"], 2500)
            self.assertEqual(self.hero(after)["experience"], self.hero(before)["experience"])
            self.assertEqual(after["date"], before["date"])
            self.assertFalse(game.runtime_info()["video_initialized"])
            self.assertEqual(list(directory.iterdir()), [])

    def test_experience_resumes_into_each_native_level_up_once(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            decision = self.encounter(game, decision)
            result = self.answer(game, decision, 0)
            count = 0
            ids = [decision["pending_choice"]["choice_id"]]
            while result["decision"]["phase"] == "choice":
                decision = result["decision"]
                choice = decision["pending_choice"]
                self.assertEqual(choice["kind"], "hero.secondary_skill")
                self.assertGreater(choice["choice_id"], ids[-1])
                ids.append(choice["choice_id"])
                self.assertEqual(game.get_decision(), decision)
                result = self.answer(game, decision, choice["options"][0])
                count += 1
                self.assertLess(count, 10)
            after = game.get_state()
            self.assertGreaterEqual(count, 1)
            self.assertEqual(self.hero(after)["experience"] - self.hero(before)["experience"], 2000)
            self.assertEqual(self.player(after, 1)["funds"], self.player(before, 1)["funds"])
            self.assertEqual(sum(e["type"] == "choice_answered" for e in result["events"]), count + 1)
            self.assert_rejected(game, lambda: self.answer(game, decision, 0), "stale_decision")

    def test_original_baseline_chest_is_now_a_supported_native_target(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            decision = game.start_session(1)
            before = game.get_state()
            result = game.move_hero(52, 34, 20, token=decision["token"])
            decision = result["decision"]
            self.assertEqual(decision["pending_choice"]["kind"], "treasure.gold_or_experience")
            gold = decision["pending_choice"]["values"]["gold"]
            self.answer(game, decision, 1)
            after = game.get_state()
            self.assertEqual(self.player(after, 1)["funds"]["gold"] - self.player(before, 1)["funds"]["gold"], gold)

    def test_invalid_answers_keep_the_native_stack_and_world_unchanged(self):
        with self.session() as (game, _):
            first = self.start(game)
            decision = self.encounter(game, first)
            choice_id = decision["pending_choice"]["choice_id"]
            for value in (2, -1):
                self.assert_rejected(game, lambda: self.answer(game, decision, value), "illegal_action")
            for value in (True, "1", 1.5, 1 << 64):
                self.assert_rejected(game, lambda: self.answer(game, decision, value), "invalid_request")
            self.assert_rejected(game, lambda: game.answer_choice(choice_id + 1, 1, token=decision["token"]), "stale_choice")
            self.assert_rejected(game, lambda: game.answer_choice(choice_id, 1, token=first["token"]), "stale_decision")
            self.assert_rejected(game, lambda: game.end_turn(token=decision["token"]), "choice_required")
            self.assert_rejected(game, lambda: game.step("session.stop", token=decision["token"], params={"extra": 1}), "choice_required")
            self.answer(game, decision, 1)

    def test_stop_during_nested_choice_rolls_back_the_whole_original_action(self):
        with self.session() as (game, _):
            first = self.start(game)
            before = game.get_state()
            decision = self.encounter(game, first)
            result = self.answer(game, decision, 0)
            self.assertEqual(result["decision"]["phase"], "choice")
            game.step("session.stop", token=result["decision"]["token"])
            self.assertEqual(game.get_state(), before)
            decision = game.start_session(1)
            decision = self.encounter(game, decision)
            self.assertGreater(decision["pending_choice"]["choice_id"], result["decision"]["pending_choice"]["choice_id"])
            self.answer(game, decision, 1)

    def test_close_during_a_choice_unwinds_without_hanging(self):
        with self.session() as (game, _):
            decision = self.start(game)
            self.encounter(game, decision)
            game.close()

    def test_neutral_join_and_refused_join_battle_boundary_are_native(self):
        with self.session() as (game, _):
            decision = self.start(game, "join")
            before = game.get_state()
            decision = self.encounter(game, decision)
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "monster.join")
            yes, no = choice["options"]
            self.assertEqual(choice["values"]["count"], 5)
            self.answer(game, decision, yes)
            after = game.get_state()
            self.assertEqual(sum(t["count"] for t in self.hero(after)["army"] if t) - sum(t["count"] for t in self.hero(before)["army"] if t), 5)
            self.assertEqual(self.player(after, 1)["funds"], self.player(before, 1)["funds"])
        with self.session() as (game, _):
            first = self.start(game, "join")
            before = game.get_state()
            decision = self.encounter(game, first)
            result = self.answer(game, decision, decision["pending_choice"]["options"][1])
            self.assertEqual(result["decision"]["phase"], "battle")
            game.step("session.stop", token=result["decision"]["token"])
            self.assertEqual(game.get_state(), before)

    def test_neutral_pursuit_can_be_declined_without_starting_a_battle(self):
        with self.session() as (game, _):
            decision = self.start(game, "pursue")
            before = game.get_state()
            decision = self.encounter(game, decision)
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "monster.pursue")
            self.answer(game, decision, choice["options"][1])
            after = game.get_state()
            self.assertEqual(self.hero(after)["army"], self.hero(before)["army"])
            self.assertNotEqual(after["map"]["tiles"][932]["object_type"], before["map"]["tiles"][932]["object_type"])

    def test_paid_join_uses_the_native_diplomacy_count_and_full_offer_price(self):
        with self.session() as (game, _):
            decision = self.start(game, "paid-join")
            before = game.get_state()
            decision = self.encounter(game, decision)
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "monster.join")
            self.assertGreater(choice["values"]["gold"], 0)
            self.answer(game, decision, choice["options"][0])
            after = game.get_state()
            count = sum(t["count"] for t in self.hero(after)["army"] if t and t["monster_id"] == choice["values"]["monster_id"])
            self.assertEqual(count, choice["values"]["count"])
            self.assertEqual(self.player(before, 1)["funds"]["gold"] - self.player(after, 1)["funds"]["gold"], choice["values"]["gold"])

    def test_recruitment_confirmation_then_exact_native_quantity_and_cost(self):
        with self.session() as (game, _):
            decision = self.start(game, "recruit")
            before = game.get_state()
            decision = self.encounter(game, decision)
            self.assertEqual(decision["pending_choice"]["kind"], "confirmation")
            result = self.answer(game, decision, decision["pending_choice"]["options"][0])
            decision = result["decision"]
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "army.recruit_count")
            self.assertEqual((choice["minimum"], choice["maximum"]), (0, 4))
            self.assert_rejected(game, lambda: self.answer(game, decision, 5), "illegal_action")
            self.answer(game, decision, 2)
            after = game.get_state()
            genies = sum(t["count"] for t in self.hero(after)["army"] if t and t["monster_id"] == choice["values"]["monster_id"])
            self.assertEqual(genies, 2)
            self.assertEqual(self.player(before, 1)["funds"]["gold"] - self.player(after, 1)["funds"]["gold"], 2 * choice["values"]["gold_per_unit"])

    def test_identify_and_visions_use_native_cost_conditions_and_state(self):
        with self.session() as (game, _):
            decision = self.start(game, "spells")
            before = game.get_state()
            quotes = self.hero(before)["adventure_spell_options"]
            for quote in quotes:
                self.assertTrue(quote["can_cast"])
                previous = game.get_state()
                result = game.cast_spell(52, quote["spell_id"], token=decision["token"])
                decision = result["decision"]
                after = game.get_state()
                self.assertEqual(self.hero(previous)["spell_points"] - self.hero(after)["spell_points"], quote["spell_points"])
                self.assertEqual(result["events"][-1]["type"], "spell_cast")
                self.assertEqual(previous["date"], after["date"])
                if quote is quotes[0]:  # Identify Hero is already active; native Visions can be cast again.
                    self.assert_rejected(game, lambda: game.cast_spell(52, quote["spell_id"], token=decision["token"]), "illegal_action")
            player = self.player(game.get_state(), 1)
            self.assertTrue(player["identify_hero"])
            self.assertIn(968, player["vision_monster_indices"])

    def test_spell_queries_are_read_only_and_invalid_casts_are_atomic(self):
        with self.session() as (game, _):
            decision = self.start(game, "spells")
            before = game.get_state()
            self.assertEqual(game.get_state(), before)
            self.assert_rejected(game, lambda: game.cast_spell(42, 1, token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.cast_spell(52, 1, token=decision["token"]), "unsupported_action")
            for spell_id in (True, -1, 9999, "spell"):
                self.assert_rejected(game, lambda: game.cast_spell(52, spell_id, token=decision["token"]), "invalid_request")


if __name__ == "__main__":
    unittest.main()
