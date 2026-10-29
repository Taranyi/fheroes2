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

"""Upgrade/dismiss stacks, buy a spell book and voluntarily dismiss a hero through native rules."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import EngineError, HeroesSession


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

        print("Initial army options:", json.dumps(game.get_army_options("hero", 52)))
        act(game.build_castle, castle_id, 1 << 26)  # Upgraded Graveyard enables Zombie -> Mutant Zombie.
        act(game.upgrade_troop, {"kind": "hero", "id": 52, "slot": 1})
        act(game.dismiss_troop, {"kind": "hero", "id": 52, "slot": 0})
        try:
            game.dismiss_troop({"kind": "hero", "id": 52, "slot": 1}, token=decision["token"])
        except EngineError as error:
            if error.code != "illegal_action":
                raise
            print("Expected last-stack protection:", error)
        act(game.move_hero, 52, 32, 25)
        act(game.refresh_hero_offers, castle_id)
        act(game.hire_hero, castle_id, 12)  # Offered Jojosh starts without a book.
        act(game.buy_spell_book, 12)
        act(game.dismiss_hero, 52)  # Roxana is outside the castle; the visitor cannot be dismissed.
        after = game.get_state(include_serialized=False)
        human = next(p for p in after["players"] if p["id"] == 1)
        jojosh = next(h for h in after["heroes"] if h["id"] == 12)
        print("Own hero IDs:", human["hero_ids"], "funds:", human["funds"], "day:", after["date"]["total_days"])
        print("Jojosh has book:", jojosh["has_spell_book"], "known spells:", jojosh["spells"])
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
