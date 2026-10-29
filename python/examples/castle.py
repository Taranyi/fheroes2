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

"""Inspect, build and recruit in a real castle, with no game window."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--save", type=Path, default=root / "build/python-env-baseline/fixtures/other-side-day1.sav")
    args = parser.parse_args()
    with HeroesSession(args.executable, timeout=60) as game:
        game.load_save(args.save)
        state = game.get_state(include_serialized=False)
        human = next(player for player in state["players"] if player["is_human"])
        castle_id = human["castle_ids"][0]
        decision = game.start_session(human["id"])
        options = game.get_castle_options(castle_id)
        print("Buildings:")
        for building in options["buildings"]:
            print(f"  {building['building_id']}: {building['name']} | {building['status']} | {building['cost']}")
        # Prefer a well; otherwise buy the first currently legal building. Rules/prices stay in C++.
        buildable = [building for building in options["buildings"] if building["can_build"]]
        if buildable:
            building = next((building for building in buildable if building["building_id"] == 8), buildable[0])
            result = game.build_castle(castle_id, building["building_id"], token=decision["token"])
            decision = result["decision"]
            print("Built:", json.dumps(result["events"]))
        else:
            print("No building can be purchased in this saved turn.")
        options = game.get_castle_options(castle_id)
        print("Dwellings:", json.dumps(options["dwellings"]))
        recruitable = next((dwelling for dwelling in options["dwellings"] if dwelling["max_recruitable"] > 0), None)
        if recruitable:
            count = min(3, recruitable["max_recruitable"])
            result = game.recruit_castle(castle_id, recruitable["dwelling_id"], count, token=decision["token"])
            print("Recruited:", json.dumps(result["events"]))
        else:
            print("No creatures can currently be recruited.")
        after = game.get_state(include_serialized=False)
        print("Castle:", json.dumps(next(castle for castle in after["castles"] if castle["id"] == castle_id)))
        print("Funds:", next(player for player in after["players"] if player["id"] == human["id"])["funds"])
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
