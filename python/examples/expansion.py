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

"""Run native object interactions, adventure travel and extended combat spells."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession
from battle import select_action

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "build/python-env-baseline/fixtures"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all", "objects", "travel", "battle"), default="all")
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    args = parser.parse_args()
    manifest = FIXTURES / "expansion-objects.json"
    if not manifest.is_file():
        parser.error("Prepare fixtures with script/windows/python-env-artifact-fixture.ps1")
    records = json.loads(manifest.read_text())
    with HeroesSession(args.executable, timeout=60) as game:
        def reset_name(name):
            record = next(r for r in records if r["name"] == name)
            return game.reset(save=FIXTURES / record["save"], seed=123,
                              controllers={1: "python", 2: "python"})["decision"]

        def hero():
            return next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"] == 52)

        def complete(result):
            for _ in range(600):
                decision = result["decision"]
                if decision["phase"] == "choice":
                    choice = decision["pending_choice"]
                    value = choice["options"][0] if choice["options"] else choice["minimum"]
                    print("Python chooses:", choice["kind"], "value=", value, "native values=", choice["values"], flush=True)
                    result = game.answer_choice(choice["choice_id"], value, token=decision["token"])
                elif decision["phase"] == "battle":
                    action = select_action(decision["battle"], use_spells=True)
                    result = game.battle_action(action["action_id"], token=decision["token"])
                else:
                    return result["decision"]
            raise RuntimeError("Demonstration decision limit exceeded")

        if args.scenario in ("all", "objects"):
            for name in ("Windmill", "Arena", "Tree of Knowledge", "Artifact"):
                decision = reset_name(name)
                before = hero()
                complete(game.move_hero(52, 15, 18, token=decision["token"]))
                after = hero()
                print(name, {k: (before[k], after[k]) for k in ("level", "experience", "attack", "power", "spell_points")}, flush=True)
            decision = reset_name("Mine")
            decision = complete(game.move_hero(52, 15, 18, token=decision["token"]))
            complete(game.cast_spell(52, 62, token=decision["token"]))  # Set Earth Guardian
            tile = game.get_state(include_serialized=False)["map"]["tiles"][663]
            print("Native mine guardians:", {k: tile[k] for k in ("owner", "guardian_monster_id", "guardian_count")}, flush=True)

        if args.scenario in ("all", "travel"):
            decision = reset_name("Magic Well")
            decision = complete(game.cast_spell(52, 57, token=decision["token"]))  # Dimension Door
            print("After Dimension Door:", hero()["position"], "mana=", hero()["spell_points"], flush=True)
            complete(game.cast_spell(52, 59, token=decision["token"]))  # Town Portal
            print("After Town Portal: castle=", hero()["castle_id"], "mana=", hero()["spell_points"], flush=True)

        if args.scenario in ("all", "battle"):
            for spell_id, name in ((11, "Mass Haste"), (44, "Summon Earth Elemental"), (5, "Teleport")):
                decision = game.reset(save=FIXTURES / "expansion-battle.sav", seed=123,
                                      controllers={1: "python", 2: "python"})["decision"]
                decision = game.move_hero(52, 15, 18, token=decision["token"])["decision"]
                action = next(a for a in decision["battle"]["actions"] if a["kind"] == "spell" and a["spell_id"] == spell_id)
                before = len(decision["battle"]["units"])
                result = game.battle_action(action["action_id"], token=decision["token"])
                print(name, "native command=", action, "unit stacks=", (before, len(result["decision"]["battle"]["units"])), flush=True)
                # Reset in the next iteration unwinds this live battle and starts a separate example.
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
