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

"""Portable real-engine smoke test using local or verified demo assets; no media files saved."""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from fheroes2_env.battle_env import BattleEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    executable, data = args.executable.resolve(strict=True), args.data.resolve(strict=True)
    config = {'terrain': 'grass', 'max_rounds': 20,
              'attacker': {'army': [{'monster_id': 3, 'count': 20}], 'controller': 'python'},
              'defender': {'army': [{'monster_id': 1, 'count': 10}], 'controller': 'builtin_ai'}}
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        environment = dict(os.environ, FHEROES2_DATA=str(data), APPDATA=directory,
                           XDG_CONFIG_HOME=directory, XDG_DATA_HOME=directory,
                           SDL_VIDEODRIVER='nonexistent-driver', SDL_AUDIODRIVER='nonexistent-driver')
        if os.name != 'nt':
            environment['HOME'] = directory
        for terrain in ('grass', 'water'):
            setup = deepcopy(config)
            setup['terrain'] = terrain
            with BattleEnv(executable=executable, battle_config=setup, env=environment,
                           reuse_process=True, render_mode='rgb_array', width=160, height=120) as env:
                initial, _ = env.reset(seed=123)
                pid = env._session.pid
                obs, _ = env.reset(seed=123)
                if pid != env._session.pid or any(not np.array_equal(initial[k], obs[k]) for k in obs):
                    raise RuntimeError('Same-seed process reuse changed observations')
                before = env.world_snapshot()
                frame = env.render()
                if frame.shape != (120, 160, 3) or frame.dtype != np.uint8 or not np.any(frame):
                    raise RuntimeError('Invalid RGB frame')
                if env.world_snapshot() != before:
                    raise RuntimeError('Rendering changed game state')
                terminated = truncated = False
                for steps in range(1, 161):
                    action = int(np.flatnonzero(obs['action_mask'])[0])
                    obs, reward, terminated, truncated, info = env.step(action)
                    if terminated or truncated:
                        break
                if not (terminated or truncated):
                    raise RuntimeError('Episode exceeded its finite horizon')
                runtime = env._session.runtime_info()
                if runtime['video_initialized'] or runtime['audio_initialized']:
                    raise RuntimeError('Headless test initialized presentation')
                process = env._session._process
                rows.append({'terrain': terrain, 'steps': steps, 'reward': reward,
                             'terminated': terminated, 'truncated': truncated, 'runtime': runtime})
            if process.poll() != 0:
                raise RuntimeError('Native process was not closed cleanly')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'passed': True, 'cases': rows}, indent=2) + '\n')
    print('Native headless Gym/reset/RGB/cleanup checks passed')


if __name__ == '__main__':
    main()
