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

"""Train/evaluate actual adventure PPO; models, reports and media stay in build/."""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from time import perf_counter

import numpy as np
import torch
import stable_baselines3
import sb3_contrib
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

import adventure_task as task
from adventure_policy import ExpeditionPolicy
from packed_policy import PackedCandidatePolicy
import battle_rl as base

EVAL_LIMITS = {'max_steps': 128, 'max_days': 32}


def cases(split):
    start, count = {'validation': (10000, 3), 'test': (20000, 6), 'transfer': (30000, 2), 'full': (40000, 1)}[split]
    names = ['BROKENA.MP2'] if split == 'transfer' else ['THEOTHER.MP2']
    return [{'id': f'{split}/{Path(names[i % len(names)]).stem}/{start + i}', 'map': names[i % len(names)], 'seed': start + i}
            for i in range(count)]


def load_model(path):
    return MaskablePPO.load(path, device='cpu')


def policy_sha(model):
    value = hashlib.sha256()
    for name, array in sorted(model.policy.state_dict().items()):
        value.update(name.encode())
        value.update(array.detach().cpu().numpy().tobytes())
    return value.hexdigest()


def evaluate(env, manifest, *, model=None, mode='greedy', observer=None):
    rows = []
    old_observer = env.observer
    try:
        env.observer = observer
        for case in manifest:
            begin = perf_counter()
            obs, info = env.reset(seed=case['seed'], options={'map_path': task.ROOT / 'maps' / case['map']})
            start = dict(info['metrics'])
            rng, rule = np.random.default_rng(case['seed'] + 900000), ExpeditionPolicy()
            totals, native, parts = 0., 0., Counter()
            while True:
                mask = env.action_masks()
                if mode == 'uniform':
                    action = int(rng.choice(np.flatnonzero(mask)))
                elif mode == 'rule':
                    action = rule.choose(obs, {'phase': 'adventure', 'player_id': env.player, 'state': env.state, 'actions': env.commands})
                else:
                    action = int(model.predict(obs, deterministic=True, action_masks=mask)[0])
                base.require(mask[action], 'Evaluation chose padding')
                obs, reward, terminated, truncated, info = env.step(action)
                base.require(info['action_accepted'], 'Native strategic command rejected')
                totals += reward
                native += info['native_reward']
                parts.update(info['reward_parts'])
                if terminated or truncated:
                    break
            end = dict(info['metrics'])
            rows.append({'id': case['id'], 'map': case['map'], 'seed': case['seed'], 'mode': mode,
                         'native_reward': native, 'native_result': info['native_result'], 'terminated': terminated, 'truncated': truncated,
                         'steps': env.steps, 'native_steps': env.native_steps, 'return': totals, 'reward_parts': dict(parts),
                         'initial': start, 'final': end, 'delta': {k: end[k] - start[k] for k in start},
                         'commands': dict(env.commands_count), 'trace_sha256': env.trace.hexdigest(),
                         'seconds': perf_counter() - begin})
            print(f'EVAL {mode} {case["id"]} steps={env.steps} day={end["day"]} native={native:+.0f} '
                  f'new_tiles={end["explored"] - start["explored"]} mobile_delta={end["mobile"] - start["mobile"]}', flush=True)
    finally:
        env.observer = old_observer
    score = {'cases': len(rows), 'wins': sum(r['native_reward'] > 0 for r in rows),
             'losses': sum(r['native_reward'] < 0 for r in rows), 'truncated': sum(r['truncated'] for r in rows),
             'new_tiles': float(np.mean([r['delta']['explored'] for r in rows])),
             'mobile_delta': float(np.mean([r['delta']['mobile'] for r in rows])),
             'army_delta': float(np.mean([r['delta']['army'] for r in rows])),
             'income_delta': float(np.mean([r['delta']['income'] for r in rows])),
             'castle_delta': float(np.mean([r['delta']['castles'] for r in rows])),
             'days': float(np.mean([r['final']['day'] for r in rows])),
             'strategic_steps': sum(r['steps'] for r in rows), 'native_steps': sum(r['native_steps'] for r in rows)}
    return score, rows


def selection_key(score):
    return score['wins'], -score['losses'], score['new_tiles'], score['mobile_delta']


class WorkerFactory:
    def __init__(self, executable, directory, rank, mode):
        self.executable, self.directory, self.rank, self.mode = executable, directory, rank, mode

    def __call__(self):
        torch.set_num_threads(1)
        path = Path(self.directory) / f'worker-{self.rank}'
        path.mkdir(parents=True, exist_ok=True)
        return task.AdventureTask(self.executable, path, reward_mode=self.mode, rich_info=False)


def vector_env(executable, directory, workers, mode):
    factories = [WorkerFactory(executable, directory, i, mode) for i in range(workers)]
    return DummyVecEnv(factories) if workers == 1 else SubprocVecEnv(factories, start_method='spawn')


class Validation(BaseCallback):
    def __init__(self, env, path, *, interval=2048):
        super().__init__()
        self.env, self.path, self.interval = env, path, interval
        self.checkpoints, self.best, self.selected_steps = [], None, 0
        self.next_assessment = interval
        self.episodes, self.native_steps = Counter(), 0
        self.seconds = 0.

    def assess(self, step):
        started = perf_counter()
        score, _ = evaluate(self.env, cases('validation'), model=self.model)
        self.checkpoints.append({'steps': step, 'validation': score})
        if self.best is None or selection_key(score) > self.best:
            self.best, self.selected_steps = selection_key(score), step
            self.model.save(self.path)
        print(f'{self.path.name} step={step} validation={score}', flush=True)
        self.seconds += perf_counter() - started

    def _on_step(self):
        for done, info in zip(self.locals['dones'], self.locals['infos']):
            if done:
                self.episodes['completed'] += 1
                self.episodes['native_terminal'] += info['native_result'] != 0
                self.episodes['native_win'] += info['native_reward'] > 0
                self.native_steps += info['native_steps']
        # _on_step runs before the current rollout's PPO update. Assess only on
        # the next rollout, when the labelled budget has actually been trained.
        if self.num_timesteps > self.next_assessment:
            self.assess(self.next_assessment)
            self.next_assessment += self.interval
        return True

    def _on_training_end(self):
        if not self.checkpoints or self.checkpoints[-1]['steps'] != self.num_timesteps:
            self.assess(self.num_timesteps)


def train(executable, output, *, seed, mode, steps, workers, interval=2048):
    with tempfile.TemporaryDirectory(dir=output) as directory:
        validation_path = Path(directory) / 'validation'
        validation_path.mkdir()
        with task.AdventureTask(executable, validation_path, rich_info=False, **EVAL_LIMITS) as validation:
            vec = vector_env(executable, directory, workers, mode)
            try:
                started = perf_counter()
                model = MaskablePPO(PackedCandidatePolicy, vec, seed=seed, device='cpu', verbose=0,
                                    n_steps=256 // workers, batch_size=64, n_epochs=6, gamma=task.GAMMA,
                                    learning_rate=.001, ent_coef=.01)
                initial_sha = policy_sha(model)
                model.save(output / 'initial')
                callback = Validation(validation, output / 'selected', interval=interval)
                model.learn(steps, callback=callback)
                elapsed = perf_counter() - started
                final_sha = policy_sha(model)
                base.require(initial_sha != final_sha, 'Policy weights did not update')
                model.save(output / 'final')
                statuses = vec.env_method('status')
                base.require(len({s['native_pid'] for s in statuses}) == workers, 'Workers share a native engine')
                vec.env_method('close')
                closed = vec.env_method('status')
                base.require(all(s['closed_process']['returncode'] == 0 for s in closed), 'A worker engine did not close cleanly')
            finally:
                vec.close()
    result = {'learning_seed': seed, 'reward_mode': mode, 'steps': model.num_timesteps, 'workers': workers,
              'ppo_epochs': model._n_updates, 'rollout_batch': 256, 'initial_policy_sha256': initial_sha,
              'final_policy_sha256': final_sha, 'selected_steps': callback.selected_steps,
              'checkpoints': callback.checkpoints, 'episodes': dict(callback.episodes),
              'native_steps_in_completed_episodes': callback.native_steps, 'workers_status': statuses, 'closed_workers': closed,
              'seconds_model_learn_and_validation': elapsed, 'seconds_validation': callback.seconds,
              'seconds_model_and_training': elapsed - callback.seconds,
              'training_decisions_per_second': model.num_timesteps / (elapsed - callback.seconds),
              'model': str((output / 'selected.zip').resolve())}
    base.write_json(output / 'report.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=task.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=8192)
    parser.add_argument('--workers', type=int, choices=(1, 2, 4), default=4)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if task.ROOT / 'build' not in output.parents or output.exists() or args.steps < 256 or args.steps % 256:
        parser.error('Use a fresh build/ directory and steps divisible by 256')
    output.mkdir(parents=True)
    executable = args.executable.resolve(strict=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    source_paths = [Path(__file__), task.ROOT / 'python/examples/adventure_task.py', task.ROOT / 'python/examples/adventure_policy.py',
                    task.ROOT / 'python/examples/packed_policy.py', task.ROOT / 'python/examples/battle_ppo.py']
    plan = {'task': 'strategic_adventure_v1', 'features': list(task.FEATURES), 'train_seeds': [0, 4095],
            'train_map': 'THEOTHER.MP2', 'validation': cases('validation'), 'test': cases('test'),
            'transfer': cases('transfer'), 'full': cases('full'), 'horizon': {'strategic_steps': 384, 'days': 64},
            'early_evaluation_limits': EVAL_LIMITS, 'full_evaluation_limits': {'max_steps': 1536, 'max_days': 128},
            'gamma': task.GAMMA, 'steps_per_run': args.steps, 'workers': args.workers,
            'selection': 'validation wins, fewer native losses, new tiles, mobile army delta; ties earliest checkpoint/seed',
            'reward': '5*native + gamma*Phi(next)-Phi(previous) - .005/decision - .02/day - .02/stalled; terminal Phi=0, truncation Phi preserved',
            'battle_and_choices': 'fixed deterministic controller, identical in all modes',
            'macro_profile': 'native routes along eight rays up to eight tiles: adjacent, objects, furthest legal; maximal recruitment/transfer; refresh once/castle/day; suppress repeated no-op in unchanged state; no trade/split/dismiss macros',
            'video_cases': [cases('test')[0]['id'], cases('test')[1]['id']]}
    base.write_json(output / 'plan.json', plan)
    identity = base.experiment_identity(executable)
    identity['files_sha256'].update({str(p.relative_to(task.ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths})
    identity['map_sha256'] = {name: hashlib.sha256((task.ROOT / 'maps' / name).read_bytes()).hexdigest() for name in ('THEOTHER.MP2', 'BROKENA.MP2')}
    identity['device'] = 'cpu_torch'
    identity['rl_libraries'] = {m.__name__: m.__version__ for m in (torch, stable_baselines3, sb3_contrib)}
    report = {'completed': False, 'pilot': args.pilot, 'identity': identity, 'plan_sha256': base.canonical_hash(plan), 'runs': []}
    base.write_json(output / 'report.json', report)
    with tempfile.TemporaryDirectory(dir=output) as directory:
        with task.AdventureTask(executable, directory, rich_info=False, **EVAL_LIMITS) as env:
            report['validation_baselines'] = {mode: evaluate(env, cases('validation'), mode=mode)[0] for mode in ('uniform', 'rule')}
            base.write_json(output / 'report.json', report)
        configs = [('dense', 7)] if args.pilot else [('dense', 7), ('dense', 19), ('sparse', 7)]
        for mode, seed in configs:
            folder = output / f'{mode}-{seed}'
            folder.mkdir()
            report['runs'].append(train(executable, folder, seed=seed, mode=mode, steps=args.steps, workers=args.workers,
                                        interval=min(2048, args.steps)))
            base.write_json(output / 'report.json', report)
        dense = [r for r in report['runs'] if r['reward_mode'] == 'dense']
        chosen = max(dense, key=lambda r: max(selection_key(c['validation']) for c in r['checkpoints']))
        report['selected'] = {'model': chosen['model'], 'learning_seed': chosen['learning_seed'], 'steps': chosen['selected_steps']}
        report['models'] = {f'{r["reward_mode"]}_{r["learning_seed"]}': {'file': r['model'],
                            'sha256': hashlib.sha256(Path(r['model']).read_bytes()).hexdigest()} for r in report['runs']}
        if not args.pilot:
            paired = [r for r in report['runs'] if r['learning_seed'] == 7]
            base.require(len({r['initial_policy_sha256'] for r in paired}) == 1, 'Sparse/dense initial weights differ')
            models = {f'{r["reward_mode"]}_{r["learning_seed"]}': load_model(r['model']) for r in report['runs']}
            for split in ('test', 'transfer', 'full'):
                limits = plan['full_evaluation_limits'] if split == 'full' else EVAL_LIMITS
                with task.AdventureTask(executable, directory, rich_info=False, **limits) as env:
                    results = {}
                    for mode in ('uniform', 'rule', *models):
                        if split == 'full' and mode not in ('uniform', 'rule', f'dense_{chosen["learning_seed"]}'):
                            continue
                        score, rows = evaluate(env, cases(split), mode=mode if mode in ('uniform', 'rule') else 'greedy', model=models.get(mode))
                        results[mode] = score
                        base.write_json(output / f'{split}-{mode}.json', rows)
                    report[split] = results
                    base.write_json(output / 'report.json', report)
        report['completed'] = True
        base.write_json(output / 'report.json', report)
    print('Completed adventure experiment:', output, flush=True)


if __name__ == '__main__':
    main()
