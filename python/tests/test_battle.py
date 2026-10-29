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

"""Validate real adventure-to-battle-to-adventure native control and cancellation."""

import importlib.util
import unittest

from fheroes2_env import EngineError
import test_castle as support

ROOT = support.ROOT
_spec = importlib.util.spec_from_file_location("battle_example", ROOT / "python/examples/battle.py")
_example = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_example)


class BattleTests(unittest.TestCase):
    session = support.CastleTests.session
    assert_rejected = support.CastleTests.assert_rejected
    player = support.CastleTests.player

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        for name in ("melee", "ranged", "heroes", "loss", "boss", "siege"):
            if not (ROOT / f"build/python-env-baseline/fixtures/battles-{name}-day1.sav").is_file():
                raise unittest.SkipTest("Prepare native battle fixtures; see docs/PYTHON_ENV_BATTLE.md")

    def start(self, game, profile="melee"):
        game.load_save(ROOT / f"build/python-env-baseline/fixtures/battles-{profile}-day1.sav")
        return game.start_session(1)

    def hero(self, state, hero_id=52):
        return next(h for h in state["heroes"] if h["id"] == hero_id)

    def enter(self, game, decision):
        result = game.move_hero(52, 32, 25, token=decision["token"])
        while result["decision"]["phase"] == "choice":
            decision = result["decision"]
            choice = decision["pending_choice"]
            self.assertEqual(choice["kind"], "monster.pursue")
            result = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])
        return result

    def finish(self, game, result, *, use_spells=False, passive=False):
        for _ in range(500):
            decision = result["decision"]
            if decision["phase"] == "battle":
                battle = decision["battle"]
                action = next(a for a in battle["actions"] if a["kind"] == "skip") if passive else _example.select_action(battle, use_spells=use_spells)
                result = game.battle_action(action["action_id"], token=decision["token"])
            elif decision["phase"] == "choice":
                choice = decision["pending_choice"]
                result = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])
            else:
                return result
        self.fail("Policy did not complete a native battle within 500 decisions")

    def test_board_units_legal_candidates_and_repeated_queries_are_read_only(self):
        with self.session() as (game, directory):
            decision = self.start(game)
            result = self.enter(game, decision)
            decision = result["decision"]
            self.assertEqual(decision["phase"], "battle")
            self.assertEqual(decision["available_actions"], ["battle.act", "session.stop"])
            battle = decision["battle"]
            self.assertEqual(battle["map_index"], 932)
            self.assertEqual((battle["width"], battle["height"], len(battle["board"])), (11, 9, 99))
            self.assertTrue(any(u["army_color"] != 1 for u in battle["units"]))
            self.assertTrue(any(u["uid"] == battle["current_unit_uid"] for u in battle["units"]))
            self.assertEqual([a["action_id"] for a in battle["actions"]], list(range(len(battle["actions"]))))
            before = game.get_state()
            self.assertEqual(before["battle"], battle)
            for _ in range(2):
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)
                game.get_army_options("hero", 42)
                game.render(width=64, height=64)
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)
            self.assertEqual(list(directory.iterdir()), [])
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_melee_native_win_updates_army_world_and_experience(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            result = self.finish(game, self.enter(game, decision))
            self.assertEqual(result["decision"]["phase"], "adventure")
            after = game.get_state()
            completed = next(e for e in result["events"] if e["type"] == "battle_completed")
            self.assertTrue(completed["attacker_result"] & 0x80)
            self.assertEqual(self.hero(after)["experience"] - self.hero(before)["experience"], completed["attacker_experience"])
            kinds = {e["action"]["kind"] for e in result["events"] if e["type"] == "battle_action"}
            self.assertIn("move", kinds)
            self.assertIn("attack", kinds)
            self.assertEqual(after["map"]["tiles"][932]["object_type"], 0)
            self.assertIsNone(after["battle"])

    def test_native_ranged_attack_finishes_and_removes_the_enemy(self):
        with self.session() as (game, _):
            decision = self.start(game, "ranged")
            result = self.finish(game, self.enter(game, decision))
            self.assertTrue(any(e["type"] == "battle_action" and e["action"]["kind"] == "shoot" for e in result["events"]))
            self.assertEqual(game.get_state()["map"]["tiles"][932]["object_type"], 0)

    def test_spell_cost_and_one_spell_per_round_use_native_checks(self):
        with self.session() as (game, _):
            decision = self.start(game)
            result = self.enter(game, decision)
            decision = result["decision"]
            battle = decision["battle"]
            spell = next(a for a in battle["actions"] if a["kind"] == "spell" and a["spell_id"] == 26)
            result = game.battle_action(spell["action_id"], token=decision["token"])
            following = result["decision"]["battle"]
            self.assertEqual(following["current_unit_uid"], battle["current_unit_uid"])
            self.assertEqual(battle["attacker_commander"]["spell_points"] - following["attacker_commander"]["spell_points"], spell["spell_points"])
            self.assertFalse(any(a["kind"] == "spell" for a in following["actions"]))
            self.finish(game, result)

    def test_retreat_uses_native_dismissal_without_hanging(self):
        with self.session() as (game, _):
            decision = self.start(game)
            result = self.enter(game, decision)
            decision = result["decision"]
            action = next(a for a in decision["battle"]["actions"] if a["kind"] == "retreat")
            result = game.battle_action(action["action_id"], token=decision["token"])
            completed = next(e for e in result["events"] if e["type"] == "battle_completed")
            self.assertTrue(completed["attacker_result"] & 2)
            self.assertFalse(self.hero(game.get_state())["active"])

    def test_hero_surrender_transfers_exact_native_price(self):
        with self.session() as (game, _):
            decision = self.start(game, "heroes")
            before = game.get_state()
            result = self.enter(game, decision)
            decision = result["decision"]
            action = next(a for a in decision["battle"]["actions"] if a["kind"] == "surrender")
            result = game.battle_action(action["action_id"], token=decision["token"])
            after = game.get_state()
            self.assertEqual(self.player(before, 1)["funds"]["gold"] - self.player(after, 1)["funds"]["gold"], action["gold"])
            self.assertEqual(self.player(after, 2)["funds"]["gold"] - self.player(before, 2)["funds"]["gold"], action["gold"])
            self.assertFalse(self.hero(after)["active"])
            self.assertTrue(any(e["type"] == "battle_completed" and e["attacker_result"] & 4 for e in result["events"]))

    def test_native_loss_can_happen_before_the_first_external_unit_turn(self):
        with self.session() as (game, _):
            decision = self.start(game, "loss")
            result = self.enter(game, decision)
            result = self.finish(game, result, passive=True)
            self.assertFalse(self.hero(game.get_state())["active"])
            self.assertTrue(any(e["type"] == "battle_completed" and e["attacker_result"] & 1 for e in result["events"]))

    def test_battle_win_can_continue_into_level_up_choices(self):
        with self.session() as (game, _):
            decision = self.start(game, "boss")
            before = game.get_state()
            result = self.finish(game, self.enter(game, decision))
            self.assertTrue(any(e["type"] == "choice_requested" and e["choice"]["kind"] == "hero.secondary_skill" for e in result["events"]))
            self.assertGreater(self.hero(game.get_state())["level"], self.hero(before)["level"])

    def test_invalid_candidates_and_stale_tokens_leave_the_live_battle_unchanged(self):
        with self.session() as (game, _):
            first = self.start(game)
            decision = self.enter(game, first)["decision"]
            for value in (True, -1, "move", 1 << 40):
                self.assert_rejected(game, lambda: game.battle_action(value, token=decision["token"]), "invalid_request")
            self.assert_rejected(game, lambda: game.battle_action(99999, token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.end_turn(token=decision["token"]), "battle_action_required")
            self.assert_rejected(game, lambda: game.battle_action(0, token=first["token"]), "stale_decision")
            wrong = dict(decision["token"], player_id=2)
            self.assert_rejected(game, lambda: game.battle_action(0, token=wrong), "wrong_player")

    def test_stop_after_combat_actions_restores_the_whole_adventure_checkpoint(self):
        with self.session() as (game, _):
            first = self.start(game)
            before = game.get_state()
            result = self.enter(game, first)
            original = result["decision"]["battle"]
            decision = result["decision"]
            action = next(a for a in decision["battle"]["actions"] if a["kind"] == "move")
            result = game.battle_action(action["action_id"], token=decision["token"])
            self.assertEqual(result["decision"]["phase"], "battle")
            game.step("session.stop", token=result["decision"]["token"])
            self.assertEqual(game.get_state(), before)
            decision = game.start_session(1)
            result = self.enter(game, decision)
            self.assertEqual(result["decision"]["battle"], original)
            self.finish(game, result)

    def test_close_during_a_battle_unwinds_the_native_arena(self):
        with self.session() as (game, _):
            decision = self.start(game)
            self.enter(game, decision)
            game.close()

    def test_enemy_castle_siege_can_be_won_and_captured(self):
        with self.session() as (game, _):
            decision = self.start(game, "siege")
            before = game.get_state()
            result = game.move_hero(52, 3, 24, token=decision["token"])
            self.assertEqual(result["decision"]["phase"], "battle")
            self.assertTrue(result["decision"]["battle"]["siege"])
            result = self.finish(game, result)
            after = game.get_state()
            castle = next(c for c in after["castles"] if c["id"] == 867)
            self.assertEqual(castle["owner"], 1)
            self.assertIn(867, self.player(after, 1)["castle_ids"])
            self.assertTrue(any(e["type"] == "battle_completed" and e["attacker_result"] & 0x80 for e in result["events"]))


if __name__ == "__main__":
    unittest.main()
