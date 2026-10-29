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

"""Buy an offered hero and trade resources through the real headless engine."""

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
            raise ValueError("This walkthrough uses the recorded The Other Side day-1 fixture")
        decision = game.start_session(1)
        castle_id = next(player for player in state["players"] if player["id"] == 1)["castle_ids"][0]
        print("Initial hero offers:", json.dumps(game.get_castle_options(castle_id)["hero_hiring"]))
        # Refreshing offers may change the native RNG/state, so it is an explicit token-checked action.
        decision = game.refresh_hero_offers(castle_id, token=decision["token"])["decision"]
        # Roxana occupies the visitor slot. Leave the castle using the real movement rules.
        decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
        offers = game.get_castle_options(castle_id)["hero_hiring"]
        hero = next(offer for offer in offers["offers"] if offer["available"])
        result = game.hire_hero(castle_id, hero["hero_id"], token=decision["token"])
        decision = result["decision"]
        print("Hired:", json.dumps(result["events"]))
        # Native IDs: wood=1, gold=64. Lots are exact quote units, not arbitrary receive amounts.
        market = game.get_castle_options(castle_id)["market"]
        quote = next(q for q in market["trades"] if q["resource_from"] == 1 and q["resource_to"] == 64)
        print("Wood -> gold quote:", json.dumps(quote))
        result = game.trade_resources(castle_id, 1, 64, 2, token=decision["token"])
        print("Traded:", json.dumps(result["events"]))
        after = game.get_state(include_serialized=False)
        human = next(player for player in after["players"] if player["id"] == 1)
        print("Own hero IDs:", human["hero_ids"], "funds:", human["funds"], "day:", after["date"]["total_days"])
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
