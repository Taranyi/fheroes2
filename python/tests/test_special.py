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

"""Native special objects, free text, information views and local market sessions."""

import json
import unittest
from copy import deepcopy

from fheroes2_env import EngineError
import test_world_state as support
import test_battle as battle_support

ROOT=support.ROOT
FIXTURES=ROOT / "build/python-env-baseline/fixtures"
CONTROLLERS={1:"python",2:"python"}


class SpecialTests(unittest.TestCase):
    session=support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        path=FIXTURES / "special-objects.json"
        if not path.is_file():
            raise unittest.SkipTest("Prepare native special fixtures")
        cls.records=json.loads(path.read_text())

    def record(self,name):
        return next(r for r in self.records if r["name"]==name)

    def start(self,game,name):
        return game.reset(save=FIXTURES / self.record(name)["save"],seed=123,controllers=CONTROLLERS)["decision"]

    def hero(self,game):
        return next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"]==52)

    def move(self,game,decision,name):
        index=self.record(name)["target_index"]
        if self.hero(game)["active"] and self.hero(game)["position"]["index"]==index:
            decision=game.move_hero(52,index%36,index//36+1,token=decision["token"])["decision"]
        return game.move_hero(52,index%36,index//36,token=decision["token"])

    def finish(self,game,result):
        for _ in range(600):
            decision=result["decision"]
            if decision["phase"]=="choice":
                choice=decision["pending_choice"]
                if choice.get("input_type")=="text":
                    result=game.answer_text(choice["choice_id"],"human",token=decision["token"])
                else:
                    result=game.answer_choice(choice["choice_id"],choice["options"][0] if choice["options"] else choice["minimum"],token=decision["token"])
            elif decision["phase"]=="battle":
                action=battle_support._example.select_action(decision["battle"],use_spells=True)
                result=game.battle_action(action["action_id"],token=decision["token"])
            else:
                return result
        self.fail("Special interaction exceeded its decision budget")

    def reject(self,game,call,code):
        before,decision=game.get_state(),game.get_decision()
        with self.assertRaises(EngineError) as error:
            call()
        self.assertEqual(error.exception.code,code)
        self.assertEqual(game.get_state(),before)
        self.assertEqual(game.get_decision(),decision)

    def sphinx_text(self,game,decision):
        result=self.move(game,decision,"Sphinx")
        choice=result["decision"]["pending_choice"]
        return game.answer_choice(choice["choice_id"],choice["options"][0],token=result["decision"]["token"])

    def test_sphinx_correct_free_text_reward_and_global_once_semantics(self):
        with self.session() as (game,_):
            decision=self.start(game,"Sphinx")
            before=game.get_state()
            result=self.sphinx_text(game,decision)
            decision=result["decision"]
            choice=decision["pending_choice"]
            self.assertEqual(choice["kind"],"sphinx.answer")
            self.assertIn("four legs",choice["prompt"])
            self.assertNotIn("answers",choice)
            self.reject(game,lambda:game.answer_choice(choice["choice_id"],1,token=decision["token"]),"choice_required")
            self.reject(game,lambda:game.step("choice.answer_text",token=decision["token"],params={"choice_id":choice["choice_id"],"text":5}),"invalid_request")
            stale=dict(decision["token"]);stale["player_id"]=2
            self.reject(game,lambda:game.answer_text(choice["choice_id"],"human",token=stale),"wrong_player")
            result=game.answer_text(choice["choice_id"],"human",token=decision["token"])
            after=game.get_state()
            self.assertEqual(after["players"][0]["funds"]["gold"],before["players"][0]["funds"]["gold"]+1234)
            self.assertTrue(self.hero(game)["active"])
            self.assertTrue(any(a and a["id"]==65 for a in self.hero(game)["artifacts"]))
            result=self.move(game,result["decision"],"Sphinx")
            self.assertNotEqual(result["decision"]["phase"],"choice")
            self.assertEqual(game.get_state()["players"][0]["funds"]["gold"],after["players"][0]["funds"]["gold"])

    def test_sphinx_wrong_answer_kills_hero_and_decline_keeps_reward(self):
        with self.session() as (game,_):
            decision=self.start(game,"Sphinx")
            funds=game.get_state()["players"][0]["funds"]
            result=self.move(game,decision,"Sphinx")
            choice=result["decision"]["pending_choice"]
            decision=game.answer_choice(choice["choice_id"],choice["options"][-1],token=result["decision"]["token"])["decision"]
            self.assertTrue(self.hero(game)["active"])
            self.assertEqual(game.get_state()["players"][0]["funds"],funds)
            result=self.sphinx_text(game,decision)
            choice=result["decision"]["pending_choice"]
            result=game.answer_text(choice["choice_id"],"incorrect",token=result["decision"]["token"])
            self.assertFalse(self.hero(game)["active"])
            self.assertEqual(game.get_state()["players"][0]["funds"],funds)
            self.assertFalse(any(e["type"]=="adventure_object_interacted" and e.get("funds",{}).get("gold",0)<0 for e in result["events"]))

    def test_text_stop_and_invalid_input_restore_the_original_native_action(self):
        with self.session() as (game,_):
            decision=self.start(game,"Sphinx")
            before=game.get_state()
            result=self.sphinx_text(game,decision)
            decision=result["decision"];choice=decision["pending_choice"]
            for value in ("x"*4097,"a\nb","a\0b",True):
                with self.assertRaises(ValueError):
                    game.answer_text(choice["choice_id"],value,token=decision["token"])
            self.assertEqual(game.get_decision(),decision)
            game.step("session.stop",token=decision["token"])
            self.assertEqual(game.get_state(),before)

    def test_trading_post_uses_native_rates_without_castle_market_and_closes_on_other_actions(self):
        with self.session() as (game,_):
            decision=self.start(game,"Trading Post")
            self.assertFalse(game.get_trading_post_options(52)["active"])
            result=self.move(game,decision,"Trading Post");decision=result["decision"]
            options=game.get_trading_post_options(52)
            self.assertTrue(options["active"])
            trade=next(t for t in options["trades"] if t["resource_from"]==64 and t["resource_to"]==1 and t["max_lots"]>=1)
            before=game.get_state()
            game.get_trading_post_options(52)
            self.assertEqual(game.get_state(),before)
            result=game.trade_at_post(52,64,1,1,token=decision["token"]);decision=result["decision"]
            funds=game.get_state()["players"][0]["funds"]
            self.assertEqual(funds["gold"],before["players"][0]["funds"]["gold"]-trade["sell_per_lot"])
            self.assertEqual(funds["wood"],before["players"][0]["funds"]["wood"]+trade["buy_per_lot"])
            self.reject(game,lambda:game.trade_at_post(42,64,1,1,token=decision["token"]),"illegal_action")
            limit=next(t for t in game.get_trading_post_options(52)["trades"] if t["resource_from"]==64 and t["resource_to"]==1)["max_lots"]
            self.reject(game,lambda:game.trade_at_post(52,64,1,limit+1,token=decision["token"]),"illegal_action")
            decision=game.end_turn(token=decision["token"])["decision"]
            self.assertFalse(game.get_trading_post_options(52)["active"])
            self.reject(game,lambda:game.trade_at_post(52,64,1,1,token=decision["token"]),"illegal_action")

    def test_scripted_event_applies_reward_skill_and_experience_once(self):
        with self.session() as (game,_):
            decision=self.start(game,"Event")
            before=game.get_state()
            result=self.finish(game,self.move(game,decision,"Event"))
            self.assertEqual(game.get_state()["players"][0]["funds"]["gold"],before["players"][0]["funds"]["gold"]+777)
            self.assertEqual(self.hero(game)["experience"],next(h for h in before["heroes"] if h["id"]==52)["experience"]+1500)
            self.assertTrue(any(a and a["id"]==65 for a in self.hero(game)["artifacts"]))
            decision=game.move_hero(52,15,19,token=result["decision"]["token"])["decision"]
            self.finish(game,self.move(game,decision,"Event"))
            self.assertEqual(game.get_state()["players"][0]["funds"]["gold"],before["players"][0]["funds"]["gold"]+777)

    def test_events_repeat_and_preserve_color_and_native_ai_eligibility(self):
        with self.session() as (game,_):
            for variant,expected in (("repeat",1554),("wrong-color",0),("ai-denied",0),("ai-allowed",1554)):
                decision=game.reset(save=FIXTURES / f"special-event-{variant}.sav",seed=123,controllers=CONTROLLERS)["decision"]
                before=game.get_state()["players"][0]["funds"]["gold"]
                result=self.finish(game,self.move(game,decision,"Event"))
                decision=game.move_hero(52,15,19,token=result["decision"]["token"])["decision"]
                self.finish(game,self.move(game,decision,"Event"))
                self.assertEqual(game.get_state()["players"][0]["funds"]["gold"]-before,expected)

    def test_portals_and_whirlpools_use_native_exit_rng_and_casualties(self):
        with self.session() as (game,_):
            for name in ("Stone Liths","Whirlpool"):
                traces=[]
                for _ in range(2):
                    decision=self.start(game,name)
                    before=self.hero(game)
                    self.move(game,decision,name)
                    after=self.hero(game)
                    self.assertGreaterEqual(after["position"]["x"],24)
                    self.assertTrue(after["active"])
                    self.assertEqual(after["is_shipmaster"],name=="Whirlpool")
                    if name=="Whirlpool":
                        self.assertLess(sum(t["count"] for t in after["army"] if t),sum(t["count"] for t in before["army"] if t))
                    traces.append(game.get_state())
                self.assertEqual(traces[0],traces[1])

    def test_magi_and_magellan_reveal_native_fog_and_charge_once(self):
        with self.session() as (game,_):
            decision=self.start(game,"Hut of the Magi")
            before=game.get_state()
            self.assertTrue(before["map"]["tiles"][674]["fog_colors"] & 1)
            self.move(game,decision,"Hut of the Magi")
            self.assertFalse(game.get_state()["map"]["tiles"][674]["fog_colors"] & 1)
            decision=self.start(game,"Magellan's Maps")
            before=game.get_state()
            result=self.finish(game,self.move(game,decision,"Magellan's Maps"))
            after=game.get_state()
            self.assertEqual(before["players"][0]["funds"]["gold"]-after["players"][0]["funds"]["gold"],1000)
            self.assertLess(sum(bool(t["fog_colors"]&1) for t in after["map"]["tiles"] if t["water"]),sum(bool(t["fog_colors"]&1) for t in before["map"]["tiles"] if t["water"]))

    def test_all_view_world_spells_return_native_filtered_data_and_readonly_images(self):
        with self.session() as (game,_):
            for spell_id,mode in ((49,2),(50,3),(51,1),(52,5),(53,4),(54,6)):
                decision=self.start(game,"Oracle")
                before=game.get_state()
                mana=self.hero(game)["spell_points"]
                quote=next(q for q in self.hero(game)["adventure_spell_options"] if q["spell_id"]==spell_id)
                result=game.cast_spell(52,spell_id,token=decision["token"])
                view=game.get_information_view()
                self.assertEqual((view["kind"],view["mode"],view["player_id"]),("world",mode,1))
                self.assertEqual(self.hero(game)["spell_points"],mana-quote["spell_points"])
                if mode==6:
                    self.assertEqual(len(view["tiles"]),1296)
                else:
                    self.assertLess(len(view["tiles"]),1296)
                allowed={2:"mine",3:"resource",1:"artifact",5:"town",4:"hero"}
                for marker in view["markers"]:
                    if mode!=6 and before["map"]["tiles"][marker["index"]]["fog_colors"] & 1:
                        self.assertEqual(marker["kind"],allowed[mode])
                    if marker["kind"]=="town":
                        castle=next(c for c in before["castles"] if c["position"]["index"]==marker["index"])
                        self.assertEqual(marker["owner"],castle["owner"])
                self.assertEqual([t["fog_colors"] for t in before["map"]["tiles"]],[t["fog_colors"] for t in game.get_state()["map"]["tiles"]])
                state,decision=game.get_state(),game.get_decision()
                frame=game.render(view="world",width=192,height=192)
                self.assertEqual(len(frame.pixels),192*192*3)
                self.assertEqual(game.get_state(),state)
                self.assertEqual(game.get_decision(),decision)
                self.assertEqual(game.get_information_view(),view)

    def test_oracle_exposes_native_rank_data_for_both_sides_and_snapshot_render(self):
        with self.session() as (game,_):
            decision=self.start(game,"Oracle")
            result=self.move(game,decision,"Oracle")
            view=game.get_information_view()
            self.assertEqual(view["kind"],"oracle")
            self.assertEqual({p["player_id"] for p in view["players"]},{1,2})
            for participant in game.get_state()["players"]:
                row=next(p for p in view["players"] if p["player_id"]==participant["id"])
                self.assertEqual(row["gold"],participant["funds"]["gold"])
            before=game.get_state()
            game.render(view="oracle",width=320,height=240)
            self.assertEqual(game.get_state(),before)
            self.assertFalse(game.runtime_info()["video_initialized"])

    def test_gym_supports_configured_text_answers_local_trades_and_views(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
        except ImportError:
            self.skipTest("Install optional gym extra")
        with self.session() as (parent,_):
            for name in ("Sphinx","Trading Post","Oracle"):
                with HeroesEnv(executable=support.EXECUTABLE,save=FIXTURES/self.record(name)["save"],env=parent._env,sphinx_answers=("wrong","human")) as env:
                    obs,_=env.reset(seed=123)
                    def select(action,**params):
                        return next(i for i,c in enumerate(env._commands) if c["action"]==action and all(c["params"].get(k)==v for k,v in params.items()))
                    obs,*_=env.step(select("hero.move",hero_id=52,x=15,y=18))
                    if name=="Sphinx":
                        obs,*_=env.step(0)
                        self.assertIn(b"four legs",bytes(obs["text"][obs["text_mask"].astype(bool)]))
                        obs,*_=env.step(select("choice.answer_text",text="human"))
                        self.assertTrue(next(h for h in env._state["heroes"] if h["id"]==52)["active"])
                    elif name=="Trading Post":
                        obs,*_=env.step(select("trading_post.trade",hero_id=52,resource_from=64,resource_to=1,lots=1))
                    else:
                        self.assertEqual(obs["view"][0],2)
                        self.assertEqual(int(obs["oracle_mask"].sum()),2)
                    self.assertTrue(env.observation_space.contains(obs))

    def test_information_is_frozen_until_replaced_and_cleared_on_reset(self):
        with self.session() as (game,_):
            decision=self.start(game,"Oracle")
            self.reject(game,game.get_information_view,"no_information_view")
            self.reject(game,lambda:game.render(view="oracle"),"no_information_view")
            result=self.move(game,decision,"Oracle")
            view=deepcopy(game.get_information_view())
            pixels=game.render(view="oracle").pixels
            game.end_turn(token=result["decision"]["token"])
            self.assertEqual(game.get_information_view(),view)
            self.assertEqual(game.render(view="oracle").pixels,pixels)
            self.start(game,"Oracle")
            self.reject(game,game.get_information_view,"no_information_view")

    def test_gym_default_text_answer_is_explicit_and_vocabulary_limits_are_validated(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
        except ImportError:
            self.skipTest("Install optional gym extra")
        with self.session() as (parent,_):
            kwargs=dict(executable=support.EXECUTABLE,save=FIXTURES/self.record("Sphinx")["save"],env=parent._env)
            for bad in ({"sphinx_answers":"human"},{"sphinx_answers":[[]]},{"sphinx_answers":["x"*257]},
                        {"max_text_bytes":0},{"max_answer_bytes":4096,"max_actions":8192}):
                with self.assertRaises(ValueError):
                    HeroesEnv(**kwargs,**bad)
            with HeroesEnv(**kwargs) as env:
                env.reset(seed=123)
                action=next(i for i,c in enumerate(env._commands) if c["action"]=="hero.move" and c["params"]=={"hero_id":52,"x":15,"y":18})
                env.step(action)
                env.step(0)
                self.assertEqual([c["params"]["text"] for c in env._commands],[""])
                obs,*_=env.step(0)
                self.assertFalse(next(h for h in env._state["heroes"] if h["id"]==52)["active"])
                self.assertTrue(env.observation_space.contains(obs))


if __name__=="__main__":
    unittest.main()
