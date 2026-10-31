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

"""Reproduce matched Gym benchmarks and equal-budget single/parallel PPO measurements."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def baseline_package(output, ref):
    destination = output / 'baseline-package'
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', ref, 'python/src/fheroes2_env'], cwd=ROOT, text=True).splitlines()
    for name in names:
        if not name.endswith('.py'):
            continue
        target = destination / Path(name).relative_to('python/src')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', 'show', f'{ref}:{name}'], cwd=ROOT))
    if not (destination / 'fheroes2_env/session.py').is_file():
        raise ValueError('Baseline ref does not contain the Python package')
    return destination


def child(output, name, script, args):
    command = [sys.executable, str(ROOT / 'python/examples' / script), '--output', str(output / name), *args]
    print('Starting', name, flush=True)
    environment = dict(os.environ, PYTHONIOENCODING='utf-8')
    with (output / (name + '.log')).open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return read(output / name / 'report.json')


def assert_equivalent(benchmarks):
    baseline = benchmarks['baseline']['signatures']
    for name, report in benchmarks.items():
        keys = ('id', 'actions', 'rewards', 'native_result', 'feature_hashes', 'battle_hashes')
        if report['profile'] == 'full':
            keys += ('full_hashes', 'world_hashes')
        if [{k: r[k] for k in keys} for r in baseline] != [{k: r[k] for k in keys} for r in report['signatures']]:
            raise AssertionError(f'{name} changed observations, rewards, native actions or results')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / ('fheroes2.exe' if os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='f3d8a3405')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--train-steps', type=int, default=8192)
    parser.add_argument('--packed-comparison', action='store_true', help='Also measure non-padding actor computation at 1/2/4 workers')
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / 'build' not in output.parents or output.exists() or not 1 <= args.repeats <= 50 or args.train_steps < 256 or args.train_steps % 256:
        parser.error('Use a fresh build/ directory, 1..50 repeats and training steps divisible by 256')
    output.mkdir(parents=True)
    executable = args.executable.resolve(strict=True)
    frozen = baseline_package(output, args.baseline_ref)
    report = {'completed': False, 'baseline_ref': subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip(),
              'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'benchmarks': {}, 'training': {}}
    common = ['--executable', str(executable)]
    modes = [('baseline', 'full', False, frozen), ('full_fresh', 'full', False, None), ('full_reuse', 'full', True, None),
             ('battle_fresh', 'battle', False, None), ('battle_reuse', 'battle', True, None)]
    for name, profile, reuse, package in modes:
        options = [*common, '--profile', profile, '--repeats', str(args.repeats)]
        if not reuse:
            options += ['--fresh']
        if package:
            options += ['--package-root', str(package)]
        report['benchmarks'][name] = child(output, name, 'benchmark_gym.py', options)
        write(output / 'report.json', report)
    assert_equivalent(report['benchmarks'])
    report['matched_workloads'] = True
    training = [('train_baseline', 'full', False, 1, frozen), ('train_single', 'battle', True, 1, None),
                ('train_two', 'battle', True, 2, None), ('train_four', 'battle', True, 4, None)]
    for name, profile, reuse, workers, package in training:
        options = [*common, '--profile', profile, '--workers', str(workers), '--steps', str(args.train_steps)]
        if not reuse:
            options += ['--fresh']
        if package:
            options += ['--package-root', str(package)]
        report['training'][name] = child(output, name, 'battle_vector.py', options)
        write(output / 'report.json', report)
    if args.packed_comparison:
        for workers in (1, 2, 4):
            name = f'train_packed_{workers}'
            options = [*common, '--profile', 'battle', '--workers', str(workers), '--steps', str(args.train_steps), '--packed']
            report['training'][name] = child(output, name, 'battle_vector.py', options)
            write(output / 'report.json', report)
    old, single = report['training']['train_baseline'], report['training']['train_single']
    report['single_training_bitwise_identical'] = (old['policy_sha256'] == single['policy_sha256']
                                                   and old['workers_status'][0]['reset_manifest_sha256'] == single['workers_status'][0]['reset_manifest_sha256'])
    if not report['single_training_bitwise_identical']:
        raise AssertionError('Optimized single-env training changed the fixed-seed policy or reset sequence')
    if len({r['ppo_updates'] for r in report['training'].values()}) != 1:
        raise AssertionError('Unequal PPO update budgets')
    base = report['benchmarks']['baseline']
    report['speedups'] = {name: {'step': base['median_step_ms'] / b['median_step_ms'],
                               'reset': base['median_reset_ms'] / b['median_reset_ms'],
                               'task_with_resets': b['median_steps_per_second_with_resets'] / base['median_steps_per_second_with_resets']}
                          for name, b in report['benchmarks'].items()}
    report['training_speedups_vs_baseline'] = {name: old['learn_seconds'] / t['learn_seconds'] for name,t in report['training'].items()}
    report['parallel_speedups_vs_single'] = {name: single['learn_seconds'] / t['learn_seconds'] for name,t in report['training'].items()}
    if args.packed_comparison:
        packed_single = report['training']['train_packed_1']['learn_seconds']
        report['packed_parallel_speedups_vs_single'] = {str(n): packed_single / report['training'][f'train_packed_{n}']['learn_seconds'] for n in (1,2,4)}
    report['completed'] = True
    write(output / 'report.json', report)
    print('Completed:', output, flush=True)


if __name__ == '__main__':
    main()
