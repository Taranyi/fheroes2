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

"""Run a real treasure/level-up choice chain without a game window."""

import os
from pathlib import Path

from fheroes2_env import HeroesSession


def main():
    root = Path(__file__).resolve().parents[2]
    executable = root / ("fheroes2.exe" if os.name == "nt" else "fheroes2")
    save = root / "build/python-env-baseline/fixtures/choices-chest-day1.sav"
    with HeroesSession(executable) as game:
        game.load_save(save)
        decision = game.start_session(1)
        result = game.move_hero(52, 32, 25, token=decision["token"])
        while result["decision"]["phase"] == "choice":
            decision = result["decision"]
            choice = decision["pending_choice"]
            print("Python decision:", choice, flush=True)
            # 0 = experience at a chest; then select the first offered secondary skill.
            value = 0 if choice["kind"] == "treasure.gold_or_experience" else choice["options"][0]
            result = game.answer_choice(choice["choice_id"], value, token=decision["token"])
        state = game.get_state(include_serialized=False)
        hero = next(h for h in state["heroes"] if h["id"] == 52)
        print("Final phase:", result["decision"]["phase"], "level:", hero["level"], "experience:", hero["experience"])
        print("Skills:", hero["secondary_skills"])
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
