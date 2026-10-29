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

"""Watch Python control the real headless engine through a Gymnasium loop."""

import argparse
import os
from pathlib import Path

from fheroes2_env.gym_preview import make_preview


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=root / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--save", type=Path, default=root / "build/python-env-baseline/fixtures/other-side-day1.sav")
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--max-steps", type=int, default=12, help="Episode time limit, including rejected actions")
    parser.add_argument("--policy", choices=("walk", "random"), default="walk")
    parser.add_argument("--headless", action="store_true", help="No viewer window; the engine is always headless")
    parser.add_argument("--fps", type=int, default=4)
    parser.add_argument("--seed", type=int, default=123, help="Seed the Python sampler, not the engine RNG")
    args = parser.parse_args()
    # A visible route on the recorded The Other Side day-1 fixture. Random works on other saves too.
    walk = (4, 4, 5, 5, 5, 8, 1, 1, 1, 0, 8, 8)
    with make_preview(executable=args.executable, save=args.save, max_steps=args.max_steps,
                      render_mode=None if args.headless else "human", fps=args.fps) as env:
        obs, info = env.reset(seed=args.seed)
        if args.policy == "walk" and (info["state"]["map"]["name"] != "The Other Side"
                                       or info["state"]["date"]["total_days"] != 1 or info["hero_id"] != 52):
            raise ValueError("Use --policy random for a save other than the recorded The Other Side day-1 fixture")
        print(f"Observation: {obs.shape}, {obs.dtype}; {env.action_space}", flush=True)
        for _ in range(args.steps):
            if env.unwrapped.window_closed:
                break
            action = env.action_space.sample() if args.policy == "random" else walk[info["episode_step"] % len(walk)]
            obs, reward, terminated, truncated, info = env.step(action)
            hero = next(h for h in info["state"]["heroes"] if h["id"] == info["hero_id"])
            events = ", ".join(event["type"] for event in info["events"]) or "-"
            print(f"Day {info['state']['date']['total_days']} | {info['action_name']} | "
                  f"accepted={info['action_accepted']} | position={hero['position']} | events={events}", flush=True)
            if info["rejection"]:
                print(f"  {info['rejection']['message']}", flush=True)
            if env.unwrapped.window_closed:
                break
            if terminated or truncated:
                print(f"Reset: terminated={terminated}, truncated={truncated}", flush=True)
                obs, info = env.reset()


if __name__ == "__main__":
    main()
