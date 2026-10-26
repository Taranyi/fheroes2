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

"""Load a save through the real engine and report both human and AI state."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--output", type=Path, help="Write the full omniscient JSON state to this file.")
    args = parser.parse_args()
    with HeroesSession(args.executable, timeout=20) as game:
        game.load_save(args.save)
        state = game.get_state(include_serialized=args.output is not None)
        print(f"{state['map']['name']}: {state['map']['width']} x {state['map']['height']}, {state['date']}")
        print("Perspective: omniscient (includes AI and fog-hidden state)")
        for player in state["players"]:
            heroes = [hero["name"] for hero in state["heroes"] if hero["id"] in player["hero_ids"]]
            castles = [castle["name"] for castle in state["castles"] if castle["id"] in player["castle_ids"]]
            print(f"{player['color']} ({'AI' if player['is_ai'] else 'human'}): {player['funds']}; heroes={heroes}; castles={castles}")
        if args.output is not None:
            args.output.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"State written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
