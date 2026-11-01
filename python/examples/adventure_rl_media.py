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


"""Record verified native adventure replays and a local comparison gallery."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import tempfile

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

import adventure_rl as experiment
import adventure_task as task
import battle_rl as base


class Recording:
    def __init__(self, path, label):
        self.path, self.label, self.frames = path, label, 0
        self.writer = imageio.get_writer(str(path), fps=12, codec='libx264', macro_block_size=2, ffmpeg_log_level='error')
        self.last = None

    def __call__(self, env, command):
        phase = env.decision['phase']
        center = None
        hid = command['params'].get('hero_id')
        hero = next((h for h in env.state['heroes'] if h['active'] and h['id'] == hid), None)
        if hero:
            center = (hero['position']['x'], hero['position']['y'])
        frame = env.game.render(view='battle' if phase == 'battle' else 'adventure', center=center, width=640, height=480)
        canvas = Image.new('RGB', (640, 560), '#14212d')
        canvas.paste(Image.fromarray(frame.to_numpy()), (0, 80))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=16)
        m = env.current_metrics
        lines = (self.label,
                 f'Seed {env.seed_value} | day {m["day"]} | strategic {env.steps} | native {env.native_steps} | {phase}',
                 f'{command["action"]} | explored {m["explored"]}/{m["map_tiles"]} | army {m["army"]} | castles {m["castles"]}')
        for y, line in zip((5, 29, 53), lines):
            draw.text((10, y), line, font=font, fill='white')
        self.last = np.asarray(canvas).copy()
        for _ in range(1 if phase in ('battle', 'choice') else 3):
            self.writer.append_data(self.last)
            self.frames += 1
        if self.frames <= 3:
            canvas.save(self.path.with_suffix('.png'))

    def close(self):
        try:
            if self.last is not None:
                for _ in range(12):
                    self.writer.append_data(self.last)
                    self.frames += 1
        finally:
            self.writer.close()
        if not self.frames:
            return {'file': self.path.name, 'frames': 0}
        with imageio.get_reader(str(self.path)) as reader:
            base.require(reader.count_frames() == self.frames, 'Recording lost frames')
            base.require(reader.get_data(self.frames - 1).shape == (560, 640, 3), 'Recording geometry changed')
            base.require(reader.get_meta_data()['fps'] == 12, 'Recording timing changed')
        return {'file': self.path.name, 'frames': self.frames, 'seconds': self.frames / 12,
                'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()}


def plot(folder, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), layout='constrained')
    for run in report['runs']:
        label = f'{run["reward_mode"]} / seed {run["learning_seed"]}'
        axes[0].plot([0] + [c['steps'] for c in run['checkpoints']],
                     [report['validation_baselines']['uniform']['new_tiles']] + [c['validation']['new_tiles'] for c in run['checkpoints']],
                     marker='o', label=label)
    axes[0].axhline(report['validation_baselines']['uniform']['new_tiles'], color='gray', linestyle=':')
    axes[0].set(title='Validation exploration', xlabel='PPO decisions', ylabel='Mean newly revealed tiles')
    axes[0].legend(fontsize=8)
    modes = list(report['test'])
    x = np.arange(len(modes))
    for ax, metric, title in ((axes[1], 'new_tiles', 'Held-out seeds: exploration'),
                              (axes[2], 'mobile_delta', 'Held-out seeds: mobile army')):
        ax.bar(x, [report['test'][mode][metric] for mode in modes], color=['#999999', '#bd9f59', '#267c9d', '#4796ad', '#b36a65'])
        ax.set(title=title, xticks=x, xticklabels=[m.replace('_', '\n') for m in modes], ylabel='Mean over six episodes')
    fig.suptitle('Native adventure PPO: 128-decision early-game evaluation, not full-game mastery')
    fig.supxlabel('Initial point = uniform initial distribution, not a greedy untrained policy. Separate full-game results in report.json.', fontsize=9)
    fig.savefig(folder / 'learning.png', dpi=150)
    plt.close(fig)


def comparisons(folder, report, plan, labels):
    directory = folder / 'videos'
    selected = f'dense_{report["selected"]["learning_seed"]}'
    pairs, checks = [], []
    for case_id in plan['video_cases']:
        prefix = case_id.replace('/', '-')
        for control in ('uniform', 'rule', 'sparse_7'):
            paths = [directory / f'{prefix}-{mode}.mp4' for mode in (control, selected)]
            readers = [imageio.get_reader(str(p)) for p in paths]
            try:
                counts = [r.count_frames() for r in readers]
                output = directory / f'{prefix}-{control}-vs-trained.mp4'
                latest = [None, None]
                with imageio.get_writer(str(output), fps=12, codec='libx264', macro_block_size=2, ffmpeg_log_level='error') as writer:
                    for n in range(max(counts)):
                        for i, reader in enumerate(readers):
                            if n < counts[i]:
                                latest[i] = reader.get_data(n).copy()
                        writer.append_data(np.concatenate(latest, axis=1))
                with imageio.get_reader(str(output)) as reader:
                    base.require(reader.count_frames() == max(counts), 'Comparison lost frames')
                    base.require(reader.get_data(max(counts) - 1).shape == (560, 1280, 3), 'Comparison geometry changed')
                checks.append({'file': output.name, 'frames': max(counts), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
                pairs.append((case_id, control, output.name))
            finally:
                for reader in readers:
                    reader.close()
    page = '''<!doctype html><html lang="hu"><meta charset="utf-8"><title>Adventure RL – helyi eredmények</title>
<style>body{font:17px system-ui;background:#14212d;color:#eee;max-width:1300px;margin:30px auto;padding:20px}video,img{width:100%;border-radius:8px}h2{margin-top:40px}a{color:#9ddcd2}pre{white-space:pre-wrap}</style>
<h1>Adventure RL – mit tanult a modell?</h1>
<p>Jobbra a validáción kiválasztott tanított modell, balra a kontroll. Azonos eredeti pálya és seed; a teszteseteket a tanítás előtt rögzítettük.</p>
<p>Natív döntési pillanatképek: stratégiai döntésenként 0,25 s; csata/választás lépésenként 1/12 s. Nincsenek köztes animációk.
A csaták és párbeszédek minden vezérlőnél ugyanazt a rögzített szabályt követik; ez a kísérlet a stratégiai döntéseket tanítja.
A felirat metrikái az előző stratégiai snapshothoz tartoznak. Eltérhet a két oldalon a nap; a rövidebb felvétel végképe megmarad.</p>
<p>A videók a 128 döntéses korai játékszakaszt mutatják. A tanítás teljes játékbeli eredményeit külön mértük; a lépéslimit nem győzelem.</p>
<p><a href="../report.json">Teljes mérés</a> · <a href="../paired-analysis.json">Párosított tesztkülönbségek</a> · <a href="media-verification.json">Videó-ellenőrzés</a></p>'''
    if (folder / 'learning.png').is_file():
        page += '<img src="../learning.png" alt="Tanulási görbe">'
    page += '<pre>' + html.escape(json.dumps({'test': report['test'], 'full': report['full']}, indent=2)) + '</pre>'
    for case, control, filename in pairs:
        page += f'<h2>{html.escape(case)} — balra: {html.escape(labels[control])}</h2><video controls preload="metadata" src="{filename}"></video>'
    (directory / 'index.html').write_text(page + '</html>', encoding='utf-8')
    return checks


def paired_effects(folder, report):
    """Paired case bootstrap; descriptive seed uncertainty, not map-wide evidence."""
    selected = f'dense_{report["selected"]["learning_seed"]}'
    rows = lambda mode: {r['id']: r for r in json.loads((folder / f'test-{mode}.json').read_text())}
    trained = rows(selected)
    rng = np.random.default_rng(271828)
    result = {'selected': selected, 'scope': 'Six paired native seeds on one fixed map; two learning seeds only', 'comparisons': {}}
    for control in ('uniform', 'rule', 'sparse_7'):
        other = rows(control)
        base.require(trained.keys() == other.keys(), 'Paired test IDs differ')
        effects = {}
        for metric in ('explored', 'mobile', 'income'):
            differences = np.array([trained[key]['delta'][metric] - other[key]['delta'][metric] for key in sorted(trained)])
            sample = rng.choice(differences, size=(10000, len(differences)), replace=True).mean(axis=1)
            effects[metric] = {'mean_difference': float(differences.mean()), 'paired_differences': differences.tolist(),
                               'bootstrap_95_percentile': np.quantile(sample, [.025, .975]).tolist()}
        result['comparisons'][control] = effects
    base.write_json(folder / 'paired-analysis.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--executable', type=Path, default=task.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--plot', action='store_true', help='Requires optional matplotlib')
    args = parser.parse_args()
    folder = args.run.resolve(strict=True)
    base.require(task.ROOT / 'build' in folder.parents, 'Generated media must stay in ignored build/')
    report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
    plan = json.loads((folder / 'plan.json').read_text(encoding='utf-8'))
    base.require(report['completed'] and not report['pilot'], 'Complete the sealed test evaluation first')
    base.require(base.canonical_hash(plan) == report['plan_sha256'], 'Plan fingerprint mismatch')
    for relative, expected in report['identity']['files_sha256'].items():
        base.require(hashlib.sha256((task.ROOT / relative).read_bytes()).hexdigest() == expected, f'Source changed: {relative}')
    identity = base.experiment_identity(args.executable.resolve(strict=True))
    for key in ('executable_sha256', 'asset_sha256'):
        base.require(identity[key] == report['identity'][key], f'{key} changed')
    for name, expected in report['identity']['map_sha256'].items():
        base.require(hashlib.sha256((task.ROOT / 'maps' / name).read_bytes()).hexdigest() == expected, 'Map changed')
    for entry in report['models'].values():
        path = Path(entry['file']).resolve(strict=True)
        base.require(folder in path.parents, 'Models must be trusted local experiment artifacts')
        base.require(hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], 'Model changed')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    selected = f'dense_{report["selected"]["learning_seed"]}'
    labels = {'uniform': 'Véletlen / kezdeti eloszlás', 'rule': 'Egyszerű szabályalapú vezérlő',
              'sparse_7': 'Tanított PPO kiegészítő jutalom nélkül', selected: 'Tanított PPO saját jutalommal'}
    directory = folder / 'videos'
    directory.mkdir(exist_ok=True)
    verified = []
    manifest = [c for c in plan['test'] if c['id'] in plan['video_cases']]
    with tempfile.TemporaryDirectory(dir=folder) as work:
        with task.AdventureTask(args.executable, work, rich_info=False, **plan['early_evaluation_limits']) as env:
            for mode, label in labels.items():
                model = experiment.load_model(report['models'][mode]['file']) if mode in report['models'] else None
                reference = {r['id']: r for r in json.loads((folder / f'test-{mode}.json').read_text())}
                for case in manifest:
                    path = directory / f'{case["id"].replace("/", "-")}-{mode}.mp4'
                    recording = Recording(path, label)
                    try:
                        _, rows = experiment.evaluate(env, [case], model=model,
                                                      mode=mode if model is None else 'greedy', observer=recording)
                        row, original = rows[0], reference[case['id']]
                        for key in ('trace_sha256', 'final', 'native_result', 'terminated', 'truncated', 'reward_parts', 'steps', 'native_steps'):
                            base.require(row[key] == original[key], f'Render replay differs: {case["id"]} {mode} {key}')
                        recording(env, {'action': 'episode.end', 'params': {}})
                    finally:
                        video = recording.close()
                    verified.append(dict(video, case=case['id'], mode=mode, trace_sha256=row['trace_sha256']))
                    base.write_json(directory / 'recording-progress.json', verified)
    if args.plot:
        plot(folder, report)
    paired_effects(folder, report)
    checks = comparisons(folder, report, plan, labels)
    base.write_json(directory / 'media-verification.json', {'source_asset_model_fingerprints_match': True,
                    'render_replays_match_unrendered_tests': True, 'videos_decoded': verified, 'comparisons_decoded': checks})
    print(directory / 'index.html', flush=True)


if __name__ == '__main__':
    main()
