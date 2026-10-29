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

"""Play a native adventure battle from Python, with optional combat spells."""

import argparse
import os
from pathlib import Path

from fheroes2_env import HeroesSession


def select_action(battle, *, use_spells=False):
    """A small policy; all legal moves and combat effects come from C++."""
    actions = battle["actions"]
    if use_spells:
        spell = next((a for a in actions if a["kind"] == "spell" and a["spell_id"] in (3, 26)), None)
        if spell:
            return spell
    for kind in ("shoot", "attack"):
        attack = next((a for a in actions if a["kind"] == kind), None)
        if attack:
            return attack
    enemies = [u for u in battle["units"] if u["alive"] and u["current_color"] != battle["current_color"]]
    moves = [a for a in actions if a["kind"] == "move"]
    if moves and enemies:
        def xy(cell):
            row, col = divmod(cell, battle["width"])
            return col + 0.5 * (row % 2), row * 0.866

        def distance(action):
            x, y = xy(action["destination"])
            return min((x - xy(u["head"])[0]) ** 2 + (y - xy(u["head"])[1]) ** 2 for u in enemies)

        return min(moves, key=distance)
    return next(a for a in actions if a["kind"] == "skip")


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=root / "build/python-env-baseline/fixtures/battles-melee-day1.sav")
    parser.add_argument("--spells", action="store_true")
    args = parser.parse_args()
    with HeroesSession(root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"), timeout=60) as game:
        game.load_save(args.save)
        decision = game.start_session(1)
        result = game.move_hero(52, 32, 25, token=decision["token"])
        for _ in range(500):
            decision = result["decision"]
            if decision["phase"] == "battle":
                battle = decision["battle"]
                action = select_action(battle, use_spells=args.spells)
                print("Round", battle["round"], "unit", battle["current_unit_uid"], "Python action:", action, flush=True)
                result = game.battle_action(action["action_id"], token=decision["token"])
            elif decision["phase"] == "choice":
                choice = decision["pending_choice"]
                value = choice["options"][0]
                result = game.answer_choice(choice["choice_id"], value, token=decision["token"])
            else:
                break
        else:
            raise RuntimeError("Policy exceeded the demonstration's decision limit")
        print("Final phase:", result["decision"]["phase"])
        print("Results:", [e for e in result["events"] if e["type"] == "battle_completed"])
        hero = next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"] == 52)
        print("Hero:", {key: hero[key] for key in ("active", "level", "experience", "army", "spell_points")})
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
