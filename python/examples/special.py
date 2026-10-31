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

"""Exercise native special objects and save Oracle/View World snapshots as PPM."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "build/python-env-baseline/fixtures"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--output", type=Path, default=ROOT / "build/python-env-special-views")
    args = parser.parse_args()
    manifest = FIXTURES / "special-objects.json"
    if not manifest.is_file():
        parser.error("Prepare fixtures with script/windows/python-env-artifact-fixture.ps1 -ExpansionOnly")
    records = json.loads(manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    data_env = dict(os.environ, FHEROES2_DATA=os.environ.get("FHEROES2_DATA", str(ROOT)))
    with HeroesSession(args.executable, timeout=60, env=data_env) as game:
        def reset(name):
            record = next(r for r in records if r["name"] == name)
            decision = game.reset(save=FIXTURES / record["save"], seed=123,
                                  controllers={1: "python", 2: "python"})["decision"]
            return record, decision

        def finish(result):
            for _ in range(100):
                decision = result["decision"]
                if decision["phase"] != "choice":
                    return decision
                choice = decision["pending_choice"]
                if choice.get("input_type") == "text":
                    # This is the demonstration fixture's answer; the API never reveals solutions.
                    print("Sphinx asks:", choice["prompt"])
                    result = game.answer_text(choice["choice_id"], "human", token=decision["token"])
                else:
                    value = choice["options"][0] if choice["options"] else choice["minimum"]
                    result = game.answer_choice(choice["choice_id"], value, token=decision["token"])
            raise RuntimeError("Demonstration choice limit exceeded")

        def save_frame(view, filename):
            frame = game.render(view=view, width=640, height=640 if view == "world" else 480)
            path = args.output / filename
            path.write_bytes(f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii") + frame.pixels)
            print("Native RGB snapshot:", path)

        for name in ("Sphinx", "Trading Post", "Event", "Stone Liths", "Whirlpool", "Hut of the Magi", "Magellan's Maps", "Oracle"):
            record, decision = reset(name)
            index = record["target_index"]
            decision = finish(game.move_hero(52, index % 36, index // 36, token=decision["token"]))
            state = game.get_state(include_serialized=False)
            hero = next(h for h in state["heroes"] if h["id"] == 52)
            print(name, "hero position=", hero["position"], "gold=", state["players"][0]["funds"]["gold"])
            if name == "Trading Post":
                quote = next(q for q in game.get_trading_post_options(52)["trades"]
                             if q["resource_from"] == 64 and q["resource_to"] == 1 and q["max_lots"])
                game.trade_at_post(52, 64, 1, 1, token=decision["token"])
                print("Exchanged gold for wood at native rate:", quote)
            if name == "Oracle":
                print("Oracle participants:", game.get_information_view()["players"])
                save_frame("oracle", "oracle.ppm")

        for spell_id in range(49, 55):
            _, decision = reset("Oracle")
            game.cast_spell(52, spell_id, token=decision["token"])
            information = game.get_information_view()
            print("View World", spell_id, "mode=", information["mode"], "markers=", len(information["markers"]))
            save_frame("world", f"world-{spell_id}.ppm")
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
