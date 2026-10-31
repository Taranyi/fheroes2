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

"""Start a configured native battle directly from Python, without a map or save."""

import argparse
import json
import os
from pathlib import Path

from fheroes2_env import HeroesSession
from battle import select_action

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--scenario", choices=("field", "siege", "naval"), default="field")
    parser.add_argument("--attacker", choices=("python", "builtin_ai"), default="python")
    parser.add_argument("--defender", choices=("python", "builtin_ai"), default="builtin_ai")
    parser.add_argument("--config", type=Path, help="Use your own JSON battle configuration")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--output", type=Path, help="Save native RGB battle frames as PPM")
    parser.add_argument("--gym", action="store_true", help="Run the same battle through the masked Gym loop")
    args = parser.parse_args()
    config = {
        "terrain": "water" if args.scenario == "naval" else "grass",
        "max_rounds": 100,
        "attacker": {"army": [{"monster_id": 3, "count": 30}], "controller": args.attacker,
                     "hero": {"attack": 4, "defense": 3, "power": 5, "knowledge": 5,
                              "spells": [15, 11, 48], "spell_points": 100}},
        "defender": {"army": [{"monster_id": 1, "count": 30}], "controller": args.defender,
                     "hero": {"id": 2, "defense": 2}},
    }
    if args.scenario == "siege":
        config["siege"] = {"race": "knight", "fortification": True, "moat": True}
    if args.config:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        config["capture_final_frame"] = True
    data_env = dict(os.environ, FHEROES2_DATA=os.environ.get("FHEROES2_DATA", str(ROOT)))

    def write_frame(frame, name):
        path = args.output / name
        path.write_bytes(f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii") + frame.pixels)
        print("Native RGB frame:", path)

    if args.gym:
        from fheroes2_env.gym_env import HeroesEnv
        with HeroesEnv(executable=args.executable, battle_config=config, env=data_env,
                       render_mode="rgb_array" if args.output else None) as env:
            obs, info = env.reset(seed=args.seed)
            for _ in range(10000):
                if info["phase"] == "terminal":
                    break
                action = env.action_space.sample(mask=obs["action_mask"])
                obs, reward, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    print("Gym reward=", reward, "terminated=", terminated, "truncated=", truncated)
                    break
            print("Native result:", info["state"]["standalone_battle"]["result"])
            if args.output:
                image = env.render()
                height, width, _ = image.shape
                path = args.output / "gym-final.ppm"
                path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + image.tobytes())
                print("Native RGB frame:", path)
        return

    with HeroesSession(args.executable, timeout=60, env=data_env) as game:
        episode = game.reset(battle_config=config, seed=args.seed)
        decision = episode["decision"]
        if args.output and decision["phase"] == "battle":
            write_frame(game.render(view="battle"), "initial.ppm")
        while decision["phase"] == "battle":
            action = select_action(decision["battle"], use_spells=True)
            print("Python participant", decision["player_id"], "round", decision["battle"]["round"], "action", action["kind"])
            decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
        print("Native result:", game.get_state(include_serialized=False)["standalone_battle"]["result"])
        if args.output:
            write_frame(game.render(view="battle"), "final.ppm")
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
