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

"""Usage: uv run --project python python python/examples/hello.py --executable fheroes2.exe"""

import argparse
import json
from pathlib import Path

from fheroes2_env import HeroesSession


def main():
    parser = argparse.ArgumentParser(description="Check the fheroes2 Python connection without loading a game.")
    parser.add_argument("--executable", type=Path, default=Path(__file__).resolve().parents[2] / "fheroes2.exe")
    args = parser.parse_args()
    with HeroesSession(args.executable) as game:
        print(json.dumps(game.info, indent=2))
        print(f"Capabilities: {game.capabilities()}")
        process_id = game.pid
    print(f"Engine process {process_id} closed cleanly (exit code {game.returncode}).")


if __name__ == "__main__":
    main()
