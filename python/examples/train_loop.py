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

"""Run complete masked Gym episodes; optionally control a native battle with a simple policy."""

import argparse
import importlib.util
import os
from pathlib import Path

from fheroes2_env.gym_env import make_env

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--save", type=Path)
    source.add_argument("--map", dest="map_path", type=Path)
    parser.add_argument("--battle-demo", action="store_true")
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    if args.battle_demo and (args.save or args.map_path):
        parser.error("--battle-demo supplies its own save")
    setup = {"map_path": args.map_path} if args.map_path else {"save": args.save or ROOT / "build/python-env-baseline/fixtures/other-side-day1.sav"}
    policy = None
    if args.battle_demo:
        setup = {"save": ROOT / "build/python-env-baseline/fixtures/battles-heroes-day1.sav"}
        spec = importlib.util.spec_from_file_location("native_battle_policy", ROOT / "python/examples/battle.py")
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
    with make_env(executable=args.executable, **setup, max_steps=args.max_steps) as env:
        for episode in range(args.episodes):
            obs, info = env.reset(seed=args.seed + episode)
            phases, total_reward = {info["phase"]}, 0.0
            for step in range(args.max_steps):
                action = env.action_space.sample(mask=obs["action_mask"])
                if policy is not None:
                    if step == 0:
                        action = next(i for i, c in enumerate(info["actions"]) if c == {"action": "hero.move", "params": {"hero_id": 52, "x": 32, "y": 25}})
                    elif info["phase"] == "battle":
                        candidate = policy.select_action(info["state"]["battle"], use_spells=True)
                        action = next(i for i, c in enumerate(info["actions"]) if c["params"].get("action_id") == candidate["action_id"])
                    elif info["phase"] == "choice":
                        action = 0
                    else:
                        action = 0  # end turn after returning to adventure
                obs, reward, terminated, truncated, info = env.step(action)
                phases.add(info["phase"])
                total_reward += reward
                if terminated or truncated:
                    print(f"episode={episode + 1} seed={info['seed']} steps={step + 1} reward={total_reward} terminated={terminated} truncated={truncated} phases={sorted(phases)}")
                    break


if __name__ == "__main__":
    main()
