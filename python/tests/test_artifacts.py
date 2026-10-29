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

"""Use native, separately generated saves to verify real artifact semantics and access."""

from collections import Counter
import hashlib
from pathlib import Path
import unittest

import test_army as support

ROOT = Path(__file__).resolve().parents[2]


def slot(hero_id, index):
    return {"hero_id": hero_id, "slot": index}


class ArtifactTests(unittest.TestCase):
    session = support.ArmyTests.session
    assert_rejected = support.ArmyTests.assert_rejected
    hero = support.ArmyTests.hero

    @classmethod
    def setUpClass(cls):
        support.ArmyTests.setUpClass()
        cls.paths = [ROOT / "build/python-env-baseline/fixtures" / name for name in ("artifacts-day1.sav", "artifacts-full-day1.sav")]
        if not all(path.is_file() for path in cls.paths):
            raise unittest.SkipTest("Prepare native artifact saves; see docs/PYTHON_ENV_ARTIFACTS.md")
        cls.hashes = [hashlib.sha256(path.read_bytes()).digest() for path in cls.paths]

    @classmethod
    def tearDownClass(cls):
        for path, expected in zip(cls.paths, cls.hashes):
            if hashlib.sha256(path.read_bytes()).digest() != expected:
                raise AssertionError("An input artifact fixture was modified")

    def start(self, game, *, full=False, meet=True):
        game.load_save(self.paths[int(full)])
        decision = game.start_session(1)
        decision = game.refresh_hero_offers(896, token=decision["token"])["decision"]
        decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
        decision = game.hire_hero(896, 46, token=decision["token"])["decision"]
        if meet:
            decision = game.meet_heroes(52, 46, token=decision["token"])["decision"]
        return decision

    def items(self, state):
        return Counter((a["id"], a["spell_id"]) for h in state["heroes"] for a in h["artifacts"] if a)

    def test_transfer_preserves_scroll_and_queries_keep_meeting(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            scroll = self.hero(before)["artifacts"][3]
            self.assertGreater(scroll["spell_id"], 0)
            result = game.transfer_artifact(slot(52, 3), slot(46, 5), token=decision["token"])
            after = game.get_state()
            self.assertEqual(self.hero(after, 46)["artifacts"][5], scroll)
            self.assertIsNone(self.hero(after)["artifacts"][3])
            self.assertEqual(self.items(after), self.items(before))
            self.assertEqual(after["army_meeting"], before["army_meeting"])
            self.assertEqual(after["date"], before["date"])
            self.assertEqual(after["players"], before["players"])
            self.assertEqual(self.hero(after)["move_points"], self.hero(before)["move_points"])
            self.assertEqual(result["events"][0]["source_artifact"]["spell_id"], scroll["spell_id"])
            self.assert_rejected(game, lambda: game.transfer_artifact(slot(46, 5), slot(52, 3), token=decision["token"]), "stale_decision")
            game.render(width=64, height=64)
            self.assertEqual(game.get_state(), after)
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_telescope_and_weapon_bonuses_follow_native_artifact_ownership(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            decision = game.transfer_artifact(slot(52, 1), slot(46, 5), token=decision["token"])["decision"]
            after = game.get_state()
            self.assertLess(self.hero(after)["scouting_distance"], self.hero(before)["scouting_distance"])
            self.assertGreater(self.hero(after, 46)["scouting_distance"], self.hero(before, 46)["scouting_distance"])
            decision = game.swap_artifacts(slot(52, 2), slot(46, 1), token=decision["token"])["decision"]
            after = game.get_state()
            self.assertLess(self.hero(after)["attack"], self.hero(before)["attack"])
            self.assertGreater(self.hero(after, 46)["attack"], self.hero(before, 46)["attack"])
            self.assertEqual(self.items(after), self.items(before))

    def test_native_anduran_set_assembles_after_cross_hero_exchange(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            parts = {self.hero(before)["artifacts"][4]["id"], self.hero(before, 46)["artifacts"][2]["id"], self.hero(before, 46)["artifacts"][3]["id"]}
            result = game.transfer_artifact(slot(52, 4), slot(46, 4), token=decision["token"])
            assembled = result["events"][0]["assembled_sets"]
            self.assertEqual(len(assembled), 1)
            self.assertEqual(assembled[0]["hero_id"], 46)
            after = game.get_state()
            owned = [a for a in self.hero(after, 46)["artifacts"] if a]
            self.assertTrue(all(a["id"] not in parts for a in owned))
            self.assertTrue(any(a["id"] == assembled[0]["artifact_id"] for a in owned))
            self.assertEqual(sum(self.items(before).values()) - sum(self.items(after).values()), 2)

    def test_temporary_scout_bonus_does_not_reveal_extra_fog_before_meeting_close(self):
        with self.session() as (game, _):
            decision = self.start(game)
            before = game.get_state()
            decision = game.transfer_artifact(slot(52, 1), slot(46, 5), token=decision["token"])["decision"]
            self.assertEqual(game.get_state()["map"]["tiles"], before["map"]["tiles"])
            decision = game.transfer_artifact(slot(46, 5), slot(52, 1), token=decision["token"])["decision"]
            result = game.end_meeting(token=decision["token"])
            self.assertEqual(result["events"][0]["scouted_heroes"], [])
            self.assertEqual(game.get_state()["map"]["tiles"], before["map"]["tiles"])
            self.assertIsNone(result["decision"]["army_meeting"])
            # A retained bonus is applied once on explicit or implicit encounter close.
            decision = game.meet_heroes(52, 46, token=result["decision"]["token"])["decision"]
            decision = game.transfer_artifact(slot(52, 1), slot(46, 5), token=decision["token"])["decision"]
            result = game.end_meeting(token=decision["token"])
            self.assertEqual(result["events"][0]["scouted_heroes"], [46])
            self.assert_rejected(game, lambda: game.end_meeting(token=result["decision"]["token"]), "illegal_action")
            decision = game.meet_heroes(52, 46, token=result["decision"]["token"])["decision"]
            decision = game.transfer_artifact(slot(46, 5), slot(52, 1), token=decision["token"])["decision"]
            # Automatic finalization must roll back on a rejected action, including fog and encounter metadata.
            self.assert_rejected(game, lambda: game.trade_resources(896, 1, 64, 0xFFFFFFFF, token=decision["token"]), "illegal_action")
            before_stop = game.get_state()
            stopped = game.step("session.stop", token=decision["token"])
            self.assertEqual(stopped["state_version"], before_stop["state_version"] + 1)
            self.assertIsNone(game.get_state()["army_meeting"])
            resumed = game.start_session(1)
            self.assertEqual(resumed["events"][0]["scouted_heroes"], [52])

    def test_full_bag_rejects_transfer_but_allows_an_explicit_swap(self):
        with self.session() as (game, _):
            decision = self.start(game, full=True)
            self.assertTrue(all(self.hero(game.get_state(), 46)["artifacts"]))
            self.assert_rejected(game, lambda: game.transfer_artifact(slot(52, 1), slot(46, 1), token=decision["token"]), "illegal_action")
            before = game.get_state()
            game.swap_artifacts(slot(52, 1), slot(46, 1), token=decision["token"])
            after = game.get_state()
            self.assertEqual(self.items(after), self.items(before))
            self.assertEqual(self.hero(after, 46)["artifacts"][1], self.hero(before)["artifacts"][1])

    def test_magic_books_and_bad_slots_are_never_moved(self):
        with self.session() as (game, _):
            decision = self.start(game)
            token = decision["token"]
            for source, target in ((slot(52, 0), slot(46, 5)), (slot(52, 1), slot(46, 0)), (slot(52, 0), slot(52, 5))):
                self.assert_rejected(game, lambda: game.swap_artifacts(source, target, token=token), "illegal_action")
                self.assert_rejected(game, lambda: game.transfer_artifact(source, target, token=token), "illegal_action")
            for bad in ({}, slot(52, 14), slot(52, -1), slot(52, True), slot(True, 1), slot(1 << 40, 1), {"hero_id": 52, "slot": 1, "extra": 0}):
                self.assert_rejected(game, lambda: game.step("artifact.transfer", token=token, params={"source": bad, "target": slot(46, 5)}), "invalid_request")
            self.assert_rejected(game, lambda: game.swap_artifacts(slot(52, 1), slot(52, 1), token=token), "illegal_action")
            self.assert_rejected(game, lambda: game.transfer_artifact(slot(52, 7), slot(46, 5), token=token), "illegal_action")

    def test_remote_or_foreign_exchange_rejected_and_local_reordering_allowed(self):
        with self.session() as (game, _):
            decision = self.start(game, meet=False)
            self.assert_rejected(game, lambda: game.transfer_artifact(slot(52, 1), slot(46, 5), token=decision["token"]), "illegal_action")
            self.assert_rejected(game, lambda: game.swap_artifacts(slot(52, 1), slot(42, 1), token=decision["token"]), "illegal_action")
            before = game.get_state()
            result = game.transfer_artifact(slot(52, 1), slot(52, 7), token=decision["token"])
            after = game.get_state()
            self.assertEqual(self.hero(after)["artifacts"][7], self.hero(before)["artifacts"][1])
            self.assertEqual(self.items(after), self.items(before))
            self.assertIsNone(after["army_meeting"])
            decision = game.meet_heroes(52, 46, token=result["decision"]["token"])["decision"]
            decision = game.end_turn(token=decision["token"])["decision"]
            self.assert_rejected(game, lambda: game.transfer_artifact(slot(52, 7), slot(46, 5), token=decision["token"]), "illegal_action")


if __name__ == "__main__":
    unittest.main()
