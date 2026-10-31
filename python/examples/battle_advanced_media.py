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

"""Verify and present local advanced-battle recordings without training or uploading."""

import argparse
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import tempfile

import imageio.v2 as imageio
import numpy as np

import battle_rl as base


def checked_run(path):
    folder = path.resolve(strict=True)
    if base.ROOT / 'build' not in folder.parents:
        raise ValueError('Media outputs must stay inside ignored repository build/')
    report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
    plan = json.loads((folder / 'plan.json').read_text(encoding='utf-8'))
    base.require(report['completed'] and not report['pilot'], 'A completed evaluation is required')
    canonical_plan = deepcopy(plan)
    # Spell IDs are integer mapping keys in the schema written by the experiment.
    canonical_plan['spells'] = {int(k): v for k, v in plan['spells'].items()}
    base.require(base.canonical_hash(canonical_plan) == report['plan_sha256'], 'Plan fingerprint mismatch')
    for relative, expected in report['identity']['files_sha256'].items():
        base.require(hashlib.sha256((base.ROOT / relative).read_bytes()).hexdigest() == expected, f'Experiment source changed: {relative}')
    for mode, video in report['videos'].items():
        original = {r['id']: r for r in json.loads((folder / f'test-{mode}.json').read_text())}
        for row in video['cases']:
            other = original[row['id']]
            base.require((row['trace'], row['native_result']) == (other['trace'], other['native_result']), 'Render replay mismatch')
    return folder, report, plan


def comparisons(folder, report, plan):
    directory = folder / 'videos'
    verification, pairs = [], []
    controls = [mode for mode in ('no_spells', 'rule', 'uniform') if mode in report['videos']]
    for case_id in plan['video_cases']:
        context = case_id.split('/')[1]
        prefix = case_id.replace('/', '-')
        for control in controls:
            paths = [directory / f'{prefix}-{mode}.mp4' for mode in (control, 'greedy')]
            readers = [imageio.get_reader(str(path)) for path in paths]
            try:
                counts = [r.count_frames() for r in readers]
                fps = readers[0].get_meta_data()['fps']
                base.require(all(count >= 6 for count in counts) and fps == readers[1].get_meta_data()['fps'], 'Invalid video timing')
                output = directory / f'compare-{context}-{control}-vs-ppo.mp4'
                latest = [None, None]
                with imageio.get_writer(str(output), fps=fps, codec='libx264', macro_block_size=2, ffmpeg_log_level='error') as writer:
                    for n in range(max(counts)):
                        for i, reader in enumerate(readers):
                            if n < counts[i]:
                                latest[i] = reader.get_data(n).copy()
                        frame = np.concatenate(latest, axis=1)
                        writer.append_data(frame)
                with imageio.get_reader(str(output)) as reader:
                    base.require(reader.count_frames() == max(counts), 'Comparison lost frames')
                    base.require(reader.get_data(max(counts) - 1).shape == frame.shape, 'Comparison geometry mismatch')
                verification.append({'file': output.name, 'frames': max(counts), 'seconds': max(counts) / fps,
                                     'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
                pairs.append((context, control, output.name))
            finally:
                for reader in readers:
                    reader.close()
    index = '''<!doctype html><html lang="hu"><meta charset="utf-8"><title>fheroes2 – összetett csata-RL</title>
<style>body{font:17px system-ui;background:#14212d;color:#eee;max-width:1300px;margin:30px auto;padding:20px}video{width:100%;border-radius:8px}h2{margin-top:40px}a{color:#9ddcd2}code{color:#b9dce8}</style>
<h1>Összetett csata-RL: varázslás és ostrom</h1>
<p>Jobbra a tanított PPO, balra az adott kontroll. Azonos kezdőkonfiguráció és seed.</p>
<p>A nézet natív döntési pillanatképekből áll: másodpercenként egy Python-döntés. A két oldal eltérő natív körben járhat;
a rövidebb videó végképe megmarad. Ez nem a normál játék folyamatos animációja.</p>'''
    index += f'<p>Kizárólag validáció alapján kiválasztott modell: <code>{html.escape(str(report["selected"]["model"]))}</code>.</p>'
    labels = {'no_spells': 'Ugyanez a modell, letiltott varázslatokkal', 'rule': 'Egyszerű szabályalapú vezérlő varázslással', 'uniform': 'Maszkos véletlen, menekülés nélkül'}
    for control in controls:
        index += f'<h1>Balra: {labels[control]}</h1>'
        for context, mode, filename in pairs:
            if mode == control:
                index += f'<h2>{context}</h2><video controls preload="metadata" src="{filename}"></video>'
    index += '</html>'
    (directory / 'index.html').write_text(index, encoding='utf-8')
    (directory / 'media-verification.json').write_text(json.dumps({'source_fingerprints_match': True, 'rendered_traces_match_test': True,
                                                                  'comparisons_decoded': verification}, indent=2) + '\n', encoding='utf-8')


def unseen_videos(folder, report, plan, executable):
    import battle_advanced as advanced
    advanced.torch.set_num_threads(1)
    advanced.torch.set_num_interop_threads(1)
    executable = executable.resolve(strict=True)
    base.require(hashlib.sha256(executable.read_bytes()).hexdigest() == report['identity']['executable_sha256'], 'Native binary changed')
    model = advanced.previous.load_model(folder / report['selected']['model'])
    # Fixed IDs, independent of results: one novel-army case per context.
    manifest = [c for c in plan['ood'] if c['profile'] == 0 and c['variant'] == 1]
    target = folder / 'unseen'
    target.mkdir(exist_ok=True)
    extra_report = deepcopy(report)
    extra_report['videos'] = {}
    with tempfile.TemporaryDirectory(dir=target) as directory:
        with advanced.AdvancedTask(executable, directory, render=True) as env:
            for mode in ('greedy', 'no_spells'):
                score, rows = advanced.evaluate(env, manifest, model=model, mode=mode, video_directory=target / 'videos')
                reference = {r['id']: r for r in json.loads((folder / f'ood-{mode}.json').read_text())}
                base.require(all((r['trace'], r['native_result']) == (reference[r['id']]['trace'], reference[r['id']]['native_result']) for r in rows), 'Unseen render replay mismatch')
                extra_report['videos'][mode] = {'score': score, 'cases': rows}
    base.write_json(target / 'recording.json', {'selection': 'Fixed profile=0 / variant=1, one per context; no outcome filtering',
                                               'videos': extra_report['videos']})
    extra_plan = dict(plan, video_cases=[c['id'] for c in manifest])
    comparisons(target, extra_report, extra_plan)
    index = folder / 'videos/index.html'
    index.write_text(index.read_text(encoding='utf-8').replace('</html>', '<h1>Ismeretlen seregek és új ostromfajok</h1><p><a href="../unseen/videos/index.html">Külön általánosítási videók</a></p></html>'), encoding='utf-8')


def plot(folder, report, plan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout='constrained')
    for run in report['runs']:
        xs = [c['steps'] for c in run['checkpoints']]
        ys = [c['validation']['win_rate'] for c in run['checkpoints']]
        axes[0, 0].plot(xs, ys, marker='o', label=f'Seed {run["seed"]}')
    axes[0, 0].axvspan(0, plan['warmup_steps'], color='gray', alpha=.12, label='Damage-only field/naval warmup')
    axes[0, 0].axhline(report.get('validation_baselines', {}).get('uniform', {}).get('win_rate', 0), color='gray', linestyle=':', label='Random validation')
    axes[0, 0].set(title='Greedy validation; selection after warmup', xlabel='Training decisions per seed', ylabel='Win rate', ylim=(0, 1.06))
    axes[0, 0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0, 0].legend(fontsize=8)
    modes = ('uniform', 'rule_no_spells', 'rule', 'greedy', 'no_spells', 'stochastic')
    labels = ('Random', 'Rule\nno magic', 'Rule', 'PPO', 'PPO\nno magic', 'PPO\nsampled')
    x = np.arange(len(modes))
    for split, offset, color in (('test', -.2, '#287ead'), ('ood', .2, '#b78c3d')):
        values = [report['evaluation'][split][mode]['win_rate'] for mode in modes]
        axes[0, 1].bar(x + offset, values, width=.38, color=color, label='Held-out seeds' if split == 'test' else 'Unseen armies / siege races')
    axes[0, 1].set(title='Separate test and generalization', xticks=x, xticklabels=labels, ylim=(0, 1.1), ylabel='Win rate')
    axes[0, 1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0, 1].legend(fontsize=8)
    contexts = ('field', 'naval', 'assault', 'defense')
    for mode, offset, color in (('greedy', -.2, '#287ead'), ('no_spells', .2, '#999999')):
        scores = report['evaluation']['test'][mode]['by_context']
        values = [scores[c]['wins'] / scores[c]['episodes'] for c in contexts]
        axes[1, 0].bar(np.arange(4) + offset, values, width=.38, color=color, label='PPO' if mode == 'greedy' else 'Same PPO, spells disabled')
    axes[1, 0].set(title='Test by battle context', xticks=np.arange(4), xticklabels=contexts, ylim=(0, 1.1), ylabel='Win rate')
    axes[1, 0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1, 0].legend(fontsize=8)
    ids = list(plan['spells'])
    names = [plan['spells'][spell] for spell in ids]
    for split, offset, color in (('test', -.2, '#287ead'), ('ood', .2, '#b78c3d')):
        scores = report['evaluation'][split]['greedy']
        values = [scores['spell_casts'].get(spell, 0) / scores['episodes'] for spell in ids]
        axes[1, 1].bar(np.arange(len(ids)) + offset, values, width=.38, color=color, label=split)
    axes[1, 1].set(title='What the selected policy actually casts', xticks=np.arange(len(ids)), xticklabels=names, ylabel='Casts per episode')
    axes[1, 1].tick_params(axis='x', labelrotation=25)
    axes[1, 1].legend(fontsize=8)
    fig.suptitle('Native fheroes2 · mixed three-stack armies · spells · attacking and defending sieges', fontsize=15)
    fig.supxlabel('Frozen test manifests; models selected only on validation. Snapshot videos and all generated artifacts remain local.', fontsize=9)
    fig.savefig(folder / 'learning.png', dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=base.ROOT / 'build/python-env-advanced/final')
    parser.add_argument('--plot', action='store_true', help='Also plot results; requires optional matplotlib')
    parser.add_argument('--unseen-videos', action='store_true', help='Also record four predeclared novel-army cases')
    parser.add_argument('--executable', type=Path, default=base.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    args = parser.parse_args()
    folder, report, plan = checked_run(args.run)
    comparisons(folder, report, plan)
    if args.unseen_videos:
        unseen_videos(folder, report, plan, args.executable)
    if args.plot:
        plot(folder, report, plan)
    print(folder / 'videos/index.html')


if __name__ == '__main__':
    main()
