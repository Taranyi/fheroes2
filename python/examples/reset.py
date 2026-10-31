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

"""Run the same seeded native episode twice and compare every full state."""

import argparse
import os
from pathlib import Path

from fheroes2_env import HeroesSession

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--save", type=Path)
    source.add_argument("--map", dest="map_path", type=Path)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--turns", type=int, default=3)
    args = parser.parse_args()
    if not 0 <= args.turns <= 30:
        parser.error("--turns must be between 0 and 30")
    setup = {"map_path": args.map_path} if args.map_path else {"save": args.save or ROOT / "build/python-env-baseline/fixtures/other-side-day1.sav"}
    trace = None
    with HeroesSession(args.executable, timeout=60) as game:
        for episode_index in range(2):
            episode = game.reset(**setup, seed=args.seed)
            states = [game.get_state()]
            decision = episode["decision"]
            for _ in range(args.turns):
                if decision["phase"] != "adventure":
                    break
                result = game.end_turn(token=decision["token"])
                decision = result["decision"]
                states.append(game.get_state())
            print(f"episode={episode_index + 1} seed={episode['seed']} pid={game.pid} day={states[-1]['date']['total_days']} phase={decision['phase']}")
            if trace is not None:
                assert states == trace, "Native replay diverged"
            trace = states
        print("Full native states match across fresh processes.")
        print(game.runtime_info())


if __name__ == "__main__":
    main()
