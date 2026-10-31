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

"""Native configurable battles without loading any adventure map or fixture save."""

from copy import deepcopy
import unittest

from fheroes2_env import EngineError
import test_world_state as support
import test_battle as battle_support


def configuration(*, controllers=("python", "builtin_ai"), heroes=True):
    result = {"terrain": "grass", "max_rounds": 100,
              "attacker": {"army": [{"monster_id": 3, "count": 20}], "controller": controllers[0]},
              "defender": {"army": [{"monster_id": 1, "count": 10}], "controller": controllers[1]}}
    if heroes:
        result["attacker"]["hero"] = {"attack": 4, "defense": 3, "power": 5, "knowledge": 5,
                                       "spell_points": 50, "spells": [15, 11]}
        result["defender"]["hero"] = {"defense": 2, "spell_points": 0}
    return result


class StandaloneTests(unittest.TestCase):
    session = support.WorldStateTests.session

    def finish(self, game, decision, *, passive=False):
        for _ in range(1000):
            if decision["phase"] == "terminal":
                return game.get_state(include_serialized=False)
            self.assertEqual(decision["phase"], "battle")
            actions = decision["battle"]["actions"]
            action = next(a for a in actions if a["kind"] == "skip") if passive else battle_support._example.select_action(decision["battle"], use_spells=True)
            decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
        self.fail("Standalone policy exceeded its action budget")

    def reject(self, game, call, code):
        state, decision = game.get_state(), game.get_decision()
        with self.assertRaises(EngineError) as error:
            call()
        self.assertEqual(error.exception.code, code)
        self.assertEqual(game.get_state(), state)
        self.assertEqual(game.get_decision(), decision)

    def test_direct_start_without_map_uses_configured_native_armies_heroes_and_result(self):
        with self.session() as (game, _):
            result = game.reset(battle_config=configuration(), seed=123)
            self.assertEqual(result["source"], "battle")
            decision = result["decision"]
            self.assertEqual(decision["phase"], "battle")
            state = game.get_state(include_serialized=False)
            self.assertEqual((state["map"]["width"], state["map"]["height"]), (2, 2))
            self.assertTrue(state["standalone_battle"]["internal_battle_context"])
            hero = next(h for h in state["heroes"] if h["id"] == 1)
            self.assertEqual((hero["attack"], hero["defense"], hero["power"], hero["knowledge"]), (4, 3, 5, 5))
            self.assertEqual(hero["spell_points"], 50)
            self.assertTrue(any(a["kind"] == "spell" for a in decision["battle"]["actions"]))
            self.assertEqual(sorted((u["monster_id"], u["count"]) for u in decision["battle"]["units"]), [(1, 10), (3, 20)])
            state = self.finish(game, decision)
            result = state["standalone_battle"]["result"]
            self.assertEqual(result["winner_player_id"], 1)
            self.assertFalse(result["truncated"])
            self.assertGreater(result["attacker_experience"], 0)
            self.assertEqual(state["phase"], "terminal")
            self.assertEqual(state["game_result"], 1)
            self.assertEqual(state["battle"]["actions"], [])
            self.assertTrue(all(t is None for t in state["standalone_battle"]["sides"][1]["army"]))
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_python_participants_route_both_sides_without_rewriting_rule_profiles(self):
        with self.session() as (game, _):
            config = configuration(controllers=("python", "python"), heroes=False)
            config["attacker"]["rule_profile"] = "ai"
            config["defender"]["rule_profile"] = "human"
            decision = game.reset(battle_config=config, seed=77)["decision"]
            seen = set()
            for _ in range(20):
                seen.add(decision["player_id"])
                decision = game.battle_action(0, token=decision["token"])["decision"]
                if seen == {1, 2}:
                    break
            self.assertEqual(seen, {1, 2})
            players = game.get_state(include_serialized=False)["players"]
            self.assertTrue(next(p for p in players if p["id"] == 1)["is_ai"])
            self.assertTrue(next(p for p in players if p["id"] == 2)["is_human"])

    def test_all_native_ai_battle_and_terminal_image_require_no_manual_participant(self):
        with self.session() as (game, _):
            config = configuration(controllers=("builtin_ai", "builtin_ai"), heroes=False)
            config.update(terrain="water", capture_final_frame=True)
            decision = game.reset(battle_config=config, seed=3)["decision"]
            self.assertEqual(decision["phase"], "terminal")
            state = game.get_state()
            self.assertEqual(state["standalone_battle"]["result"]["winner_player_id"], 1)
            frame = game.render(view="battle", width=192, height=144)
            self.assertEqual(len(frame.pixels), 192 * 144 * 3)
            self.assertEqual(game.get_state(), state)
            self.assertFalse(game.runtime_info()["audio_initialized"])
            self.assertTrue(all(p["is_ai"] for p in state["players"]))

    def test_all_nine_terrains_support_native_battle_render_without_map_assets(self):
        with self.session() as (game, _):
            images = []
            for terrain in ("grass", "snow", "swamp", "lava", "desert", "dirt", "wasteland", "beach", "water"):
                config = configuration(controllers=("python", "python"))
                config["terrain"] = terrain
                decision = game.reset(battle_config=config, seed=8)["decision"]
                before = game.get_state()
                frame = game.render(view="battle", width=192, height=144)
                images.append(frame.pixels)
                self.assertEqual(game.get_state(), before)
                self.assertEqual(game.get_decision(), decision)
            self.assertEqual(len(set(images)), 9)

    def test_sieges_of_all_races_use_native_walls_towers_and_earthquake_candidates(self):
        with self.session() as (game, _):
            for race in ("knight", "barbarian", "sorceress", "warlock", "wizard", "necromancer"):
                config = configuration(controllers=("python", "python"))
                config["attacker"]["hero"]["spells"] = [48]
                config["siege"] = {"race": race, "fortification": race == "knight"}
                decision = game.reset(battle_config=config, seed=33)["decision"]
                self.assertTrue(decision["battle"]["siege"])
                earthquake = next(a for a in decision["battle"]["actions"] if a["kind"] == "spell" and a["spell_id"] == 48)
                walls = sum(cell["object"] for cell in decision["battle"]["board"])
                mana = decision["battle"]["attacker_commander"]["spell_points"]
                decision = game.battle_action(earthquake["action_id"], token=decision["token"])["decision"]
                self.assertLess(sum(cell["object"] for cell in decision["battle"]["board"]), walls)
                self.assertEqual(decision["battle"]["attacker_commander"]["spell_points"], mana - earthquake["spell_points"])
                game.render(view="battle", width=192, height=144)
                self.finish(game, decision)

    def test_castle_captain_and_heroless_forces_keep_native_commanders(self):
        with self.session() as (game, _):
            config = configuration(controllers=("python", "python"), heroes=False)
            config["attacker"]["hero"] = {"power": 5, "spells": [48], "spell_points": 100}
            config["siege"] = {"race": "wizard", "captain": True, "left_turret": False, "right_turret": False, "moat": False}
            decision = game.reset(battle_config=config, seed=4)["decision"]
            self.assertIsNotNone(decision["battle"]["defender_commander"])
            self.finish(game, decision)

    def test_round_limit_is_truncation_and_does_not_report_a_winner(self):
        with self.session() as (game, _):
            config = configuration(controllers=("python", "python"))
            config.update(max_rounds=2, capture_final_frame=True)
            decision = game.reset(battle_config=config, seed=9)["decision"]
            state = self.finish(game, decision, passive=True)
            result = state["standalone_battle"]["result"]
            self.assertEqual((result["truncated"], result["reason"], result["rounds"], result["winner_player_id"]), (True, "round_limit", 2, 0))
            self.assertTrue(all(any(t for t in side["army"]) for side in state["standalone_battle"]["sides"]))
            game.render(view="battle", width=192, height=144)

    def test_invalid_commands_tokens_queries_and_source_changes_are_atomic(self):
        with self.session() as (game, _):
            decision = game.reset(battle_config=configuration(), seed=12)["decision"]
            wrong = dict(decision["token"], player_id=2)
            self.reject(game, lambda: game.battle_action(0, token=wrong), "wrong_player")
            self.reject(game, lambda: game.battle_action(99999, token=decision["token"]), "illegal_action")
            self.reject(game, lambda: game.step("hero.move", token=decision["token"], params={"hero_id": 1, "x": 1, "y": 0}), "battle_action_required")
            self.reject(game, lambda: game.configure_battle(configuration(), seed=1), "session_active")
            self.reject(game, lambda: game.render(view="adventure"), "unsupported_view")
            stale = decision["token"]
            game.battle_action(0, token=stale)
            self.reject(game, lambda: game.battle_action(0, token=stale), "stale_decision")

    def test_config_validation_rejects_unknown_random_and_incompatible_cases_without_replacing_world(self):
        with self.session() as (game, _):
            config = configuration()
            decision = game.configure_battle(config, seed=12)["decision"]
            game.step("session.stop", token=decision["token"])
            before = game.get_state()
            invalid = []
            for path, value in ((["terrain"], "moon"), (["max_rounds"], True), (["max_rounds"], 0),
                                (["attacker", "army"], []), (["attacker", "army"], [None]),
                                (["attacker", "army", 0, "count"], 0), (["attacker", "army", 0, "count"], 100001),
                                (["attacker", "army", 0, "monster_id"], 67), (["attacker", "controller"], "manual"),
                                (["defender", "hero", "id"], 1), (["attacker", "hero", "spells"], [49]),
                                (["attacker", "hero", "skills"], [{"id": 7, "level": 4}]),
                                (["attacker", "hero", "artifacts"], [{"id": 82}]), (["unknown"], 1)):
                bad = deepcopy(config)
                target = bad
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                invalid.append(bad)
            invalid.append(dict(config, terrain="water", siege={}))
            invalid.append(dict(config, siege={"race": "wizard", "fortification": True}))
            for bad in invalid:
                with self.subTest(config=bad), self.assertRaises(EngineError) as error:
                    game.configure_battle(bad, seed=7)
                self.assertEqual(error.exception.code, "invalid_request")
                self.assertEqual(game.get_state(), before)

    def test_stop_restores_initial_setup_and_reset_replays_a_fresh_seeded_battle(self):
        with self.session() as (game, _):
            config = configuration(controllers=("python", "python"))
            ready = game.configure_battle(config, seed=121)
            before = game.get_state()
            decision = game.step("battle.start", token=ready["decision"]["token"])["decision"]
            spell = next(a for a in decision["battle"]["actions"] if a["kind"] == "spell")
            decision = game.battle_action(spell["action_id"], token=decision["token"])["decision"]
            game.step("session.stop", token=decision["token"])
            self.assertEqual(game.get_state(), before)
            traces = []
            for _ in range(2):
                decision = game.reset(battle_config=config, seed=121)["decision"]
                traces.append(self.finish(game, decision))
            self.assertEqual(traces[0], traces[1])
            game.close()
            self.assertEqual(game.reset(seed=121)["decision"]["phase"], "battle")

    def test_skills_artifacts_spells_and_slot_formation_are_configured_exactly(self):
        with self.session() as (game, _):
            config = configuration()
            config["attacker"]["army"] = [None, {"monster_id": 3, "count": 20}, None, {"monster_id": 1, "count": 5}]
            config["attacker"]["formation"] = "grouped"
            config["attacker"]["hero"]["skills"] = [{"id": 2, "level": 3}]
            config["attacker"]["hero"]["artifacts"] = [{"id": 65}]
            game.reset(battle_config=config, seed=1)
            state = game.get_state(include_serialized=False)
            hero = next(h for h in state["heroes"] if h["id"] == 1)
            self.assertTrue(any(a and a["id"] == 65 for a in hero["artifacts"]))
            self.assertTrue(any(s and s["id"] == 2 and s["level"] == 3 for s in hero["secondary_skills"]))
            self.assertIsNone(state["standalone_battle"]["sides"][0]["army"][0])
            own = [u for u in state["battle"]["units"] if u["army_color"] == 1]
            self.assertEqual(sorted(u["head"] for u in own), [33, 55])

    def test_native_retreat_and_surrender_preserve_funds_and_result_flags(self):
        with self.session() as (game, _):
            for kind in ("retreat", "surrender"):
                config = configuration(controllers=("python", "python"))
                config["attacker"]["gold"] = 100000
                decision = game.reset(battle_config=config, seed=12)["decision"]
                command = next(a for a in decision["battle"]["actions"] if a["kind"] == kind)
                before = game.get_state(include_serialized=False)
                game.battle_action(command["action_id"], token=decision["token"])
                after = game.get_state(include_serialized=False)
                self.assertEqual(after["standalone_battle"]["result"]["winner_player_id"], 2)
                self.assertEqual(after["game_result"], 0x100)
                cost = command.get("gold", 0)
                self.assertEqual(after["players"][0]["funds"]["gold"], before["players"][0]["funds"]["gold"] - cost)
                self.assertEqual(after["players"][1]["funds"]["gold"], before["players"][1]["funds"]["gold"] + cost)

    def test_ai_only_round_limit_returns_bounded_native_progress(self):
        with self.session() as (game, _):
            config = configuration(controllers=("builtin_ai", "builtin_ai"), heroes=False)
            config["max_rounds"] = 1
            config["attacker"]["army"] = [{"monster_id": 1, "count": 10000}]
            config["defender"]["army"] = [{"monster_id": 1, "count": 10000}]
            decision = game.reset(battle_config=config, seed=3)["decision"]
            self.assertEqual(decision["phase"], "terminal")
            result = game.get_state(include_serialized=False)["standalone_battle"]["result"]
            self.assertTrue(result["truncated"])
            self.assertEqual(result["rounds"], 1)

    def test_gym_checker_defending_agent_and_configuration_reset_options(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
            from gymnasium.utils.env_checker import check_env
        except ImportError:
            self.skipTest("Install optional gym extra")
        with self.session() as (parent, _):
            with HeroesEnv(executable=support.EXECUTABLE, battle_config=configuration(), env=parent._env) as env:
                check_env(env, skip_render_check=True)
                config = configuration(controllers=("builtin_ai", "python"), heroes=False)
                config["attacker"]["army"], config["defender"]["army"] = config["defender"]["army"], config["attacker"]["army"]
                obs, info = env.reset(seed=33, options={"battle_config": config})
                self.assertEqual(info["player_id"], 2)
                for _ in range(100):
                    chosen = battle_support._example.select_action(env._decision["battle"], use_spells=True)
                    index = next(i for i, c in enumerate(env._commands) if c["params"]["action_id"] == chosen["action_id"])
                    obs, reward, terminated, truncated, info = env.step(index)
                    if terminated or truncated:
                        break
                self.assertEqual((reward, terminated, truncated), (1.0, True, False))
                self.assertTrue(env.observation_space.contains(obs))
                for controllers in (("python", "python"), ("builtin_ai", "builtin_ai")):
                    with self.assertRaises(ValueError):
                        env.reset(options={"battle_config": configuration(controllers=controllers)})

    def test_gym_standalone_loop_reward_reset_render_and_native_truncation(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
        except ImportError:
            self.skipTest("Install optional gym extra")
        with self.session() as (parent, _):
            with HeroesEnv(executable=support.EXECUTABLE, battle_config=configuration(), env=parent._env,
                           render_mode="rgb_array", width=192, height=144) as env:
                obs, info = env.reset(seed=123)
                self.assertTrue(env.observation_space.contains(obs))
                for _ in range(100):
                    selected = battle_support._example.select_action(env._decision["battle"], use_spells=True)
                    index = next(i for i, c in enumerate(env._commands) if c["params"]["action_id"] == selected["action_id"])
                    obs, reward, terminated, truncated, info = env.step(index)
                    if terminated or truncated:
                        break
                self.assertEqual((reward, terminated, truncated), (1.0, True, False))
                self.assertEqual(env.render().shape, (144, 192, 3))
                self.assertTrue(env.observation_space.contains(obs))
                env.reset(seed=123)
            config = configuration()
            config["max_rounds"] = 1
            with HeroesEnv(executable=support.EXECUTABLE, battle_config=config, env=parent._env) as env:
                env.reset(seed=123)
                for _ in range(30):
                    action = next(i for i, c in enumerate(env._commands) if env._decision["battle"]["actions"][c["params"]["action_id"]]["kind"] == "skip")
                    obs, reward, terminated, truncated, _ = env.step(action)
                    if terminated or truncated:
                        break
                self.assertEqual((reward, terminated, truncated), (0.0, False, True))
                self.assertTrue(env.observation_space.contains(obs))


if __name__ == "__main__":
    unittest.main()
