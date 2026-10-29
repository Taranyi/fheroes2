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

"""Read the actual engine's complete state from the two recorded local saves."""

from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fheroes2_env import EngineError, HeroesSession

ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE = Path(os.environ.get("FHEROES2_TEST_EXE", ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2")))


def occupied(slots):
    return [slot for slot in slots if slot is not None]


def label(value):
    return value.lower().replace(" ", "_")


class WorldStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "docs/python_env/baseline.expected.json").read_text(encoding="utf-8"))
        cls.fixtures = cls.manifest["fixtures"]
        if not all((ROOT / fixture["path"]).is_file() for fixture in cls.fixtures):
            raise unittest.SkipTest("Local reference saves are missing; see docs/PYTHON_ENV_BASELINE.md")
        if not EXECUTABLE.is_file():
            raise RuntimeError("Build the desktop engine with ENABLE_PYTHON_ENV=ON first")

    @contextmanager
    def session(self):
        work = ROOT / "build/python-env-state-tests"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            env = dict(os.environ)
            env.pop("HOME", None)
            env.update(APPDATA=directory, FHEROES2_DATA=str(ROOT), SDL_VIDEODRIVER="nonexistent-driver", SDL_AUDIODRIVER="nonexistent-driver")
            with HeroesSession(EXECUTABLE, env=env, timeout=20) as game:
                yield game, Path(directory)

    def test_recorded_states_match_all_original_ui_values(self):
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture["id"]), self.session() as (game, _):
                path = ROOT / fixture["path"]
                before = hashlib.sha256(path.read_bytes()).hexdigest().upper()
                loaded = game.load_save(path)
                self.assertTrue(loaded["loaded"])
                self.assertEqual(loaded["map_name"], fixture["map_name"])
                state = game.get_state()
                expected = fixture["observed"]
                player = next(player for player in state["players"] if player["is_human"])
                self.assertEqual(player["funds"], expected["funds"])
                self.assertEqual(len(player["hero_ids"]), expected["own_heroes"])
                self.assertEqual(len(player["castle_ids"]), expected["own_castles"])
                for key in ("day", "week", "month"):
                    self.assertEqual(state["date"][key], expected[key])
                self.assertEqual([state["map"]["width"], state["map"]["height"]], fixture["map_size"])
                hero = next(hero for hero in state["heroes"] if hero["name"] == expected["hero"]["name"])
                self.assertIn(hero["id"], player["hero_ids"])
                for key in ("level", "experience", "attack", "defense", "power", "knowledge", "spell_points", "max_spell_points"):
                    self.assertEqual(hero[key], expected["hero"][key], key)
                self.assertEqual(
                    [{"creature": label(troop["name"]), "count": troop["count"]} for troop in occupied(hero["army"])],
                    expected["hero"]["army"],
                )
                self.assertEqual([label(artifact["name"]) for artifact in occupied(hero["artifacts"])], expected["hero"]["artifacts"])
                levels = {1: "basic", 2: "advanced", 3: "expert"}
                self.assertEqual(
                    [{"skill": label(skill["name"]), "level": levels[skill["level"]]} for skill in hero["secondary_skills"]],
                    expected["hero"]["secondary_skills"],
                )
                castle = next(castle for castle in state["castles"] if castle["name"] == expected["castle"]["name"])
                self.assertIn(castle["id"], player["castle_ids"])
                self.assertEqual(
                    [{"creature": label(troop["name"]), "count": troop["count"]} for troop in occupied(castle["garrison"])],
                    expected["castle"]["garrison"],
                )
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), before)
                self.assertEqual(before, fixture["sha256"])

    def test_ai_and_fog_hidden_state_is_exported(self):
        with self.session() as (game, directory):
            game.load_save(ROOT / self.fixtures[0]["path"])
            state = game.get_state()
            human = next(player for player in state["players"] if player["is_human"])
            opponents = [player for player in state["players"] if player["is_ai"]]
            self.assertTrue(opponents)
            self.assertEqual(state["perspective"], "omniscient")
            self.assertEqual(len(state["map"]["tiles"]), 36 * 36)
            for player in opponents:
                self.assertGreater(player["funds"]["gold"], 0)
                self.assertTrue(player["hero_ids"])
                self.assertTrue(player["castle_ids"])
                hero = next(hero for hero in state["heroes"] if hero["id"] == player["hero_ids"][0])
                self.assertEqual(hero["owner"], player["id"])
                self.assertTrue(occupied(hero["army"]))
                tile = state["map"]["tiles"][hero["position"]["index"]]
                self.assertTrue(tile["fog_colors"] & human["id"])
            self.assertEqual(list(directory.iterdir()), [])

    def test_positions_and_save_payload_are_complete_and_read_only(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            first = game.get_state()
            self.assertTrue(game.capabilities()["game_initialized"])
            game.hello()
            second = game.get_state()
            self.assertEqual(first, second)
            self.assertGreater(len(json.dumps(first)), 65536)
            payload = first["serialized_state"]
            self.assertEqual(payload["format"], "fheroes2_save_payload")
            self.assertGreater(len(bytes.fromhex(payload["data"])), 10000)
            for tile in first["map"]["tiles"]:
                self.assertEqual(tile["index"], tile["y"] * first["map"]["width"] + tile["x"])
            timberhill = next(castle for castle in first["castles"] if castle["name"] == "Timberhill")
            roxana = next(hero for hero in first["heroes"] if hero["name"] == "Roxana")
            self.assertEqual(timberhill["position"], {"index": 896, "x": 32, "y": 24})
            self.assertEqual(roxana["position"], timberhill["position"])
            self.assertEqual(roxana["castle_id"], timberhill["id"])
            self.assertEqual(timberhill["visiting_hero_id"], roxana["id"])
            compact = game.get_state(include_serialized=False)
            self.assertNotIn("serialized_state", compact)
            del first["serialized_state"]
            self.assertEqual(compact, first)

    def test_failed_load_clears_state_and_another_load_can_recover(self):
        with self.session() as (game, directory):
            with self.assertRaises(EngineError) as failed:
                game.get_state()
            self.assertEqual(failed.exception.code, "no_game_loaded")
            good = ROOT / self.fixtures[0]["path"]
            first = game.load_save(good)
            for path in (directory / "missing.sav", directory / "corrupt.sav"):
                if path.name == "corrupt.sav":
                    path.write_bytes(b"this is not a Heroes II save")
                with self.assertRaises(EngineError) as failed:
                    game.load_save(path)
                self.assertEqual(failed.exception.code, "load_failed")
                self.assertFalse(game.capabilities()["game_initialized"])
                with self.assertRaises(EngineError) as failed:
                    game.get_state()
                self.assertEqual(failed.exception.code, "no_game_loaded")
                loaded = game.load_save(good)
                self.assertGreater(loaded["state_version"], first["state_version"])
                self.assertEqual(game.get_state(include_serialized=False)["date"]["total_days"], 1)

    def test_sequential_loads_replace_world_without_advancing_it(self):
        with self.session() as (game, _):
            states = []
            for fixture in (self.fixtures[0], self.fixtures[1], self.fixtures[0]):
                game.load_save(ROOT / fixture["path"])
                states.append(game.get_state())
            self.assertEqual(states[1]["map"]["name"], "Forsaken Lands")
            self.assertEqual(states[1]["date"]["total_days"], 2)
            self.assertGreater(states[2]["state_version"], states[0]["state_version"])
            states[0].pop("state_version")
            states[2].pop("state_version")
            self.assertEqual(states[0], states[2])

    def test_two_loaded_worlds_are_independent(self):
        with self.session() as (first, _), self.session() as (second, _):
            first.load_save(ROOT / self.fixtures[0]["path"])
            second.load_save(ROOT / self.fixtures[1]["path"])
            self.assertEqual(first.get_state(include_serialized=False)["map"]["width"], 36)
            self.assertEqual(second.get_state(include_serialized=False)["map"]["width"], 72)
            first.close()
            self.assertEqual(second.get_state(include_serialized=False)["date"]["total_days"], 2)

    def test_method_params_are_validated_without_mutating_loaded_world(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            for method, params in (("load_save", {}), ("load_save", {"path": 123}), ("get_state", {"include_serialized": 1}), ("get_state", {"player": 1})):
                with self.assertRaises(EngineError) as failed:
                    game.request(method, params)
                self.assertEqual(failed.exception.code, "invalid_request")
            self.assertEqual(game.get_state(), before)

    def test_controller_waits_at_real_loaded_human_turn_without_changing_world(self):
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture["id"]), self.session() as (game, directory):
                game.load_save(ROOT / fixture["path"])
                before = game.get_state()
                human = next(player for player in before["players"] if player["is_human"])
                decision = game.start_session(human["id"])
                self.assertTrue(decision["waiting"])
                self.assertEqual(decision["player_id"], human["id"])
                self.assertEqual(decision["phase"], "adventure")
                self.assertEqual(decision["controller"], "external")
                self.assertEqual(decision["token"]["state_version"], before["state_version"])
                self.assertEqual(decision["turn_order"], [player["id"] for player in sorted(before["players"], key=lambda p: (not p["is_human"], p["id"]))])
                self.assertEqual(decision["available_actions"], ["session.stop", "hero.move", "turn.end", "castle.build", "castle.recruit", "castle.refresh_heroes", "castle.hire", "market.trade"])
                self.assertIsNone(decision["pending_choice"])
                self.assertEqual(decision["notifications"][0]["type"], "decision_required")
                for _ in range(3):
                    self.assertEqual(game.get_decision(), decision)
                    self.assertEqual(game.get_state(), before)
                    self.assertTrue(game.capabilities()["controller_active"])
                    self.assertTrue(game.capabilities()["gameplay_actions"])
                self.assertTrue(game.step("session.stop", token=decision["token"])["stopped"])
                self.assertFalse(game.capabilities()["controller_active"])
                with self.assertRaises(EngineError) as failed:
                    game.get_decision()
                self.assertEqual(failed.exception.code, "no_active_session")
                self.assertEqual(game.get_state(), before)
                self.assertEqual(list(directory.iterdir()), [])

    def test_controller_requires_loaded_human_and_valid_parameters(self):
        with self.session() as (game, _):
            with self.assertRaises(EngineError) as failed:
                game.start_session(1)
            self.assertEqual(failed.exception.code, "no_game_loaded")
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            for player in (2, 4, 8, 16, 32):
                with self.assertRaises(EngineError) as failed:
                    game.start_session(player)
                self.assertEqual(failed.exception.code, "wrong_player")
            for params in ({}, {"player_id": True}, {"player_id": -1}, {"player_id": 0}, {"player_id": 3}, {"player_id": "1"}, {"player_id": 1, "extra": 1}):
                with self.assertRaises(EngineError) as failed:
                    game.request("start_session", params)
                self.assertEqual(failed.exception.code, "invalid_request")
            for value in (True, -1, 0, 3, "1"):
                with self.assertRaises(ValueError):
                    game.start_session(value)
            self.assertFalse(game.capabilities()["controller_active"])
            self.assertEqual(game.get_state(), before)

    def test_command_tokens_reject_wrong_player_session_and_stale_identifiers(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            decision = game.start_session(1)
            token = decision["token"]
            for field, value, code in (
                ("player_id", 2, "wrong_player"),
                ("session_id", "another-process", "wrong_session"),
                ("episode_id", token["episode_id"] + 1, "stale_decision"),
                ("state_version", token["state_version"] + 1, "stale_decision"),
                ("decision_id", token["decision_id"] + 1, "stale_decision"),
                ("decision_id", True, "invalid_request"),
            ):
                with self.subTest(field=field), self.assertRaises(EngineError) as failed:
                    game.step("session.stop", token={**token, field: value})
                self.assertEqual(failed.exception.code, code)
                self.assertEqual(game.get_decision(), decision)
            self.assertEqual(game.get_state(), before)
            game.step("session.stop", token=token)
            next_decision = game.start_session(1)
            self.assertGreater(next_decision["token"]["decision_id"], token["decision_id"])
            with self.assertRaises(EngineError) as failed:
                game.step("session.stop", token=token)
            self.assertEqual(failed.exception.code, "stale_decision")
            game.step("session.stop", token=next_decision["token"])
            game.load_save(ROOT / self.fixtures[0]["path"])
            final = game.start_session(1)
            with self.assertRaises(EngineError) as failed:
                game.step("session.stop", token=next_decision["token"])
            self.assertEqual(failed.exception.code, "stale_decision")
            game.step("session.stop", token=final["token"])

    def test_unsupported_or_malformed_actions_preserve_pending_decision(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            decision = game.start_session(1)
            for action in ("castle.buy_boat", "battle.attack", "choice.answer", "unknown"):
                with self.assertRaises(EngineError) as failed:
                    game.step(action, token=decision["token"])
                self.assertEqual(failed.exception.code, "unsupported_action")
            for params in ({}, {"action": "session.stop", "token": {}, "params": {}}, {"action": "session.stop", "token": decision["token"], "params": {"extra": 1}}):
                with self.assertRaises(EngineError) as failed:
                    game.request("step", params)
                self.assertEqual(failed.exception.code, "invalid_request")
            self.assertEqual(game.get_decision(), decision)
            self.assertEqual(game.get_state(), before)
            game.step("session.stop", token=decision["token"])

    def test_active_controller_blocks_reload_and_reentry_and_close_unwinds(self):
        with self.session() as (game, _):
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            decision = game.start_session(1)
            for method, params in (("start_session", {"player_id": 1}), ("load_save", {"path": str(ROOT / self.fixtures[1]["path"])})):
                with self.assertRaises(EngineError) as failed:
                    game.request(method, params)
                self.assertEqual(failed.exception.code, "session_active")
            self.assertEqual(game.get_decision(), decision)
            self.assertEqual(game.get_state(), before)
            game.close()
            self.assertEqual(game.returncode, 0)

    def test_decision_tokens_are_isolated_between_loaded_processes(self):
        with self.session() as (first, _), self.session() as (second, _):
            for game in (first, second):
                game.load_save(ROOT / self.fixtures[0]["path"])
            first_decision = first.start_session(1)
            second_decision = second.start_session(1)
            self.assertNotEqual(first_decision["token"]["session_id"], second_decision["token"]["session_id"])
            with self.assertRaises(EngineError) as failed:
                second.step("session.stop", token=first_decision["token"])
            self.assertEqual(failed.exception.code, "wrong_session")
            first.close()
            self.assertEqual(second.get_decision(), second_decision)
            second.step("session.stop", token=second_decision["token"])

    def test_eof_and_malformed_input_inside_engine_decision_wait(self):
        def request(method, request_id, params):
            return json.dumps({"api_version": 1, "id": request_id, "method": method, "params": params}).encode() + b"\n"

        payload = (
            request("load_save", 1, {"path": str(ROOT / self.fixtures[0]["path"])})
            + request("start_session", 2, {"player_id": 1})
            + b"not json\n"
            + request("get_decision", 3, {})
            + request("get_state", 4, {"include_serialized": False})
        )
        result = subprocess.run([str(EXECUTABLE), "--python-env"], input=payload, capture_output=True, timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([reply["id"] for reply in replies], [1, 2, None, 3, 4])
        self.assertEqual(replies[2]["error"]["code"], "invalid_request")
        self.assertEqual(replies[1]["result"], replies[3]["result"])
        self.assertEqual(replies[4]["result"]["date"]["total_days"], 1)

    def test_headless_render_preserves_world_and_never_initializes_presentation(self):
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture["id"]), self.session() as (game, directory):
                info = game.runtime_info()
                self.assertTrue(info["headless"])
                self.assertFalse(info["video_initialized"])
                self.assertFalse(info["audio_initialized"])
                self.assertFalse(info["controller_initialized"])
                game.load_save(ROOT / fixture["path"])
                before = game.get_state()
                human = next(player for player in before["players"] if player["is_human"])
                decision = game.start_session(human["id"])
                frames = [game.render(width=192, height=160) for _ in range(3)]
                self.assertEqual(frames[0], frames[1])
                self.assertEqual(frames[1], frames[2])
                self.assertEqual(frames[0].shape, (160, 192, 3))
                self.assertEqual(len(frames[0].pixels), 192 * 160 * 3)
                self.assertGreater(len(set(frames[0].pixels)), 20)
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)
                self.assertEqual(game.runtime_info(), info)
                game.step("session.stop", token=decision["token"])
                self.assertEqual(list(directory.iterdir()), [])

    def test_headless_render_sizes_camera_and_independent_processes(self):
        with self.session() as (first, _), self.session() as (second, _):
            first.load_save(ROOT / self.fixtures[0]["path"])
            second.load_save(ROOT / self.fixtures[1]["path"])
            castle = first.render(width=320, height=256, center=(32, 24))
            corner = first.render(width=320, height=256, center=(0, 0))
            self.assertNotEqual(castle.pixels, corner.pixels)
            self.assertEqual(castle.center, (32, 24))
            tiny = first.render(width=32, height=32, center=(35, 35))
            self.assertEqual(tiny.shape, (32, 32, 3))
            large = second.render(width=1024, height=1024, center=(71, 71))
            self.assertEqual(len(large.pixels), 1024 * 1024 * 3)
            reference = second.render(width=320, height=256, center=(32, 24))
            self.assertNotEqual(castle.pixels, reference.pixels)
            first.close()
            self.assertEqual(second.render(width=320, height=256, center=(32, 24)), reference)

    def test_invalid_render_requests_preserve_loaded_state_and_pending_decision(self):
        with self.session() as (game, directory):
            with self.assertRaises(EngineError) as failed:
                game.render()
            self.assertEqual(failed.exception.code, "no_game_loaded")
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            decision = game.start_session(1)
            params = {"view": "adventure", "width": 192, "height": 160, "output_path": str(directory / "frame.rgb")}
            for change, code in (
                ({"view": "battle"}, "unsupported_view"),
                ({"view": "castle"}, "unsupported_view"),
                ({"view": "hero"}, "unsupported_view"),
                ({"width": True}, "invalid_request"),
                ({"width": -1}, "invalid_request"),
                ({"width": 1025}, "invalid_request"),
                ({"center_x": 36, "center_y": 0}, "invalid_request"),
                ({"center_x": 0}, "invalid_request"),
                ({"extra": 1}, "invalid_request"),
                ({"output_path": "bad\0path"}, "invalid_path"),
            ):
                with self.subTest(change=change), self.assertRaises(EngineError) as failed:
                    game.request("render", {**params, **change})
                self.assertEqual(failed.exception.code, code)
            self.assertEqual(list(directory.iterdir()), [])
            self.assertEqual(game.get_state(), before)
            self.assertEqual(game.get_decision(), decision)
            game.render(width=64, height=64)

    def test_render_output_failures_do_not_overwrite_existing_files_and_can_recover(self):
        with self.session() as (game, directory):
            game.load_save(ROOT / self.fixtures[0]["path"])
            before = game.get_state()
            existing = directory / "existing.rgb"
            existing.write_bytes(b"preserve this file")
            for path in (existing, directory / "missing" / "frame.rgb"):
                with self.assertRaises(EngineError) as failed:
                    game.request("render", {"view": "adventure", "width": 64, "height": 64, "output_path": str(path)})
                self.assertEqual(failed.exception.code, "render_failed")
            self.assertEqual(existing.read_bytes(), b"preserve this file")
            self.assertEqual(game.get_state(), before)
            game.render(width=64, height=64)

    def test_render_temporary_files_are_cleaned_on_success_and_rejection(self):
        with self.session() as (game, directory):
            game.load_save(ROOT / self.fixtures[0]["path"])
            temporary_directory = tempfile.TemporaryDirectory
            paths = []

            def create_frame_directory(**kwargs):
                result = temporary_directory(dir=directory, **kwargs)
                paths.append(Path(result.name))
                return result

            with mock.patch("fheroes2_env.session.tempfile.TemporaryDirectory", side_effect=create_frame_directory):
                frame = game.render(width=64, height=64)
                with self.assertRaises(EngineError):
                    game.render(view="battle")
                another = game.render(width=64, height=64)
            self.assertEqual(frame, another)
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(not path.exists() for path in paths))
            image = directory / "frame.ppm"
            frame.save_ppm(image)
            self.assertEqual(image.read_bytes(), b"P6\n64 64\n255\n" + frame.pixels)

    def test_render_client_validates_geometry_before_sending_request(self):
        with self.session() as (game, _):
            for kwargs in ({"width": True}, {"height": 0}, {"width": 1025}, {"center": (0,)}, {"center": (-1, 0)}, {"center": (True, 0)}):
                with self.assertRaises(ValueError):
                    game.render(**kwargs)
            self.assertFalse(game.capabilities()["game_initialized"])
            self.assertTrue(game.capabilities()["render"])

    @unittest.skipUnless(os.name == "nt", "This missing-asset fixture isolates the Windows runtime layout")
    def test_render_reports_missing_graphics_package_without_crashing(self):
        with self.session() as (_, directory):
            isolated = directory / "isolated"
            (isolated / "DATA").mkdir(parents=True)
            executable = isolated / EXECUTABLE.name
            shutil.copy2(EXECUTABLE, executable)
            if os.name == "nt":
                for library in EXECUTABLE.parent.glob("*.dll"):
                    shutil.copy2(library, isolated / library.name)
            for asset in ("HEROES2.AGG", "HEROES2X.AGG"):
                source = ROOT / "DATA" / asset
                if source.is_file():
                    os.link(source, isolated / "DATA" / asset)
            env = dict(os.environ)
            env.pop("HOME", None)
            env.update(APPDATA=str(directory / "profile"), FHEROES2_DATA=str(isolated), SDL_VIDEODRIVER="nonexistent-driver", SDL_AUDIODRIVER="nonexistent-driver")
            with HeroesSession(executable, env=env, cwd=isolated, timeout=20) as game:
                game.load_save(ROOT / self.fixtures[0]["path"])
                before = game.get_state()
                with self.assertRaises(EngineError) as failed:
                    game.render(width=64, height=64)
                self.assertEqual(failed.exception.code, "assets_unavailable")
                self.assertEqual(game.get_state(), before)
                self.assertFalse(game.runtime_info()["video_initialized"])


if __name__ == "__main__":
    unittest.main()
