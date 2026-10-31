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

"""Verify native sailing, harbor purchases and own-castle visits."""

import unittest

from fheroes2_env import EngineError
import test_world_state as support
import test_battle as battle_support

ROOT = support.ROOT
FIXTURES = ROOT / "build/python-env-baseline/fixtures"
PYTHON = {1: "python", 2: "python"}


class NavigationTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        for name in ("coast", "shipyard", "poor", "blocked", "battle"):
            if not (FIXTURES / f"navigation-{name}-day1.sav").is_file():
                raise unittest.SkipTest("Prepare native navigation fixtures")

    def start(self, game, profile="shipyard"):
        return game.reset(save=FIXTURES / f"navigation-{profile}-day1.sav", seed=123, controllers=PYTHON)["decision"]

    def hero(self, game):
        return next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"] == 52)

    def next_day(self, game, decision):
        decision = game.end_turn(token=decision["token"])["decision"]
        self.assertEqual(decision["player_id"], 2)
        return game.end_turn(token=decision["token"])["decision"]

    def reject(self, game, call, code="illegal_action"):
        state, decision = game.get_state(), game.get_decision()
        with self.assertRaises(EngineError) as error:
            call()
        self.assertEqual(error.exception.code, code)
        self.assertEqual(game.get_state(), state)
        self.assertEqual(game.get_decision(), decision)

    def test_buy_boat_exact_native_cost_placement_and_readonly_quotes(self):
        with self.session() as (game, directory):
            decision = self.start(game)
            before = game.get_state()
            options = game.get_castle_options(896)["boat"]
            self.assertTrue(options["can_buy"])
            self.assertEqual(options["placement_index"], 968)
            self.assertTrue(game.check_actions([{"action":"castle.buy_boat", "params":{"castle_id":896}}], token=decision["token"])[0])
            self.assertEqual(game.get_state(), before)
            result = game.buy_boat(896, token=decision["token"])
            after = game.get_state()
            for resource, cost in options["cost"].items():
                self.assertEqual(after["players"][0]["funds"][resource], before["players"][0]["funds"][resource] - cost)
            self.assertEqual(after["map"]["tiles"][968]["boat_owner"], 1)
            self.assertEqual(result["events"][0]["type"], "boat_purchased")
            self.assertFalse(game.get_castle_options(896)["boat"]["can_buy"])
            self.reject(game, lambda: game.buy_boat(896, token=result["decision"]["token"]))
            self.assertEqual(list(directory.iterdir()), [])
            self.assertFalse(game.runtime_info()["video_initialized"])
            self.assertFalse(game.runtime_info()["audio_initialized"])

    def test_purchase_rejects_missing_shipyard_money_blocked_harbor_foreign_and_bad_params(self):
        with self.session() as (game, _):
            for profile in ("coast", "poor", "blocked"):
                decision = self.start(game, profile)
                self.assertFalse(game.get_castle_options(896)["boat"]["can_buy"])
                self.reject(game, lambda: game.buy_boat(896, token=decision["token"]))
            decision = self.start(game)
            self.reject(game, lambda: game.buy_boat(867, token=decision["token"]))
            self.reject(game, lambda: game.step("castle.buy_boat", params={"castle_id":896,"count":2}, token=decision["token"]), "invalid_request")
            self.reject(game, lambda: game.step("castle.buy_boat", params={"castle_id":True}, token=decision["token"]), "invalid_request")

    def test_new_boat_immediately_updates_cached_route_for_waiting_shore_hero(self):
        with self.session() as (game,_):
            decision=self.start(game)
            decision=game.move_hero(52,32,25,token=decision["token"])["decision"]
            command={"action":"hero.move","params":{"hero_id":52,"x":32,"y":26}}
            self.assertEqual(game.check_actions([command],token=decision["token"]),[False])
            decision=game.buy_boat(896,token=decision["token"])["decision"]
            self.assertEqual(game.check_actions([command],token=decision["token"]),[True])
            game.move_hero(52,32,26,token=decision["token"])
            self.assertTrue(self.hero(game)["is_shipmaster"])

    def test_board_sail_disembark_and_reboard_preserve_native_boat_rules(self):
        with self.session() as (game, _):
            decision = self.start(game, "blocked")
            decision = game.move_hero(52,32,25, token=decision["token"])["decision"]
            result = game.move_hero(52,32,26, token=decision["token"])
            decision = result["decision"]
            self.assertTrue(self.hero(game)["is_shipmaster"])
            self.assertEqual(self.hero(game)["move_points"],0)
            self.assertEqual(self.hero(game)["position"]["index"],968)
            self.assertTrue(any(e["type"] == "hero_boarded" for e in result["events"]))
            self.assertEqual(game.get_state()["map"]["tiles"][968]["boat_owner"],0)
            self.reject(game, lambda:game.move_hero(52,32,27,token=decision["token"]))
            decision = self.next_day(game,decision)
            movement = self.hero(game)["move_points"]
            decision = game.move_hero(52,32,27,token=decision["token"])["decision"]
            self.assertTrue(self.hero(game)["is_shipmaster"])
            self.assertEqual(self.hero(game)["move_points"], movement-100)
            before = game.get_state()
            game.render(width=96,height=96,center=(32,27))
            game.render(view="hero",hero_id=52,width=96,height=96)
            self.assertEqual(game.get_state(),before)
            result = game.move_hero(52,32,25,token=decision["token"])
            decision = result["decision"]
            self.assertFalse(self.hero(game)["is_shipmaster"])
            self.assertEqual(self.hero(game)["move_points"],0)
            self.assertEqual(self.hero(game)["position"]["index"],932)
            self.assertTrue(any(e["type"] == "hero_disembarked" for e in result["events"]))
            self.assertEqual(game.get_state()["map"]["tiles"][968]["boat_owner"],1)
            decision = self.next_day(game,decision)
            game.move_hero(52,32,26,token=decision["token"])
            self.assertTrue(self.hero(game)["is_shipmaster"])

    def test_land_cannot_walk_on_empty_water_or_cross_boat_to_distant_water(self):
        with self.session() as (game, _):
            decision = self.start(game)
            state = game.get_state()
            for x,y in ((32,26),(32,27),(33,27)):
                with self.assertRaises(EngineError):
                    game.move_hero(52,x,y,token=decision["token"])
                self.assertEqual(game.get_state(),state)
            decision = self.start(game,"blocked")
            state = game.get_state()
            with self.assertRaises(EngineError):
                game.move_hero(52,32,28,token=decision["token"])
            self.assertEqual(game.get_state(),state)

    def test_own_castle_entry_restores_visitor_and_garrison_access_without_ui(self):
        with self.session() as (game, _):
            decision = self.start(game)
            decision = game.move_hero(52,32,25,token=decision["token"])["decision"]
            self.assertIsNone(self.hero(game)["castle_id"])
            result = game.move_hero(52,32,24,token=decision["token"])
            self.assertEqual(self.hero(game)["castle_id"],896)
            self.assertTrue(any(e["type"] == "castle_visited" for e in result["events"]))
            castle = next(c for c in game.get_state()["castles"] if c["id"] == 896)
            self.assertEqual(castle["visiting_hero_id"],52)
            hero_slot = next(i for i,troop in enumerate(self.hero(game)["army"]) if troop is not None and troop["count"] > 1)
            castle_slot = next(i for i,troop in enumerate(castle["garrison"]) if troop is None)
            decision = game.transfer_troops({"kind":"hero","id":52,"slot":hero_slot},
                                            {"kind":"castle","id":896,"slot":castle_slot},1,
                                            token=result["decision"]["token"])["decision"]
            castle = next(c for c in game.get_state()["castles"] if c["id"] == 896)
            self.assertEqual(castle["garrison"][castle_slot]["count"],1)
            before = game.get_state()
            game.get_army_options("castle",896)
            game.render(view="castle",castle_id=896,width=96,height=96)
            self.assertEqual(game.get_state(),before)
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_seeded_sailing_replay_and_reset_from_ship(self):
        with self.session() as (game, _):
            traces=[]
            for _ in range(2):
                decision=self.start(game,"blocked")
                trace=[]
                for x,y in ((32,25),(32,26)):
                    decision=game.move_hero(52,x,y,token=decision["token"])["decision"]
                    trace.append(game.get_state())
                decision=self.next_day(game,decision)
                game.move_hero(52,32,28,token=decision["token"])
                trace.append(game.get_state())
                traces.append(trace)
            self.assertEqual(traces[0],traces[1])

    def test_gym_boat_candidate_sailing_mask_and_ship_observation(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
            from fheroes2_env.gym_observation import HERO_FIELDS
        except ImportError:
            self.skipTest("Install the optional gym extra")
        with self.session() as (parent,_):
            with HeroesEnv(executable=support.EXECUTABLE, save=FIXTURES / "navigation-shipyard-day1.sav", env=parent._env) as env:
                obs,_ = env.reset(seed=123)
                def select(name, **params):
                    return next(i for i,c in enumerate(env._commands) if c["action"] == name and all(c["params"].get(k)==v for k,v in params.items()))
                obs,_,_,_,_ = env.step(select("castle.buy_boat",castle_id=896))
                self.assertTrue(env.observation_space.contains(obs))
                obs,_,_,_,_ = env.step(select("hero.move",hero_id=52,x=32,y=25))
                obs,_,_,_,_ = env.step(select("hero.move",hero_id=52,x=32,y=26))
                hero_index = next(i for i,row in enumerate(obs["heroes"]) if row[0]==52)
                self.assertEqual(obs["heroes"][hero_index,HERO_FIELDS.index("is_shipmaster")],1)
                self.assertTrue(env.observation_space.contains(obs))
                self.assertFalse(any(c["action"]=="hero.move" and c["params"]["hero_id"]==52 for c in env._commands))

    def test_enemy_ship_battle_returns_to_sailing_and_routes_both_sides(self):
        with self.session() as (game,_):
            decision=self.start(game,"battle")
            decision=game.move_hero(52,32,28,token=decision["token"])["decision"]
            seen=set()
            completed=False
            for _ in range(300):
                if decision["phase"] == "battle":
                    seen.add(decision["player_id"])
                    # Let the slower defender take a turn before the much stronger attacker wins.
                    action=(next(a for a in decision["battle"]["actions"] if a["kind"]=="skip") if 2 not in seen
                            else battle_support._example.select_action(decision["battle"],use_spells=True))
                    result=game.battle_action(action["action_id"],token=decision["token"])
                elif decision["phase"] == "choice":
                    choice=decision["pending_choice"]
                    result=game.answer_choice(choice["choice_id"],choice["options"][0],token=decision["token"])
                else:
                    break
                completed |= any(e["type"]=="battle_completed" for e in result["events"])
                decision=result["decision"]
            self.assertTrue(completed)
            self.assertEqual(seen,{1,2})
            self.assertTrue(self.hero(game)["active"])
            self.assertTrue(self.hero(game)["is_shipmaster"])
            self.assertEqual(decision["phase"],"adventure")


if __name__ == "__main__":
    unittest.main()
