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

"""Optional SB3 MaskablePPO battle experiment; all generated artifacts stay in build/."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from time import perf_counter

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import torch
from torch import nn
from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.policies import MaskableActorCriticPolicy
from stable_baselines3.common.callbacks import BaseCallback

import battle_rl as base


def configuration(family, terrain, variant=0):
    """Two stacks per side, no resurrection/summoning/mind-control in this curriculum."""
    result = base.configuration(family, terrain, variant)
    result['max_rounds'] = 15
    armies = {
        'ranged': ([(3, 8 + variant * 2), (6, 4 + variant)], [(1, 60 + variant * 15), (12, 15 + variant * 3)]),
        'melee': ([(6, 6 + variant), (1, 20)], [(12, 24 + variant * 6), (1, 25)]),
        'flying': ([(33, 7 + variant), (48, 15)], [(48, 25 + variant * 5), (12, 15 + variant * 5)]),
    }
    for side, army in zip(('attacker', 'defender'), armies[family]):
        result[side]['army'] = [{'monster_id': monster, 'count': count} for monster, count in army]
    return result


def cases(split, count=3):
    result = base.evaluation_cases(split, count)
    for case in result:
        case['config'] = configuration(case['family'], case['terrain'], case['variant'])
    return result


def hit_points(obs, own_color=1):
    units = obs['battle_units'][obs['battle_unit_mask'].astype(bool)]
    hp = np.maximum(units[:, base.U['hit_points']], 0)
    own = units[:, base.U['army_color']] == own_color
    return np.array([hp[own].sum(), hp[~own].sum()], dtype=np.float64)


def reward_parts(previous, current, initial, native_reward, mode):
    """Signed HP deltas: healing would reverse the earlier bonus, never clamp to damage-only."""
    if mode == 'sparse':
        return {'outcome': float(native_reward), 'enemy_hp': 0., 'own_hp': 0., 'step_cost': 0.}
    return {'outcome': float(native_reward),
            'enemy_hp': .5 * float(previous[1] - current[1]) / max(float(initial[1]), 1),
            'own_hp': -.5 * float(previous[0] - current[0]) / max(float(initial[0]), 1),
            'step_cost': -.002}


class BattleTask(gym.Wrapper):
    """Task-specific features/reward around unchanged HeroesEnv; dynamic slot meanings retained."""
    def __init__(self, executable, directory, reward_mode='dense', render=False):
        super().__init__(base.create_env(executable, directory, render=render))
        self.reward_mode = reward_mode
        self.observation_space = spaces.Box(-np.inf, np.inf, (self.action_space.n, len(base.FEATURES)), dtype=np.float32)
        self.raw_obs = None

    def observation(self, raw, phase):
        result = np.zeros(self.observation_space.shape, dtype=np.float32)
        if phase == 'battle':
            slots, features = base.action_features(raw)
            result[slots] = features
        return result

    def reset(self, *, seed=None, options=None):
        # Explicit evaluation options bypass the training curriculum sampler.
        if options is None:
            if seed is not None:
                self._rng = np.random.default_rng(seed)
            if not hasattr(self, '_rng'):
                self._rng = np.random.default_rng(0)
            family = base.FAMILIES[int(self._rng.integers(3))]
            terrain = base.TRAIN_TERRAINS[int(self._rng.integers(3))]
            options = {'battle_config': configuration(family, terrain, int(self._rng.integers(3)))}
            seed = int(self._rng.integers(4096))
        raw, info = self.env.reset(seed=seed, options=options)
        self.raw_obs = raw
        self.initial_hp = self.previous_hp = hit_points(raw)
        base.require(np.all(self.initial_hp > 0), 'Curriculum ended before first Python decision')
        return self.observation(raw, info['phase']), info

    def step(self, action):
        raw, native_reward, terminated, truncated, info = self.env.step(action)
        base.require(info['action_accepted'], 'PPO selected an invalid native action')
        current = hit_points(raw)
        parts = reward_parts(self.previous_hp, current, self.initial_hp, native_reward, self.reward_mode)
        self.previous_hp, self.raw_obs = current, raw
        info.update(native_reward=float(native_reward), reward_parts=parts,
                    native_terminated=terminated, native_truncated=truncated)
        # The configured round/decision cap is the task horizon, an absorbing task end.
        # Prevent SB3 from value-bootstrapping a finite task beyond that horizon.
        return self.observation(raw, info['phase']), sum(parts.values()), terminated or truncated, False, info

    def action_masks(self):
        return self.env.action_masks()


class CandidatePolicy(MaskableActorCriticPolicy):
    """Shared candidate actor, pooled critic; no hardcoded action preference or slot identity."""
    def _build(self, lr_schedule):
        width = self.observation_space.shape[-1]
        self.actor = nn.Sequential(nn.Linear(width, 32), nn.Tanh(), nn.Linear(32, 1))
        self.critic = nn.Sequential(nn.Linear(width, 32), nn.Tanh(), nn.Linear(32, 1))
        # Exact uniform initial masked policy. Both sparse/dense runs start from identical weights.
        nn.init.zeros_(self.actor[-1].weight)
        nn.init.zeros_(self.actor[-1].bias)
        self.optimizer = self.optimizer_class(self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs)

    def get_distribution(self, obs, action_masks=None):
        logits = self.actor(obs.float()).squeeze(-1)
        distribution = self.action_dist.proba_distribution(action_logits=logits)
        distribution.apply_masking(action_masks if action_masks is not None else (obs[:, :, 0] != 0))
        return distribution

    def predict_values(self, obs):
        valid = (obs[:, :, 0:1] != 0).float()
        pooled = (obs.float() * valid).sum(dim=1) / valid.sum(dim=1).clamp_min(1)
        return self.critic(pooled)

    def forward(self, obs, deterministic=False, action_masks=None):
        distribution = self.get_distribution(obs, action_masks)
        actions = distribution.get_actions(deterministic=deterministic)
        return actions, self.predict_values(obs), distribution.log_prob(actions)

    def evaluate_actions(self, obs, actions, action_masks=None):
        distribution = self.get_distribution(obs, action_masks)
        return self.predict_values(obs), distribution.log_prob(actions), distribution.entropy()


def evaluate(env, manifest, model=None, mode='greedy', video_directory=None):
    rows = []
    for case in manifest:
        obs, info = env.reset(seed=case['seed'], options={'battle_config': case['config']})
        rng = np.random.default_rng(case['seed'] + 900000)
        total, native, steps, actions, step_times, parts_total = 0., 0., 0, [], [], {}
        writer = None
        if video_directory:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw
            video_directory.mkdir(parents=True, exist_ok=True)
            video_path = video_directory / (case['id'].replace('/', '-') + '-' + mode + '.mp4')
            writer = imageio.get_writer(str(video_path), fps=6, codec='libx264', macro_block_size=2, ffmpeg_log_level='error')

            def frame(caption):
                image = Image.fromarray(env.render())
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, image.width, 34), fill='black')
                draw.text((8, 10), caption, fill='white')
                for _ in range(6):
                    writer.append_data(np.asarray(image))

            frame(f"{mode} | {case['family']} / {case['terrain']} | seed {case['seed']} | initial")
        try:
            while True:
                mask = env.action_masks()
                if mode in ('uniform', 'uniform_no_retreat'):
                    if mode == 'uniform_no_retreat':
                        # Stronger control: separate from the full native legal-action baseline.
                        mask = mask.copy()
                        for name in ('retreat', 'surrender'):
                            mask &= env.raw_obs['actions'][:, base.A['battle_kind']] != base.BATTLE_KINDS.index(name) + 1
                    valid = np.flatnonzero(mask)
                    action = int(rng.choice(valid))
                elif mode == 'heuristic':
                    slots, features = base.action_features(env.raw_obs)
                    action = int(slots[base.heuristic(features)])
                else:
                    action = int(model.predict(obs, deterministic=(mode == 'greedy'), action_masks=mask)[0])
                base.require(mask[action], 'Evaluation chose an invalid slot')
                raw_action = env.raw_obs['actions'][action]
                kind = base.BATTLE_KINDS[int(raw_action[base.A['battle_kind']]) - 1]
                actions.append(int(raw_action[base.A['action_id']]))
                start = perf_counter()
                obs, reward, terminated, truncated, info = env.step(action)
                step_times.append(perf_counter() - start)
                total += reward
                native += info['native_reward']
                steps += 1
                for name, value in info['reward_parts'].items():
                    parts_total[name] = parts_total.get(name, 0.) + value
                if writer:
                    ending = ' WIN' if info['native_terminated'] and native > 0 else (' LOSS' if info['native_terminated'] and native < 0 else (' LIMIT' if info['native_truncated'] else ''))
                    frame(f"{mode} | {case['family']} | step {steps}: {kind} | reward {total:+.2f}{ending}")
                if terminated or truncated:
                    break
        finally:
            if writer:
                writer.close()
        rows.append({'id': case['id'], 'seed': case['seed'], 'return': native, 'shaped_return': total,
                     'terminated': info['native_terminated'], 'truncated': info['native_truncated'], 'steps': steps, 'action_ids': actions,
                     'reward_parts': parts_total, 'remaining_hp_fraction': (env.previous_hp / env.initial_hp).tolist(),
                     'step_seconds': step_times, 'native_result': info['state']['standalone_battle']['result']})
    score = {'episodes': len(rows), 'wins': sum(row['return'] > 0 for row in rows),
             'losses': sum(row['return'] < 0 for row in rows), 'truncated': sum(row['truncated'] for row in rows),
             'win_rate': sum(row['return'] > 0 for row in rows) / len(rows),
             'mean_shaped_return': float(np.mean([row['shaped_return'] for row in rows])),
             'own_hp_remaining': float(np.mean([row['remaining_hp_fraction'][0] for row in rows])),
             'enemy_hp_remaining': float(np.mean([row['remaining_hp_fraction'][1] for row in rows])),
             'step': base.timing([t for row in rows for t in row['step_seconds']])}
    return score, rows


class Validation(BaseCallback):
    def __init__(self, env, manifest, output, interval):
        super().__init__()
        self.env, self.manifest, self.output, self.interval = env, manifest, output, interval
        self.checkpoints, self.best = [], (-1., -1.)
        self.next_step = interval

    def _on_step(self):
        # Evaluate only after a PPO update; _on_rollout_end occurs BEFORE the update.
        if self.num_timesteps > self.next_step:
            score, _ = evaluate(self.env, self.manifest, self.model)
            checkpoint = {'steps': self.num_timesteps - 1, 'validation': score}
            self.checkpoints.append(checkpoint)
            key = (score['win_rate'], score['own_hp_remaining'])
            if key > self.best:
                self.best = key
                self.model.save(self.output)
                self.selected_steps = self.num_timesteps - 1
            self.next_step += self.interval
            print(f"{self.output.name} step={self.num_timesteps - 1} validation={score['win_rate']:.3f}", flush=True)
        return True

    def _on_training_end(self):
        score, _ = evaluate(self.env, self.manifest, self.model)
        self.checkpoints.append({'steps': self.num_timesteps, 'validation': score})
        key = (score['win_rate'], score['own_hp_remaining'])
        if key > self.best:
            self.best = key
            self.selected_steps = self.num_timesteps
            self.model.save(self.output)


def load_model(path, env=None):
    # Load only this example's locally generated SB3 zip files (SB3 uses cloudpickle).
    return MaskablePPO.load(path, env=env, device='cpu')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=base.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, default=base.ROOT / 'build/python-env-battle-ppo')
    parser.add_argument('--steps', type=int, default=4096)
    parser.add_argument('--seeds', type=int, nargs='+', default=[7, 19])
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--model', type=Path, help='Evaluate and record an existing trusted local PPO zip; skip training')
    args = parser.parse_args()
    if args.steps < 256 or args.steps % 256 or len(set(args.seeds)) != len(args.seeds):
        parser.error('steps must be a positive multiple of 256, seeds unique')
    if args.pilot and args.model:
        parser.error('--pilot and --model cannot be combined')
    args.output = args.output.resolve()
    if args.output != base.ROOT / 'build' and base.ROOT / 'build' not in args.output.parents:
        parser.error('Generated models/videos/frames/reports must stay inside the ignored repository build/ directory')
    if (args.output / 'plan.json').exists():
        parser.error('Choose a fresh output directory to preserve previous experiment results')
    args.output.mkdir(parents=True)
    executable = args.executable.resolve(strict=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    import stable_baselines3, sb3_contrib, imageio, imageio_ffmpeg
    validation, test = cases('validation', 3), cases('test', 10)
    plan = {'schema_version': 1, 'curriculum': 'two_stacks_v1', 'steps_per_run': args.steps, 'learning_seeds': args.seeds,
            'architecture': 'Shared 24->32 tanh->1 candidate actor; masked-mean 24->32 tanh->1 critic; uniform initial actor',
            'reward_modes': ['sparse', 'dense'], 'gamma': .99, 'dense_reward': 'native + 0.5 enemy HP lost fraction - 0.5 own HP lost fraction - 0.002/decision',
            'task_horizon': '15 native rounds / 80 decisions; absorbing task end, native truncation still reported separately',
            'validation': validation, 'test': test, 'train_native_seeds': [0, 4095],
            'video_cases': [c['id'] for c in test if c['terrain'] == 'grass' and c['variant'] == 2][:1] +
                           [next(c['id'] for c in test if c['family'] == family and c['terrain'] == 'grass' and c['variant'] == 2) for family in ('melee', 'flying')],
            'selection': 'validation win rate, then own HP remaining; ties earliest; no test tuning',
            'test_baseline_policies': ['uniform', 'uniform_no_retreat', 'heuristic'],
            'ppo': {'learning_rate': .001, 'n_steps': 256, 'batch_size': 64, 'n_epochs': 6, 'ent_coef': .01},
            'video_semantics': 'Native decision snapshots, one second per snapshot; no intermediate animation or real-time speed claim'}
    base.require(not ({c['seed'] for c in validation} & {c['seed'] for c in test}), 'Evaluation seed overlap')
    base.write_json(args.output / 'plan.json', plan)
    identity = base.experiment_identity(executable)
    identity['files_sha256']['python/examples/battle_ppo.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity['libraries'] = {m.__name__: m.__version__ for m in (torch, stable_baselines3, sb3_contrib, imageio, imageio_ffmpeg)}
    report = {'identity': identity, 'plan_sha256': base.canonical_hash(plan), 'runs': [], 'completed': False}
    start = perf_counter()
    with tempfile.TemporaryDirectory(dir=args.output) as directory:
        if args.model:
            path = args.model.resolve(strict=True)
            chosen = load_model(path)
            report['loaded_model'] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            with BattleTask(executable, directory) as evaluation_env:
                for mode in ('greedy', 'stochastic'):
                    torch.manual_seed(81231)
                    score, rows = evaluate(evaluation_env, test, chosen, mode)
                    report['test_' + mode] = score
                    base.write_json(args.output / f'test-{mode}.json', rows)
            with BattleTask(executable, directory, render=True) as video_env:
                video_cases = [c for c in test if c['id'] in plan['video_cases']]
                report['videos'] = {}
                for mode in ('uniform', 'uniform_no_retreat', 'greedy'):
                    score, rows = evaluate(video_env, video_cases, chosen, mode, args.output / 'videos')
                    report['videos'][mode] = {'score': score, 'cases': rows}
            report.update(completed=True, wall_seconds=perf_counter() - start)
            base.write_json(args.output / 'report.json', report)
            return
        with BattleTask(executable, directory) as evaluation_env:
            report['validation_baselines'] = {mode: evaluate(evaluation_env, validation, mode=mode)[0] for mode in ('uniform', 'heuristic')}
            for seed in args.seeds:
                for reward_mode in plan['reward_modes']:
                    path = args.output / f'{reward_mode}-seed-{seed}'
                    with BattleTask(executable, directory, reward_mode) as training_env:
                        model = MaskablePPO(CandidatePolicy, training_env, seed=seed, device='cpu', verbose=0,
                                            gamma=plan['gamma'], **plan['ppo'])
                        initial = {k: v.detach().cpu().clone() for k, v in model.policy.state_dict().items()}
                        callback = Validation(evaluation_env, validation, path, max(256, args.steps // 4))
                        begin = perf_counter()
                        model.learn(total_timesteps=args.steps, callback=callback)
                        elapsed = perf_counter() - begin
                        changed = any(not torch.equal(initial[k], v.cpu()) for k, v in model.policy.state_dict().items())
                        base.require(changed, 'PPO did not update weights')
                        report['runs'].append({'seed': seed, 'reward_mode': reward_mode, 'model': path.name + '.zip',
                                               'selected_steps': callback.selected_steps, 'checkpoints': callback.checkpoints,
                                               'training_seconds_including_validation': elapsed, 'weights_changed': changed,
                                               'steps_per_second_including_validation': args.steps / elapsed})
                        base.write_json(args.output / 'report.json', report)
            def selection(run):
                c = next(c for c in run['checkpoints'] if c['steps'] == run['selected_steps'])['validation']
                return c['win_rate'], c['own_hp_remaining']
            best = max(report['runs'], key=selection)
            report['selected'] = {k: best[k] for k in ('seed', 'reward_mode', 'model', 'selected_steps')}
            base.write_json(args.output / 'selection-before-test.json', report['selected'])
            if not args.pilot:
                report['test_baselines'] = {}
                for mode in ('uniform', 'uniform_no_retreat', 'heuristic'):
                    score, rows = evaluate(evaluation_env, test, mode=mode)
                    report['test_baselines'][mode] = score
                    base.write_json(args.output / f'test-{mode}.json', rows)
                for run in report['runs']:
                    model = load_model(args.output / run['model'])
                    for mode in ('greedy', 'stochastic'):
                        # Fixed policy RNG per evaluation; held-out case seeds are separate from train seeds.
                        torch.manual_seed(81231)
                        score, rows = evaluate(evaluation_env, test, model, mode)
                        run['test_' + mode] = score
                        base.write_json(args.output / f"test-{run['reward_mode']}-{run['seed']}-{mode}.json", rows)
                    base.write_json(args.output / 'report.json', report)
                chosen = load_model(args.output / best['model'])
                _, original = evaluate(evaluation_env, test[:3], chosen)
                again = load_model(args.output / best['model'])
                _, restored = evaluate(evaluation_env, test[:3], again)
                report['reload_matches'] = all((a['action_ids'], a['native_result']) == (b['action_ids'], b['native_result']) for a, b in zip(original, restored))
                base.require(report['reload_matches'], 'Restored model changed evaluation behavior')
        if not args.pilot:
            with BattleTask(executable, directory, render=True) as video_env:
                video_cases = [c for c in test if c['id'] in plan['video_cases']]
                report['videos'] = {}
                for mode in ('uniform', 'uniform_no_retreat', 'greedy'):
                    score, rows = evaluate(video_env, video_cases, chosen, mode, args.output / 'videos')
                    report['videos'][mode] = {'score': score, 'cases': rows}
    report.update(completed=True, wall_seconds=perf_counter() - start)
    base.write_json(args.output / 'report.json', report)
    print('Completed:', args.output, flush=True)


if __name__ == '__main__':
    main()
