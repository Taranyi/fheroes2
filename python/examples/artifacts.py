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

"""Move and swap real artifacts between heroes, preserving scrolls and native bonuses."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def slot(hero_id, index):
    return {"hero_id": hero_id, "slot": index}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--save", type=Path, default=root / "build/python-env-baseline/fixtures/artifacts-day1.sav")
    args = parser.parse_args()
    if not args.save.is_file():
        parser.error("Prepare the native artifact fixture first; see docs/PYTHON_ENV_ARTIFACTS.md")
    with HeroesSession(args.executable, timeout=60) as game:
        game.load_save(args.save)
        state = game.get_state(include_serialized=False)
        human = next(p for p in state["players"] if p["is_human"])
        castle_id = human["castle_ids"][0]
        decision = game.start_session(human["id"])

        def act(method, *values):
            nonlocal decision
            result = method(*values, token=decision["token"])
            decision = result["decision"]
            print(json.dumps(result["events"]), flush=True)

        # The native fixture uses the baseline's offered Zom (46), with separate test artifacts.
        act(game.refresh_hero_offers, castle_id)
        act(game.move_hero, 52, 32, 25)
        act(game.hire_hero, castle_id, 46)
        act(game.meet_heroes, 52, 46)
        act(game.transfer_artifact, slot(52, 1), slot(46, 5))  # Telescope; scout bonus follows the artifact.
        act(game.transfer_artifact, slot(52, 3), slot(46, 6))  # Scroll, retaining its native spell.
        act(game.swap_artifacts, slot(52, 2), slot(46, 1))  # Dragon Sword for Medal of Courage.
        act(game.transfer_artifact, slot(52, 4), slot(46, 4))  # Third Anduran piece assembles the native set.
        act(game.end_meeting)  # Apply net scouting gain on encounter close, just like the normal meeting UI.
        for hero in game.get_state(include_serialized=False)["heroes"]:
            if hero["id"] in (52, 46):
                print(hero["name"], "attack:", hero["attack"], "scouting:", hero["scouting_distance"])
                print(json.dumps(hero["artifacts"]))
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
