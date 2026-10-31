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

"""Small matched full-world Gym benchmark on an existing read-only adventure save."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument('--package-root', type=Path)
_early, _ = _bootstrap.parse_known_args()
if _early.package_root:
    sys.path.insert(0, str(_early.package_root.resolve()))

import numpy as np
from fheroes2_env.gym_env import HeroesEnv
import fheroes2_env
import battle_rl as base


def digest(obs):
    result = hashlib.sha256()
    for key, array in sorted(obs.items()):
        result.update(key.encode())
        result.update(array.tobytes())
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, parents=[_bootstrap])
    parser.add_argument('--executable', type=Path, default=base.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--save', type=Path, default=base.ROOT / 'build/python-env-baseline/fixtures/other-side-day1.sav')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    output, save = args.output.resolve(), args.save.resolve(strict=True)
    if base.ROOT / 'build' not in output.parents or output.exists() or not 1 <= args.repeats <= 50:
        parser.error('Use a fresh build/ directory and 1..50 repeats')
    output.mkdir(parents=True)
    rounds = []
    save_hash = hashlib.sha256(save.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(dir=output) as directory:
        with HeroesEnv(executable=args.executable, save=save, env=base.engine_environment(directory), timeout=60) as env:
            env.reset(seed=90000)  # excluded warmup
            for repeat in range(args.repeats):
                begin = perf_counter()
                obs, info = env.reset(seed=90000 + repeat)
                reset = perf_counter() - begin
                signatures, times = [digest(obs)], []
                for _ in range(3):
                    base.require(obs['action_mask'][0], 'First native action is not legal')
                    begin = perf_counter()
                    obs, reward, terminated, truncated, info = env.step(0)
                    times.append(perf_counter() - begin)
                    state = dict(info['state'])
                    state.pop('state_version', None)
                    signatures.append((digest(obs), base.canonical_hash(state), reward, terminated, truncated))
                    if terminated or truncated:
                        break
                rounds.append({'repeat': repeat, 'reset_seconds': reset, 'step_seconds': times, 'signatures': signatures})
                print(repeat, reset, times, flush=True)
    base.require(hashlib.sha256(save.read_bytes()).hexdigest() == save_hash, 'Input save changed')
    package = Path(fheroes2_env.__file__).resolve().parent
    base.write_json(output / 'report.json', {'rounds': rounds, 'save_sha256': save_hash,
                                            'median_reset_ms': float(np.median([r['reset_seconds'] for r in rounds])) * 1000,
                                            'median_step_ms': float(np.median([np.mean(r['step_seconds']) for r in rounds])) * 1000,
                                            'actual_package': str(package),
                                            'package_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')}})


if __name__ == '__main__':
    main()
