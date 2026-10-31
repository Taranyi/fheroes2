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

"""Exercise the declared object and spell expansion through native sessions."""

import json
import unittest
from copy import deepcopy

from fheroes2_env import EngineError
import test_world_state as support
import test_battle as battle_support

ROOT = support.ROOT
FIXTURES = ROOT / "build/python-env-baseline/fixtures"
CONTROLLERS = {1: "python", 2: "python"}


class ExpansionTests(unittest.TestCase):
    session = support.WorldStateTests.session

    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        manifest=FIXTURES / "expansion-objects.json"
        if not manifest.is_file():
            raise unittest.SkipTest("Prepare --expansion-only native fixtures")
        cls.objects=json.loads(manifest.read_text())

    def start(self, game, name):
        record=next(r for r in self.objects if r["name"].lower()==name.lower())
        return game.reset(save=FIXTURES / record["save"],seed=123,controllers=CONTROLLERS)["decision"]

    def hero(self,game):
        return next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"]==52)

    def finish(self,game,result,*,answer=None):
        for _ in range(600):
            decision=result["decision"]
            if decision["phase"]=="choice":
                choice=decision["pending_choice"]
                value=(answer(choice) if answer else (choice["options"][0] if choice["options"] else choice["minimum"]))
                result=game.answer_choice(choice["choice_id"],value,token=decision["token"])
            elif decision["phase"]=="battle":
                action=battle_support._example.select_action(decision["battle"],use_spells=True)
                result=game.battle_action(action["action_id"],token=decision["token"])
            else:
                return result
        self.fail("Expansion interaction exceeded its decision budget")

    def visit(self,game,decision,**kwargs):
        if self.hero(game)["position"]["index"]==663:
            decision=game.move_hero(52,15,19,token=decision["token"])["decision"]
        return self.finish(game,game.move_hero(52,15,18,token=decision["token"]),**kwargs)

    def reject(self,game,call,code):
        state,decision=game.get_state(),game.get_decision()
        with self.assertRaises(EngineError) as error:
            call()
        self.assertEqual(error.exception.code,code)
        self.assertEqual(game.get_state(),state)
        self.assertEqual(game.get_decision(),decision)

    def test_every_declared_object_fixture_completes_native_interaction_headlessly(self):
        with self.session() as (game,_):
            for record in self.objects:
                with self.subTest(object=record["name"],id=record["object_id"]):
                    decision=game.reset(save=FIXTURES / record["save"],seed=123,controllers=CONTROLLERS)["decision"]
                    before=game.get_state()
                    result=self.visit(game,decision)
                    self.assertIn(result["decision"]["phase"],("adventure","terminal"))
                    self.assertGreater(game.get_state()["state_version"],before["state_version"])
                    self.assertFalse(game.runtime_info()["video_initialized"])
                    self.assertFalse(game.runtime_info()["audio_initialized"])

    def test_combat_catalog_exposes_extended_spells_without_mutating_queries(self):
        with self.session() as (game,_):
            decision=game.reset(save=FIXTURES / "expansion-battle.sav",seed=4,controllers=CONTROLLERS)["decision"]
            decision=game.move_hero(52,15,18,token=decision["token"])["decision"]
            self.assertEqual(decision["phase"],"battle")
            spells={a["spell_id"] for a in decision["battle"]["actions"] if a["kind"]=="spell"}
            self.assertTrue({2,4,5,11,14,16,28,29,30,34,35,41,44,45,46,47}.issubset(spells))
            self.assertGreater(len(spells),20)
            before=game.get_state()
            self.assertEqual(game.get_decision(),decision)
            game.render(view="battle",width=96,height=96)
            self.assertEqual(game.get_state(),before)
            self.assertEqual(game.get_decision(),decision)

    def test_resource_visits_skill_training_and_arena_are_native_and_not_repeatable(self):
        with self.session() as (game,_):
            decision=self.start(game,"Windmill")
            before=game.get_state()["players"][0]["funds"]
            result=self.visit(game,decision)
            after=game.get_state()["players"][0]["funds"]
            self.assertNotEqual(after,before)
            # Native action leaves a hero in front of a visited windmill.
            result=self.visit(game,result["decision"])
            self.assertEqual(game.get_state()["players"][0]["funds"],after)
            decision=self.start(game,"Mercenary Camp")
            attack=self.hero(game)["attack"]
            result=self.visit(game,decision)
            self.assertEqual(self.hero(game)["attack"],attack+1)
            result=self.visit(game,result["decision"])
            self.assertEqual(self.hero(game)["attack"],attack+1)
            decision=self.start(game,"Arena")
            before=self.hero(game)
            result=game.move_hero(52,15,18,token=decision["token"])
            choice=result["decision"]["pending_choice"]
            self.assertEqual(choice["kind"],"hero.primary_skill")
            self.assertEqual(len(choice["options"]),3)
            decision=result["decision"]
            self.reject(game,lambda:game.answer_choice(choice["choice_id"],999,token=decision["token"]),"illegal_action")
            result=game.answer_choice(choice["choice_id"],choice["options"][0],token=decision["token"])
            self.assertEqual(self.hero(game)["attack"],before["attack"]+1)

    def test_artifact_and_tree_confirmation_decline_accept_and_rollback(self):
        with self.session() as (game,_):
            for name in ("Artifact","Tree of Knowledge"):
                with self.subTest(object=name):
                    decision=self.start(game,name)
                    before=game.get_state()
                    result=game.move_hero(52,15,18,token=decision["token"])
                    choice=result["decision"]["pending_choice"]
                    self.assertEqual(choice["kind"],"confirmation")
                    self.assertEqual(choice["values"]["gold"],2000)
                    decision=result["decision"]
                    game.step("session.stop",token=decision["token"])
                    self.assertEqual(game.get_state(),before)
                    decision=self.start(game,name)
                    before=self.hero(game)
                    funds=game.get_state()["players"][0]["funds"]["gold"]
                    result=self.visit(game,decision,answer=lambda c:c["options"][-1] if c["kind"]=="confirmation" else c["options"][0])
                    self.assertEqual(game.get_state()["players"][0]["funds"]["gold"],funds)
                    self.assertEqual(self.hero(game)["experience"],before["experience"])
                    self.assertEqual(self.hero(game)["artifacts"],before["artifacts"])
                    result=self.visit(game,result["decision"])
                    self.assertEqual(game.get_state()["players"][0]["funds"]["gold"],funds-2000)
                    if name=="Artifact":
                        self.assertNotEqual(self.hero(game)["artifacts"],before["artifacts"])
                    else:
                        self.assertGreater(self.hero(game)["level"],before["level"])

    def test_mine_capture_guardian_spells_and_income_are_observable_for_all_sides(self):
        with self.session() as (game,_):
            for spell_id in (61,62,63,64,65):
                with self.subTest(spell=spell_id):
                    decision=self.start(game,"Mine")
                    result=self.visit(game,decision)
                    decision=result["decision"]
                    tile=game.get_state()["map"]["tiles"][663]
                    self.assertEqual(tile["owner"],1)
                    self.assertEqual(self.hero(game)["position"]["index"],663)
                    option=next(o for o in self.hero(game)["adventure_spell_options"] if o["spell_id"]==spell_id)
                    self.assertTrue(option["can_cast"])
                    mana=self.hero(game)["spell_points"]
                    result=game.cast_spell(52,spell_id,token=decision["token"])
                    tile=game.get_state()["map"]["tiles"][663]
                    self.assertGreater(tile["guardian_count"],0)
                    self.assertGreater(tile["guardian_monster_id"],0)
                    self.assertEqual(tile["owner"],0 if spell_id==61 else 1)
                    self.assertEqual(self.hero(game)["spell_points"],mana-option["spell_points"])
                    before=game.get_state()
                    game.get_state(); game.get_decision(); game.render(width=96,height=96,center=(15,18))
                    self.assertEqual(game.get_state(),before)
            decision=self.start(game,"Sawmill")
            decision=self.visit(game,decision)["decision"]
            before=game.get_state()["players"][0]["funds"]["wood"]
            decision=game.end_turn(token=decision["token"])["decision"]
            game.end_turn(token=decision["token"])
            self.assertGreater(game.get_state()["players"][0]["funds"]["wood"],before)

    def test_town_travel_choice_native_cost_and_stop_restore(self):
        with self.session() as (game,_):
            for spell_id in (58,59):
                decision=self.start(game,"Magic Well")
                before=game.get_state()
                mana=self.hero(game)["spell_points"]
                option=next(o for o in self.hero(game)["adventure_spell_options"] if o["spell_id"]==spell_id)
                self.assertTrue(option["can_cast"])
                result=game.cast_spell(52,spell_id,token=decision["token"])
                if spell_id==59:
                    decision=result["decision"]
                    choice=decision["pending_choice"]
                    self.assertEqual(choice["kind"],"spell.town_portal")
                    self.assertIn(896,choice["options"])
                    self.reject(game,lambda:game.answer_choice(choice["choice_id"],867,token=decision["token"]),"illegal_action")
                    game.step("session.stop",token=decision["token"])
                    self.assertEqual(game.get_state(),before)
                    decision=self.start(game,"Magic Well")
                    result=game.cast_spell(52,spell_id,token=decision["token"])
                    result=self.finish(game,result)
                self.assertEqual(self.hero(game)["castle_id"],896)
                self.assertEqual(self.hero(game)["spell_points"],mana-option["spell_points"])
                self.assertEqual(result["decision"]["phase"],"adventure")

    def test_summon_boat_moves_exactly_one_native_boat_without_presentation(self):
        with self.session() as (game,_):
            decision=game.reset(save=FIXTURES / "expansion-summon.sav",seed=4,controllers=CONTROLLERS)["decision"]
            before=game.get_state()
            option=next(o for o in self.hero(game)["adventure_spell_options"] if o["spell_id"]==56)
            self.assertTrue(option["can_cast"])
            result=game.cast_spell(52,56,token=decision["token"])
            after=game.get_state()
            self.assertEqual(after["map"]["tiles"][968]["boat_owner"],1)
            self.assertEqual(after["map"]["tiles"][1078]["boat_owner"],0)
            self.assertEqual(self.hero(game)["spell_points"],1000-option["spell_points"])
            self.assertEqual(self.hero(game)["position"]["index"],932)
            self.assertFalse(game.runtime_info()["video_initialized"])

    def enter_spell_battle(self,game):
        decision=game.reset(save=FIXTURES / "expansion-battle.sav",seed=4,controllers=CONTROLLERS)["decision"]
        return game.move_hero(52,15,18,token=decision["token"])["decision"]

    def test_every_initially_legal_combat_spell_executes_and_charges_once(self):
        with self.session() as (game,_):
            decision=self.enter_spell_battle(game)
            spells=sorted({a["spell_id"] for a in decision["battle"]["actions"] if a["kind"]=="spell"})
            for spell_id in spells:
                with self.subTest(spell=spell_id):
                    decision=self.enter_spell_battle(game)
                    action=next(a for a in decision["battle"]["actions"] if a["kind"]=="spell" and a["spell_id"]==spell_id)
                    before=game.get_state()
                    result=game.battle_action(action["action_id"],token=decision["token"])
                    self.assertEqual(self.hero(game)["spell_points"],1000-action["spell_points"])
                    self.assertTrue(any(e["type"]=="battle_action" and e["action"]["spell_id"]==spell_id for e in result["events"]))
                    after=result["decision"]
                    if after["phase"]=="battle" and after["player_id"]==1:
                        self.assertFalse(any(a["kind"]=="spell" for a in after["battle"]["actions"]))
                    self.reject(game,lambda:game.battle_action(action["action_id"],token=decision["token"]),"stale_decision")

    def test_summoning_adds_native_units_and_teleport_moves_the_selected_unit(self):
        with self.session() as (game,_):
            for spell_id in (5,41,44,45,46,47):
                decision=self.enter_spell_battle(game)
                units=decision["battle"]["units"]
                action=next(a for a in decision["battle"]["actions"] if a["kind"]=="spell" and a["spell_id"]==spell_id)
                result=game.battle_action(action["action_id"],token=decision["token"])
                after=result["decision"]["battle"]["units"]
                if spell_id==5:
                    unit=next(u for u in after if u["uid"]==action["target_uid"])
                    self.assertEqual(unit["head"],action["target_cell"])
                else:
                    self.assertGreater(len(after),len(units))

    def test_injured_and_dead_targets_offer_native_healing_and_resurrection(self):
        with self.session() as (game,_):
            for resurrect in (8,9,40):
                decision=self.enter_spell_battle(game)
                target=next(u for u in decision["battle"]["units"] if u["army_color"]==1 and (u["monster_id"]!=2 if resurrect==40 else u["monster_id"]==2))
                # Let the defender cast damage at the chosen friendly stack.
                for _ in range(20):
                    if decision["player_id"]==2:
                        arrow=next(a for a in decision["battle"]["actions"] if a["kind"]=="spell" and a["spell_id"]==3 and a["target_cell"]==target["head"])
                        decision=game.battle_action(arrow["action_id"],token=decision["token"])["decision"]
                        break
                    skip=next(a for a in decision["battle"]["actions"] if a["kind"]=="skip")
                    decision=game.battle_action(skip["action_id"],token=decision["token"])["decision"]
                for _ in range(20):
                    if decision["player_id"]==1:
                        break
                    skip=next(a for a in decision["battle"]["actions"] if a["kind"]=="skip")
                    decision=game.battle_action(skip["action_id"],token=decision["token"])["decision"]
                damaged=next(u for u in decision["battle"]["units"] if u["uid"]==target["uid"])
                self.assertLess(damaged["count"],target["count"])
                action=next(a for a in decision["battle"]["actions"] if a["kind"]=="spell" and a["spell_id"]==resurrect and a["target_cell"]==target["head"])
                decision=game.battle_action(action["action_id"],token=decision["token"])["decision"]
                healed=next(u for u in decision["battle"]["units"] if u["uid"]==target["uid"])
                self.assertGreater(healed["count"],damaged["count"])

    def test_earthquake_is_siege_only(self):
        with self.session() as (game,_):
            decision=self.enter_spell_battle(game)
            self.assertFalse(any(a.get("spell_id")==48 for a in decision["battle"]["actions"]))
            decision=game.reset(save=FIXTURES / "expansion-siege.sav",seed=4,controllers=CONTROLLERS)["decision"]
            decision=game.move_hero(52,3,24,token=decision["token"])["decision"]
            for _ in range(20):
                if decision["player_id"]==1:
                    break
                skip=next(a for a in decision["battle"]["actions"] if a["kind"]=="skip")
                decision=game.battle_action(skip["action_id"],token=decision["token"])["decision"]
            action=next(a for a in decision["battle"]["actions"] if a.get("spell_id")==48)
            self.assertEqual(action["target_cell"],-1)
            game.battle_action(action["action_id"],token=decision["token"])
            self.assertEqual(self.hero(game)["spell_points"],1000-action["spell_points"])


    def test_dimension_door_uses_native_targets_charges_once_and_rolls_back(self):
        with self.session() as (game,_):
            decision=self.start(game,"Magic Well")
            before=game.get_state()
            mana=self.hero(game)["spell_points"]
            movement=self.hero(game)["move_points"]
            option=next(o for o in self.hero(game)["adventure_spell_options"] if o["spell_id"]==57)
            result=game.cast_spell(52,57,token=decision["token"])
            decision=result["decision"]
            choice=decision["pending_choice"]
            self.assertEqual(choice["kind"],"spell.dimension_door")
            self.assertTrue(choice["options"])
            self.assertTrue(all(abs(index%36-15)<=7 and abs(index//36-19)<=7 for index in choice["options"]))
            self.reject(game,lambda:game.answer_choice(choice["choice_id"],663,token=decision["token"]),"illegal_action")
            game.step("session.stop",token=decision["token"])
            self.assertEqual(game.get_state(),before)
            decision=self.start(game,"Magic Well")
            result=game.cast_spell(52,57,token=decision["token"])
            decision=result["decision"]
            choice=decision["pending_choice"]
            destination=next(i for i in choice["options"] if i==17*36+14)
            result=game.answer_choice(choice["choice_id"],destination,token=decision["token"])
            self.assertEqual(self.hero(game)["position"]["index"],destination)
            self.assertEqual(self.hero(game)["spell_points"],mana-option["spell_points"])
            self.assertEqual(self.hero(game)["move_points"],max(0,movement-option["move_points"]))
            self.assertEqual(result["decision"]["phase"],"adventure")


    def test_gym_encodes_object_effects_prices_and_native_target_choices(self):
        try:
            from fheroes2_env.gym_env import HeroesEnv
        except ImportError:
            self.skipTest("Install optional gym extra")
        with self.session() as (parent,_):
            for name,action,params,kind in (
                    ("Arena","hero.move",{"hero_id":52,"x":15,"y":18},"hero.primary_skill"),
                    ("Tree of Knowledge","hero.move",{"hero_id":52,"x":15,"y":18},"confirmation"),
                    ("Magic Well","hero.cast",{"hero_id":52,"spell_id":59},"spell.town_portal"),
                    ("Magic Well","hero.cast",{"hero_id":52,"spell_id":57},"spell.dimension_door")):
                record=next(r for r in self.objects if r["name"]==name)
                with HeroesEnv(executable=support.EXECUTABLE,save=FIXTURES / record["save"],env=parent._env,max_steps=100) as env:
                    obs,_=env.reset(seed=4)
                    matching=[i for i,c in enumerate(env._commands) if c["action"]==action and c["params"]==params]
                    self.assertTrue(matching,f"Missing {name} {params}: {[(c['action'],c['params']) for c in env._commands if c['action'] in ('hero.cast','hero.move')]}")
                    index=matching[0]
                    obs,_,_,_,_=env.step(index)
                    self.assertEqual(env._decision["pending_choice"]["kind"],kind)
                    self.assertEqual(obs["tiles"].shape[1],19)
                    self.assertEqual(obs["heroes"].shape[1],25)
                    self.assertTrue(env.observation_space.contains(obs))
                    if name=="Tree of Knowledge":
                        self.assertEqual(env._decision["pending_choice"]["values"]["gold"],2000)
                    obs,_,_,_,_=env.step(0)
                    self.assertTrue(env.observation_space.contains(obs))


    def test_paid_dwelling_recruits_requested_positive_count_at_native_price(self):
        with self.session() as (game,_):
            decision=self.start(game,"Desert Tent")
            before=game.get_state()
            quote={}
            def answer(choice):
                if choice["kind"]=="army.recruit_count":
                    self.assertGreaterEqual(choice["maximum"],1)
                    quote.update(choice["values"])
                    return 1
                return choice["options"][0]
            self.visit(game,decision,answer=answer)
            self.assertTrue(quote)
            self.assertEqual(before["players"][0]["funds"]["gold"]-game.get_state()["players"][0]["funds"]["gold"],quote["gold_per_unit"])
            before_hero=next(h for h in before["heroes"] if h["id"]==52)
            def count(hero):
                return sum(t["count"] for t in hero["army"] if t and t["monster_id"]==quote["monster_id"])
            self.assertEqual(count(self.hero(game)),count(before_hero)+1)



if __name__=="__main__":
    unittest.main()
