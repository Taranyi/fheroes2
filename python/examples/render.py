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

"""Render the real adventure map without a window, audio or game time advancing."""

import argparse
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--output", type=Path, default=root / "build/python-env-render.ppm")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--center", nargs=2, type=int, metavar=("X", "Y"))
    args = parser.parse_args()
    with HeroesSession(args.executable, timeout=20) as game:
        game.load_save(args.save)
        state = game.get_state(include_serialized=False)
        human = next(player for player in state["players"] if player["is_human"])
        hero = next((hero for hero in state["heroes"] if hero["id"] in human["hero_ids"] and hero["position"] is not None), None)
        center = tuple(args.center) if args.center is not None else ((hero["position"]["x"], hero["position"]["y"]) if hero else None)
        decision = game.start_session(human["id"])
        frame = game.render(width=args.width, height=args.height, center=center)
        assert game.get_state(include_serialized=False) == state
        assert game.get_decision() == decision
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.save_ppm(args.output)
        print(f"RGB shape: {frame.shape}; center: {frame.center}; perspective: omniscient")
        print(f"Runtime: {game.runtime_info()}")
        print(f"Image written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
