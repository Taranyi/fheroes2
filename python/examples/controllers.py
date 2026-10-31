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

"""Run AI–AI, mixed AI/Python or two Python policies on The Other Side."""

import argparse
import os
from pathlib import Path

from fheroes2_env import HeroesSession
from battle import select_action

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("ai-only", "mixed", "python"), default="ai-only")
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--map", dest="map_path", type=Path, default=ROOT / "maps/THEOTHER.MP2")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--steps", type=int, default=200)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    controllers = {
        "ai-only": {1: "builtin_ai", 2: "builtin_ai"},
        "mixed": {1: "builtin_ai", 2: "python"},
        "python": {1: "python", 2: "python"},
    }[args.mode]
    with HeroesSession(args.executable, timeout=120) as game:
        episode = game.reset(map_path=args.map_path, seed=args.seed, controllers=controllers, rule_profiles={1: "ai", 2: "ai"})
        decision = episode["decision"]
        print("Controllers:", controllers, flush=True)
        for index in range(args.steps):
            phase, player, token = decision["phase"], decision["player_id"], decision["token"]
            if phase == "terminal":
                break
            if phase == "simulation":
                result = game.advance_simulation(max_turns=1, token=token)
            elif phase == "adventure":
                # Replace this with agents[player](game.get_state(), decision).
                # The demonstration's two Python policies simply end their adventure turns.
                result = game.end_turn(token=token)
            elif phase == "battle":
                action = select_action(decision["battle"], use_spells=True)
                result = game.battle_action(action["action_id"], token=token)
            elif phase == "choice":
                choice = decision["pending_choice"]
                value = choice["options"][0] if choice["options"] else choice["minimum"]
                result = game.answer_choice(choice["choice_id"], value, token=token)
            else:
                raise RuntimeError(f"Unexpected decision phase: {phase}")
            decision = result["decision"]
            state = game.get_state(include_serialized=False)
            print(f"step={index + 1} day={state['date']['total_days']} phase={phase} actor={player} next={decision['phase']}:{decision['player_id']}", flush=True)
            for participant in state["players"]:
                color = participant["id"]
                heroes = sum(hero["active"] and hero["owner"] == color for hero in state["heroes"])
                print(f"  side={color} controller={participant['controller']} native_control={participant['control']} gold={participant['funds']['gold']} heroes={heroes}", flush=True)
        print("Final phase:", decision["phase"], "outcomes:", decision["simulation"]["outcomes"])
        print("Runtime:", game.runtime_info())


if __name__ == "__main__":
    main()
