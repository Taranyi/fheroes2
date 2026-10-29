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

"""Verify native memory rendering without world, decision, or combat-outcome changes."""

import unittest

from fheroes2_env import EngineError
import test_castle as support
import test_battle as battle_support

ROOT = support.ROOT


class ViewTests(unittest.TestCase):
    session = support.CastleTests.session
    start = support.CastleTests.start
    assert_rejected = support.CastleTests.assert_rejected

    @classmethod
    def setUpClass(cls):
        support.CastleTests.setUpClass()
        cls.fixtures = support.CastleTests.fixtures

    def assert_frame(self, frame, width, height):
        self.assertEqual(frame.shape, (height, width, 3))
        self.assertEqual(len(frame.pixels), width * height * 3)
        self.assertGreater(len(set(zip(frame.pixels[0::3], frame.pixels[1::3], frame.pixels[2::3]))), 25)

    def battle_start(self, game, name="heroes"):
        save = ROOT / f"build/python-env-baseline/fixtures/battles-{name}-day1.sav"
        if not save.is_file():
            self.skipTest("Prepare native battle fixtures")
        game.load_save(save)
        decision = game.start_session(1)
        result = game.move_hero(52, 3, 24, token=decision["token"]) if name == "siege" else game.move_hero(52, 32, 25, token=decision["token"])
        while result["decision"]["phase"] == "choice":
            decision = result["decision"]
            choice = decision["pending_choice"]
            result = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])
        self.assertEqual(result["decision"]["phase"], "battle")
        return result

    def test_all_active_hero_and_castle_views_include_ai_and_are_read_only(self):
        for fixture in range(2):
            with self.subTest(fixture=fixture), self.session() as (game, directory):
                decision, _, _ = self.start(game, fixture)
                before = game.get_state()
                requests = [("hero", {"hero_id": h["id"]}) for h in before["heroes"] if h["active"]]
                requests += [("castle", {"castle_id": c["id"]}) for c in before["castles"]]
                for view, params in requests:
                    with self.subTest(view=view, params=params):
                        frame = game.render(view=view, width=160, height=120, **params)
                        self.assert_frame(frame, 160, 120)
                        self.assertEqual(game.render(view=view, width=160, height=120, **params), frame)
                        self.assertEqual(game.get_state(), before)
                        self.assertEqual(game.get_decision(), decision)
                self.assertEqual(list(directory.iterdir()), [])
                info = game.runtime_info()
                for key in ("video_initialized", "audio_initialized", "controller_initialized", "interactive_input"):
                    self.assertFalse(info[key])

    def test_native_size_and_resize_do_not_pollute_following_views(self):
        with self.session() as (game, _):
            self.start(game)
            before = game.get_state()
            for view, params in (("hero", {"hero_id": 52}), ("castle", {"castle_id": 896})):
                small = game.render(view=view, width=96, height=72, **params)
                native = game.render(view=view, **params)
                self.assert_frame(native, 640, 480)
                self.assertEqual(game.render(view=view, width=96, height=72, **params), small)
                self.assertEqual(game.get_state(), before)

    def test_images_reflect_native_building_and_troop_upgrade(self):
        with self.session() as (game, _):
            decision, _, castle_id = self.start(game)
            castle_before = game.render(view="castle", castle_id=castle_id)
            hero_before = game.render(view="hero", hero_id=52)
            decision = game.build_castle(castle_id, 1 << 26, token=decision["token"])["decision"]
            self.assertNotEqual(game.render(view="castle", castle_id=castle_id).pixels, castle_before.pixels)
            game.upgrade_troop({"kind": "hero", "id": 52, "slot": 1}, token=decision["token"])
            self.assertNotEqual(game.render(view="hero", hero_id=52).pixels, hero_before.pixels)
            before = game.get_state()
            game.render(view="hero", hero_id=52)
            self.assertEqual(game.get_state(), before)

    def test_battle_field_and_siege_images_preserve_pending_decision(self):
        for name in ("heroes", "ranged", "boss", "siege"):
            with self.subTest(name=name), self.session() as (game, _):
                decision = self.battle_start(game, name)["decision"]
                before = game.get_state()
                frame = game.render(view="battle", width=320, height=240)
                self.assert_frame(frame, 320, 240)
                for _ in range(2):
                    self.assertEqual(game.render(view="battle", width=320, height=240), frame)
                    game.render(view="hero", hero_id=52, width=160, height=120)
                    game.render(view="castle", castle_id=896, width=160, height=120)
                    self.assertEqual(game.get_state(), before)
                    self.assertEqual(game.get_decision(), decision)
                game.step("session.stop", token=decision["token"])
                with self.assertRaises(EngineError) as failed:
                    game.render(view="battle")
                self.assertEqual(failed.exception.code, "no_active_battle")

    def test_battle_image_tracks_a_native_move(self):
        with self.session() as (game, _):
            decision = self.battle_start(game)["decision"]
            before = game.render(view="battle")
            move = next(a for a in decision["battle"]["actions"] if a["kind"] == "move")
            result = game.battle_action(move["action_id"], token=decision["token"])
            self.assertEqual(result["decision"]["phase"], "battle")
            self.assertNotEqual(game.render(view="battle").pixels, before.pixels)

    def test_rendering_does_not_change_native_combat_results(self):
        snapshots = []
        for render in (False, True):
            with self.session() as (game, _):
                result = self.battle_start(game, "melee")
                for _ in range(200):
                    decision = result["decision"]
                    if decision["phase"] == "battle":
                        if render:
                            game.render(view="battle", width=192, height=144)
                            game.render(view="hero", hero_id=52, width=96, height=72)
                            game.render(view="castle", castle_id=896, width=96, height=72)
                        action = battle_support._example.select_action(decision["battle"])
                        result = game.battle_action(action["action_id"], token=decision["token"])
                    elif decision["phase"] == "choice":
                        choice = decision["pending_choice"]
                        result = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])
                    else:
                        break
                else:
                    self.fail("Battle did not complete")
                snapshots.append(game.get_state())
        self.assertEqual(snapshots[0], snapshots[1])

    def test_new_view_validation_and_failure_recovery_are_atomic(self):
        with self.session() as (game, directory):
            decision, _, _ = self.start(game)
            base = {"view": "hero", "hero_id": 52, "width": 128, "height": 96, "output_path": str(directory / "frame.rgb")}
            for changes in ({"hero_id": True}, {"hero_id": -1}, {"hero_id": 1 << 40}, {"hero_id": 0}, {"castle_id": 896}, {"center_x": 1, "center_y": 1}):
                self.assert_rejected(game, lambda: game.request("render", dict(base, **changes)), "invalid_request")
            for castle_id in (True, -1, 1 << 40, 0xFFFFFFFF):
                params = {"view": "castle", "castle_id": castle_id, "width": 128, "height": 96, "output_path": str(directory / "frame.rgb")}
                self.assert_rejected(game, lambda: game.request("render", params), "invalid_request")
            self.assert_rejected(game, lambda: game.render(view="battle"), "no_active_battle")
            game.render(view="hero", hero_id=52)
            game.render(view="castle", castle_id=896)
            self.assertEqual(game.get_decision(), decision)
            self.assertEqual(list(directory.iterdir()), [])

    def test_client_ids_are_validated_before_sending_and_base_views_remain_usable(self):
        with self.session() as (game, _):
            self.start(game)
            before = game.get_state()
            for value in (True, -1, 1 << 40, "hero"):
                with self.assertRaises(ValueError):
                    game.render(view="hero", hero_id=value)
                with self.assertRaises(ValueError):
                    game.render(view="castle", castle_id=value)
            self.assertEqual(game.get_state(), before)
            self.assert_frame(game.render(width=128, height=96), 128, 96)


if __name__ == "__main__":
    unittest.main()
