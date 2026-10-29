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

"""Split/merge/swap stacks, reinforce a garrison and transfer between meeting heroes."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def slot(kind, entity_id, index):
    return {"kind": kind, "id": entity_id, "slot": index}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--save", type=Path, default=root / "build/python-env-baseline/fixtures/other-side-day1.sav")
    args = parser.parse_args()
    with HeroesSession(args.executable, timeout=60) as game:
        game.load_save(args.save)
        state = game.get_state(include_serialized=False)
        if state["map"]["name"] != "The Other Side" or state["date"]["total_days"] != 1:
            raise ValueError("This walkthrough uses the recorded The Other Side day-1 fixture")
        decision = game.start_session(1)
        castle_id = next(p for p in state["players"] if p["id"] == 1)["castle_ids"][0]

        def act(method, *values):
            nonlocal decision
            result = method(*values, token=decision["token"])
            decision = result["decision"]
            print(json.dumps(result["events"]), flush=True)
            return result

        # Roxana: 9 Skeletons + 4 Zombies. Split four Skeletons into an empty slot, then merge back.
        act(game.transfer_troops, slot("hero", 52, 0), slot("hero", 52, 2), 4)
        act(game.transfer_troops, slot("hero", 52, 2), slot("hero", 52, 0), 4)
        act(game.swap_troops, slot("hero", 52, 0), slot("hero", 52, 1))
        act(game.swap_troops, slot("hero", 52, 0), slot("hero", 52, 1))
        # A visitor can reinforce the garrison; the garrison may give all units back.
        act(game.transfer_troops, slot("hero", 52, 1), slot("castle", castle_id, 0), 4)
        act(game.transfer_troops, slot("castle", castle_id, 0), slot("hero", 52, 1), 4)
        act(game.refresh_hero_offers, castle_id)
        act(game.move_hero, 52, 32, 25)
        offer = next(h for h in game.get_castle_options(castle_id)["hero_hiring"]["offers"] if h["available"])
        other_id = offer["hero_id"]
        act(game.hire_hero, castle_id, other_id)
        # Meeting pays its native movement cost once. Multiple army changes can then use this encounter.
        act(game.meet_heroes, 52, other_id)
        act(game.transfer_troops, slot("hero", 52, 0), slot("hero", other_id, 4), 2)
        after = game.get_state(include_serialized=False)
        print("Meeting:", after["army_meeting"])
        for hero in after["heroes"]:
            if hero["id"] in (52, other_id):
                print(hero["name"], "movement:", hero["move_points"], "army:", json.dumps(hero["army"]))
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
