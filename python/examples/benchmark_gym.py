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

"""Matched native workloads for the full and battle-only Gym profiles; output stays local."""

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
import fheroes2_env
import battle_vector as vector
from battle_vector import advanced

BATTLE_KEYS = ('battle', 'battle_units', 'battle_unit_mask', 'battle_effects', 'battle_board', 'battle_commanders', 'actions', 'action_mask')


def arrays_hash(obs, keys):
    digest = hashlib.sha256()
    for key in sorted(keys):
        array = obs[key]
        digest.update(key.encode())
        digest.update(str((array.shape, str(array.dtype))).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def episode(env, case, *, verify=False):
    start = perf_counter()
    obs, info = env.reset(seed=case['seed'], options={'battle_config': case['config']})
    reset_seconds = perf_counter() - start
    feature_hashes, raw_hashes, full_hashes, world_hashes, actions, rewards, times = [], [], [], [], [], [], []
    while True:
        if verify:
            feature_hashes.append(arrays_hash({'features': obs}, ('features',)))
            raw_hashes.append(arrays_hash(env.raw_obs, BATTLE_KEYS))
        if verify and 'global' in env.raw_obs:
            full_hashes.append(arrays_hash(env.raw_obs, env.raw_obs.keys()))
            state = dict(info['state'])
            state.pop('state_version', None)
            if state.get('pending_choice') is not None:
                state['pending_choice'] = dict(state['pending_choice'])
                state['pending_choice'].pop('choice_id', None)  # per-process cursor, not gameplay state
            world_hashes.append(advanced.base.canonical_hash(state))
        action = advanced.choose(env, obs, 'rule', np.random.default_rng(42))
        actions.append(int(env.raw_obs['actions'][action, advanced.base.A['action_id']]))
        start = perf_counter()
        obs, reward, terminated, truncated, info = env.step(action)
        times.append(perf_counter() - start)
        rewards.append(reward)
        if terminated or truncated:
            if verify:
                raw_hashes.append(arrays_hash(env.raw_obs, BATTLE_KEYS))
            result = info.get('battle_result') or info['state']['standalone_battle']['result']
            break
    return {'id': case['id'], 'actions': actions, 'rewards': rewards, 'native_result': result,
            'feature_hashes': feature_hashes, 'battle_hashes': raw_hashes, 'full_hashes': full_hashes, 'world_hashes': world_hashes,
            'reset_seconds': reset_seconds, 'step_seconds': times}


def measure(executable, output, *, profile='battle', reuse=True, repeats=5):
    manifest = [c for c in advanced.cases('validation') if c['profile'] == 0]
    rounds, reference = [], None
    with tempfile.TemporaryDirectory(dir=output) as directory:
        with vector.TrainingTask(executable, directory, profile=profile, reuse_process=reuse) as env:
            episode(env, manifest[0])  # excluded filesystem/allocator warmup
            reference_rows = [episode(env, case, verify=True) for case in manifest]
            reference = [{k: r[k] for k in ('id', 'actions', 'rewards', 'native_result', 'feature_hashes', 'battle_hashes', 'full_hashes', 'world_hashes')} for r in reference_rows]
            for repeat in range(repeats):
                start = perf_counter()
                rows = [episode(env, case) for case in manifest]
                wall = perf_counter() - start
                keys = ('id', 'actions', 'rewards', 'native_result')
                advanced.base.require([{k: r[k] for k in keys} for r in rows] == [{k: r[k] for k in keys} for r in reference], 'Native replay changed')
                steps = [t for r in rows for t in r['step_seconds']]
                resets = [r['reset_seconds'] for r in rows]
                rounds.append({'repeat': repeat, 'steps': len(steps), 'step': advanced.base.timing(steps), 'reset': advanced.base.timing(resets),
                               'combined_reset_step_seconds': sum(steps) + sum(resets),
                               'wall_seconds_including_policy_and_resets': wall,
                               'steps_per_second_with_resets': len(steps) / wall})
                print(profile, reuse, repeat, rounds[-1]['step']['mean_ms'], rounds[-1]['reset']['mean_ms'], flush=True)
            status = env.worker_status()
    package = Path(fheroes2_env.__file__).resolve().parent
    return {'profile': profile, 'reuse_process': reuse, 'repeats': repeats, 'cases_per_repeat': len(manifest), 'rounds': rounds,
            'median_step_ms': float(np.median([r['step']['mean_ms'] for r in rounds])),
            'median_reset_ms': float(np.median([r['reset']['mean_ms'] for r in rounds])),
            'median_steps_per_second_with_resets': float(np.median([r['steps_per_second_with_resets'] for r in rounds])),
            'signatures': reference, 'status': status, 'actual_package': str(package),
            'package_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.glob('*.py'))},
            'identity': advanced.base.experiment_identity(executable)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, parents=[_bootstrap])
    parser.add_argument('--executable', type=Path, default=advanced.base.ROOT / ('fheroes2.exe' if advanced.base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=('full', 'battle'), default='battle')
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    output = args.output.resolve()
    if advanced.base.ROOT / 'build' not in output.parents or output.exists() or not 1 <= args.repeats <= 50:
        parser.error('Choose a fresh ignored build/ directory and 1..50 repeats')
    output.mkdir(parents=True)
    result = measure(args.executable.resolve(strict=True), output, profile=args.profile, reuse=not args.fresh, repeats=args.repeats)
    advanced.base.write_json(output / 'report.json', result)


if __name__ == '__main__':
    main()
