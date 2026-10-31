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

"""Buy a boat, visit home, sail and disembark in the dedicated harbor fixture."""

import argparse
import os
from pathlib import Path
from fheroes2_env import HeroesSession

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable",type=Path,default=ROOT / ("fheroes2.exe" if os.name=="nt" else "fheroes2"))
    args=parser.parse_args()
    fixture=ROOT / "build/python-env-baseline/fixtures/navigation-shipyard-day1.sav"
    if not fixture.is_file():
        parser.error("Prepare fixtures with script/windows/python-env-artifact-fixture.ps1")
    with HeroesSession(args.executable,timeout=60) as game:
        decision=game.reset(save=fixture,seed=123,controllers={1:"python",2:"python"})["decision"]
        def show(label,result):
            hero=next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"]==52)
            print(label, "position=",hero["position"],"ship=",hero["is_shipmaster"],"movement=",hero["move_points"],"castle=",hero["castle_id"],flush=True)
            print("  events:",[e["type"] for e in result["events"]],flush=True)
            return result["decision"]
        print("Harbor:",game.get_castle_options(896)["boat"],flush=True)
        decision=show("Buy boat",game.buy_boat(896,token=decision["token"]))
        for label,x,y in (("Leave home",32,25),("Visit own castle",32,24),("Reach shore",32,25),("Board",32,26)):
            decision=show(label,game.move_hero(52,x,y,token=decision["token"]))
        # Each Python side explicitly ends its turn; no keyboard player is needed.
        decision=game.end_turn(token=decision["token"])["decision"]
        decision=game.end_turn(token=decision["token"])["decision"]
        decision=show("Sail",game.move_hero(52,32,28,token=decision["token"]))
        decision=show("Disembark",game.move_hero(52,32,25,token=decision["token"]))
        print("Empty boat at former water tile:",[(t["index"],t["boat_owner"]) for t in game.get_state(include_serialized=False)["map"]["tiles"] if t["boat_owner"]])
        print("Runtime:",game.runtime_info())


if __name__=="__main__":
    main()
