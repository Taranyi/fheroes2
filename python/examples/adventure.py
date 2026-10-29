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

"""Move, collect seven wood and run the built-in AI on the recorded reference map."""

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
        if state["map"]["name"] != "The Other Side" or state["date"]["total_days"] != 1:
            raise RuntimeError("This example uses the recorded The Other Side day-1 fixture")
        hero = next(hero for hero in state["heroes"] if hero["name"] == "Roxana" and hero["owner"] == 1)
        decision = game.start_session(1)
        for x, y in ((32, 25), (32, 26), (31, 27), (30, 28), (29, 29)):
            result = game.move_hero(hero["id"], x, y, token=decision["token"])
            decision = result["decision"]
            print(json.dumps(result["events"]))
        result = game.end_turn(token=decision["token"])
        decision = result["decision"]
        print(json.dumps(result["events"]))
        result = game.move_hero(hero["id"], 27, 32, token=decision["token"])
        print(json.dumps(result["events"]))
        assert next(event for event in result["events"] if event["type"] == "resource_collected")["funds"]["wood"] == 7
        frame = game.render(width=640, height=480, center=(28, 32))
        output = root / "build/python-env-adventure.ppm"
        frame.save_ppm(output)
        print(f"Day: {game.get_state(include_serialized=False)['date']}; image: {output}")
        print(f"Runtime: {game.runtime_info()}")


if __name__ == "__main__":
    main()
