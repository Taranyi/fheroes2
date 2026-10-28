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

"""Enter the loaded human-turn checkpoint, inspect it and detach without advancing time."""

import argparse
import os
from pathlib import Path

from fheroes2_env import EngineError, HeroesSession


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    args = parser.parse_args()
    with HeroesSession(args.executable, timeout=20) as game:
        game.load_save(args.save)
        before = game.get_state()
        human = next(player for player in before["players"] if player["is_human"])
        decision = game.start_session(human["id"])
        print(f"Waiting for {human['color']}: phase={decision['phase']}, actions={decision['available_actions']}")
        print(f"Decision token: {decision['token']}")
        assert game.get_decision() == decision
        try:
            game.step("turn.end", token=decision["token"])
        except EngineError as error:
            if error.code != "unsupported_action":
                raise
            print("turn.end is not implemented yet; the pending decision is unchanged.")
        else:
            raise RuntimeError("Example expects the initial controller capability set")
        assert game.get_state() == before
        game.step("session.stop", token=decision["token"])
        assert not game.capabilities()["controller_active"]
        assert game.get_state() == before
        print("Controller detached; the full serialized world is unchanged.")


if __name__ == "__main__":
    main()
