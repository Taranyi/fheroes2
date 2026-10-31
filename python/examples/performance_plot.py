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

"""Plot local run_performance reports; requires optional matplotlib."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    root = Path(__file__).resolve().parents[2]
    if root / 'build' not in directory.parents:
        parser.error('Plots must remain under build/')
    report = json.loads((directory / 'report.json').read_text())
    if not report['completed'] or not report['matched_workloads']:
        parser.error('A completed matched benchmark is required')
    training = dict(report['training'])
    for workers in (1, 2, 4):
        name = f'train_packed_{workers}'
        path = directory / name / 'report.json'
        if name not in training and path.exists():
            training[name] = json.loads(path.read_text())
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout='constrained')
    fig.suptitle('fheroes2 Gym / PPO — matched CPU measurements', fontsize=17)
    labels = ['Old full', 'Full fresh', 'Full reuse', 'Battle fresh', 'Battle reuse']
    colors = ['#87949f', '#3e789c', '#3e789c', '#219c88', '#219c88']
    for ax, field, operation in zip(axes[0], ('median_step_ms', 'median_reset_ms'), ('step', 'reset')):
        values = [b[field] for b in report['benchmarks'].values()]
        ranges = [[r[operation]['mean_ms'] for r in b['rounds']] for b in report['benchmarks'].values()]
        errors = np.array([[v - min(rs), max(rs) - v] for v, rs in zip(values, ranges)]).T
        bars = ax.bar(labels, values, color=colors, yerr=errors, capsize=4)
        ax.bar_label(bars, fmt='%.1f', padding=4)
        ax.set(title=f'Gym {operation}: median of 5 round means', ylabel='milliseconds (lower is faster)')
        ax.tick_params(axis='x', rotation=15)
        ax.text(.02, .95, 'Whiskers: min–max, not confidence intervals', transform=ax.transAxes, va='top', fontsize=9)
        ax.set_ylim(0, max(max(rs) for rs in ranges) * 1.2)
    labels = ['Old 1', 'Fast 1', 'Fast 2', 'Fast 4', 'Packed 1', 'Packed 2', 'Packed 4'][:len(training)]
    x = np.arange(len(training))
    learn = [t['learn_seconds'] for t in training.values()]
    overhead = [t['startup_seconds'] + t['close_seconds'] for t in training.values()]
    ax = axes[1, 0]
    bars = ax.bar(x, learn, color='#3e789c', label='PPO learn()')
    ax.bar(x, overhead, bottom=learn, color='#e2b256', label='Startup + close')
    ax.bar_label(bars, fmt='%.1f', padding=4, fontsize=9)
    ax.set(xticks=x, xticklabels=labels, ylabel='seconds (lower is faster)', title='8192 decisions / 192 PPO epochs per run')
    ax.tick_params(axis='x', rotation=20)
    ax.legend()
    ax = axes[1, 1]
    bars = ax.bar(x, [t['validation']['wins'] for t in training.values()], color='#219c88')
    ax.bar_label(bars, fmt='%.0f', padding=4)
    ax.set(xticks=x, xticklabels=labels, ylim=(0, 26), ylabel='wins / 24', title='Validation sanity check — one seed per configuration')
    ax.tick_params(axis='x', rotation=20)
    fig.supxlabel('Full: complete world data. Battle: smaller explicit API, same 512 × 97 policy input.\n'
                  'Training excludes evaluation, ZIP save and parent Python imports. Packed uses float32 tolerance.', fontsize=10)
    fig.savefig(directory / 'performance.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
