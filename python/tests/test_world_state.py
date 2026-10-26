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
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
