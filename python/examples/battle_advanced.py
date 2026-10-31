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

"""Harder native battle PPO: mixed armies, spells, naval combat and both siege sides."""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
from time import perf_counter

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import torch
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback

import battle_rl as base
import battle_ppo as previous
from fheroes2_env.gym_env import HeroesEnv

CONTEXTS = ('field', 'naval', 'assault', 'defense')
SPELLS = {1: 'Fireball', 3: 'Lightning Bolt', 10: 'Haste', 12: 'Slow', 15: 'Bless', 26: 'Magic Arrow', 48: 'Earthquake'}
EXTRA = ('target_side', 'target_hp', 'target_count', 'target_speed', 'target_shots', 'target_flying', 'target_wide',
         'target_attack', 'target_defense', 'target_effect_count', 'own_mana', 'enemy_mana', 'mana_cost', 'round',
         'siege', 'defending', 'current_x', 'current_y', 'target_x', 'target_y', 'destination_x', 'destination_y',
         'area_own_hp', 'area_enemy_hp', 'own_power')
FEATURES = (*base.FEATURES, *(f'spell_{i}' for i in range(1, 49)), *EXTRA)
ARMIES = (
    (((3, 10), (6, 7), (33, 4)), ((14, 16), (16, 6), (12, 25))),
    (((25, 10), (22, 12), (21, 20)), ((30, 18), (34, 5), (48, 30))),
    (((55, 5), (48, 40), (49, 10)), ((39, 25), (41, 7), (43, 4))),
)
UNSEEN_ARMIES = (
    (((44, 6), (28, 4), (42, 8)), ((7, 10), (32, 12), (51, 12))),
    (((24, 12), (9, 5), (56, 3)), ((13, 18), (17, 7), (8, 6))),
)


def configuration(context, profile=0, variant=0, *, unseen=False):
    base.require(context in CONTEXTS, 'Unknown hard battle context')
    own, enemy = (UNSEEN_ARMIES if unseen else ARMIES)[profile]
    factor = (0.9, 1., 1.1)[variant]
    own_army = [{'monster_id': m, 'count': max(1, round(n * factor))} for m, n in own]
    enemy_army = [{'monster_id': m, 'count': max(1, round(n * (2 - factor)))} for m, n in enemy]
    hero = {'id': 1, 'attack': 3, 'defense': 3, 'power': 3 + variant, 'knowledge': 8,
            'spell_points': 35 + variant * 7, 'spells': list(SPELLS)}
    own_side = {'army': own_army, 'hero': hero, 'controller': 'python'}
    enemy_side = {'army': enemy_army, 'controller': 'builtin_ai'}
    # Field/naval opponents have no hero and therefore cannot end by fleeing.
    # Both commanders in a siege can cast; native attacker retreat remains observable.
    if context in ('assault', 'defense'):
        enemy_side['hero'] = {'id': 46, 'attack': 2, 'defense': 2, 'power': 2, 'knowledge': 4,
                              'spell_points': 14, 'spells': [3, 12, 15]}
    terrains = ('desert', 'swamp', 'lava') if unseen else ('grass', 'snow', 'dirt')
    result = {'terrain': 'water' if context == 'naval' else terrains[variant], 'max_rounds': 20,
              'attacker': enemy_side if context == 'defense' else own_side,
              'defender': own_side if context == 'defense' else enemy_side}
    if context in ('assault', 'defense'):
        races = ('sorceress', 'warlock', 'necromancer') if unseen else ('knight', 'barbarian', 'wizard')
        result['siege'] = {'race': races[variant], 'left_turret': variant > 0, 'right_turret': variant > 1,
                           'moat': True, 'captain': False, 'fortification': not unseen and variant == 0}
    return result


def cases(split):
    base.require(split in ('validation', 'test', 'ood'), 'Unknown split')
    unseen = split == 'ood'
    start = {'validation': 10000, 'test': 20000, 'ood': 30000}[split]
    return [{'id': f'{split}/{context}/{profile}/{variant}', 'seed': start + ci * 100 + profile * 10 + variant,
             'context': context, 'profile': profile, 'variant': variant,
             'config': configuration(context, profile, variant, unseen=unseen)}
            for ci, context in enumerate(CONTEXTS) for profile in range(2 if unseen else 3)
            for variant in ((0, 2) if split == 'validation' else (0, 1, 2))]


def mana(raw, color):
    return float(sum(h[1] for h in raw['battle_commanders'] if h[0] == color))


def xy(cell):
    row, column = divmod(int(cell), 11)
    # Native Board::GetIndexDirection / even-row offset layout.
    return np.array((column - .5 * (row % 2), row * .8660254037844386))


def action_features(raw, allowed, power):
    """Public current numeric state and known own hero power; no rollout or outcome lookahead."""
    slots, common = base.action_features(dict(raw, action_mask=allowed))
    result = np.zeros((len(slots), len(FEATURES)), dtype=np.float32)
    result[:, :len(base.FEATURES)] = common
    units = raw['battle_units'][raw['battle_unit_mask'].astype(bool)]
    units = units[units[:, base.U['alive']] != 0]
    uid, color = int(raw['battle'][4]), int(raw['battle'][5])
    current = next(u for u in units if int(u[base.U['uid']]) == uid)
    by_uid = {int(u[base.U['uid']]): u for u in units}
    by_cell = {int(u[base.U[k]]): u for u in units for k in ('head', 'tail') if u[base.U[k]] >= 0}
    points = np.array([xy(c) for c in range(99)])
    heads = np.array([xy(u[base.U['head']]) for u in units])
    tails = np.array([xy(u[base.U['tail']]) if u[base.U['tail']] >= 0 else xy(u[base.U['head']]) for u in units])
    covered = (((points[:, None] - heads) ** 2).sum(axis=2) <= 1.0201) | (((points[:, None] - tails) ** 2).sum(axis=2) <= 1.0201)
    hp = units[:, base.U['hit_points']]
    own = units[:, base.U['current_color']] == color
    areas = covered @ np.stack((hp * own, hp * ~own), axis=1)
    own_mana, enemy_mana = mana(raw, color), mana(raw, 3 - color)
    current_point = xy(current[base.U['head']])
    enemies = units[:, base.U['current_color']] != color
    distance = lambda point: float(np.sqrt(np.minimum(((heads[enemies] - point) ** 2).sum(axis=1), ((tails[enemies] - point) ** 2).sum(axis=1))).min())
    before = distance(current_point)
    for i, slot in enumerate(slots):
        action = raw['actions'][slot]
        spell_id = int(action[base.A['spell_id']])
        kind = base.BATTLE_KINDS[int(action[base.A['battle_kind']]) - 1]
        if kind == 'spell':
            base.require(1 <= spell_id <= 48, 'Unknown spell feature')
            result[i, len(base.FEATURES) + spell_id - 1] = 1
        cell = int(action[base.A['target_cell']]) if kind in ('attack', 'shoot', 'spell') else -1
        target_uid = int(action[base.A['target_uid']])
        target = by_uid.get(target_uid) if target_uid > 0 else by_cell.get(cell)
        target_point = xy(cell) if cell >= 0 else current_point
        dest = int(action[base.A['destination']])
        dest_point = xy(dest) if kind in ('move', 'attack') and dest >= 0 else current_point
        after = distance(dest_point)
        result[i, 16:19] = (before / 12, (before - after) / 12, after / 12)
        t = lambda field: 0. if target is None else float(target[base.U[field]])
        side = 0 if target is None else (1 if t('current_color') == color else -1)
        effects = 0 if target is None else int(t('modes')).bit_count()
        # Fireball radius-one occupancy, not an estimated damage/reward label.
        area = areas[cell] if cell >= 0 else (0., 0.)
        result[i, -len(EXTRA):] = (side, math.log1p(t('hit_points')) / 8, math.log1p(t('count')) / 8,
                                  t('speed') / 15, min(t('shots') / 24, 1), t('flying'), t('wide'),
                                  t('attack') / 30, t('defense') / 30, effects / 32,
                                  own_mana / 100, enemy_mana / 100, max(0, float(action[base.A['spell_points']])) / 20,
                                  float(raw['battle'][3]) / 20, float(raw['battle'][8]), float(color == raw['battle'][7]),
                                  current_point[0] / 11, current_point[1] / 9, target_point[0] / 11, target_point[1] / 9,
                                  dest_point[0] / 11, dest_point[1] / 9, math.log1p(area[0]) / 8, math.log1p(area[1]) / 8,
                                  power / 20)
    base.require(np.isfinite(result).all(), 'Nonfinite advanced features')
    return slots, result


class AdvancedTask(gym.Wrapper):
    def __init__(self, executable, directory, *, render=False, reward_mode='dense', warmup_steps=0):
        options = dict(base.compact_options(), max_actions=512, max_battle_units=12)
        env = HeroesEnv(executable=executable, battle_config=configuration('field'), max_steps=160,
                        env=base.engine_environment(directory), render_mode='rgb_array' if render else None, **options)
        super().__init__(env)
        self.observation_space = spaces.Box(-np.inf, np.inf, (self.action_space.n, len(FEATURES)), dtype=np.float32)
        self.reward_mode = reward_mode
        self.steps_seen, self.warmup_steps = 0, warmup_steps
        self.training_resets, self.cast_counts = [], Counter()

    def action_masks(self):
        mask = self.raw_obs['action_mask'].astype(bool)
        for kind in ('retreat', 'surrender'):
            mask &= self.raw_obs['actions'][:, base.A['battle_kind']] != base.BATTLE_KINDS.index(kind) + 1
        return mask

    def observation(self, phase):
        result = np.zeros(self.observation_space.shape, dtype=np.float32)
        if phase == 'battle':
            slots, features = action_features(self.raw_obs, self.action_masks(), self.power)
            result[slots] = features
        return result

    def reset(self, *, seed=None, options=None):
        if options is None:
            if seed is not None or not hasattr(self, '_rng'):
                self._rng = np.random.default_rng(seed or 0)
            warmup = self.steps_seen < self.warmup_steps
            contexts = CONTEXTS[:2] if warmup else CONTEXTS
            config = configuration(contexts[int(self._rng.integers(len(contexts)))], int(self._rng.integers(3)), int(self._rng.integers(3)))
            if warmup:
                config['attacker']['hero']['spells'] = [3, 26]
            options = {'battle_config': config}
            seed = int(self._rng.integers(4096))
            context = 'defense' if config['defender']['controller'] == 'python' else ('assault' if config.get('siege') else ('naval' if config['terrain'] == 'water' else 'field'))
            self.training_resets.append({'seed': seed, 'context': context, 'warmup': warmup, 'config': deepcopy(config)})
        config = options['battle_config']
        own_side = 'attacker' if config['attacker']['controller'] == 'python' else 'defender'
        self.color = 1 if own_side == 'attacker' else 2
        self.power = config[own_side]['hero']['power']
        raw, info = self.env.reset(seed=seed, options=options)
        self.raw_obs = raw
        self.initial_hp = self.previous_hp = previous.hit_points(raw, self.color)
        self.initial_mana = self.previous_mana = mana(raw, self.color)
        base.require(info['phase'] == 'battle' and np.all(self.initial_hp > 0), 'Task ended before first Python decision')
        return self.observation(info['phase']), info

    def step(self, action):
        base.require(self.action_masks()[int(action)], 'Task forbids retreat/surrender or invalid action')
        spell = int(self.raw_obs['actions'][int(action), base.A['spell_id']])
        raw, native, terminated, truncated, info = self.env.step(action)
        base.require(info['action_accepted'], 'Masked advanced action rejected')
        hp, mp = previous.hit_points(raw, self.color), mana(raw, self.color)
        parts = previous.reward_parts(self.previous_hp, hp, self.initial_hp, native, self.reward_mode)
        parts['mana'] = -.1 * (self.previous_mana - mp) / max(self.initial_mana, 1) if self.reward_mode == 'dense' else 0.
        self.previous_hp, self.previous_mana, self.raw_obs = hp, mp, raw
        self.steps_seen += 1
        if spell:
            self.cast_counts[str(spell)] += 1
        info.update(native_reward=float(native), native_terminated=terminated, native_truncated=truncated, reward_parts=parts)
        return self.observation(info['phase']), sum(parts.values()), terminated or truncated, False, info


def choose(env, obs, mode, rng, model=None):
    mask = env.action_masks()
    spell_col = 1 + base.BATTLE_KINDS.index('spell')
    if mode in ('no_spells', 'rule_no_spells'):
        mask &= obs[:, spell_col] == 0
    if mode == 'uniform':
        return int(rng.choice(np.flatnonzero(mask)))
    if mode.startswith('rule'):
        # An explicit control policy, never an actor feature or training target.
        if mode == 'rule':
            options = np.flatnonzero(mask & (obs[:, spell_col] != 0))
            for spell in (3, 26):
                targets = [s for s in options if obs[s, len(base.FEATURES) + spell - 1] and obs[s, -len(EXTRA)] < 0]
                if targets:
                    return int(max(targets, key=lambda s: obs[s, -len(EXTRA) + 1]))
        slots = np.flatnonzero(mask & (obs[:, spell_col] == 0))
        return int(slots[base.heuristic(obs[slots, :len(base.FEATURES)])])
    return int(model.predict(obs, deterministic=mode != 'stochastic', action_masks=mask)[0])


def summarize(rows):
    wins = sum(r['native_reward'] > 0 for r in rows)
    return {'episodes': len(rows), 'wins': wins, 'losses': sum(r['native_reward'] < 0 for r in rows),
            'truncated': sum(r['truncated'] for r in rows), 'win_rate': wins / len(rows),
            'win_wilson95': base.wilson(wins, len(rows)), 'own_hp': float(np.mean([r['remaining_hp'][0] for r in rows])),
            'enemy_hp': float(np.mean([r['remaining_hp'][1] for r in rows])), 'mean_steps': float(np.mean([r['steps'] for r in rows])),
            'spell_casts': dict(sum((Counter(r['spells']) for r in rows), Counter())),
            'spell_episodes': sum(bool(r['spells']) for r in rows),
            'enemy_retreats_or_surrenders': sum(r.get('enemy_retreat', False) for r in rows),
            'step': base.timing([t for r in rows for t in r['step_seconds']]),
            'by_context': {c: {'episodes': len(group := [r for r in rows if r['context'] == c]),
                              'wins': sum(r['native_reward'] > 0 for r in group),
                              'truncated': sum(r['truncated'] for r in group),
                              'spell_casts': sum(len(r['spells']) for r in group)} for c in sorted({r['context'] for r in rows})}}


def evaluate(env, manifest, *, model=None, mode='greedy', video_directory=None):
    rows = []
    for case in manifest:
        obs, info = env.reset(seed=case['seed'], options={'battle_config': case['config']})
        rng = np.random.default_rng(case['seed'] + 918231)
        trace, spells, times, total = [], [], [], 0.
        writer = None
        if video_directory is not None:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw, ImageFont
            video_directory.mkdir(parents=True, exist_ok=True)
            writer = imageio.get_writer(str(video_directory / (case['id'].replace('/', '-') + '-' + mode + '.mp4')),
                                        fps=6, codec='libx264', macro_block_size=2, ffmpeg_log_level='error')
            def frame(label):
                picture = Image.fromarray(env.render())
                draw = ImageDraw.Draw(picture)
                draw.rectangle((0, 0, 640, 48), fill='black')
                draw.text((8, 4), f'{mode} | {case["context"]} | Python P{env.color} | seed {case["seed"]}', fill='white', font=ImageFont.load_default(size=14))
                draw.text((8, 25), label, fill='white', font=ImageFont.load_default(size=14))
                for _ in range(6):
                    writer.append_data(np.asarray(picture))
            frame('Initial state')
        try:
            while True:
                action = choose(env, obs, mode, rng, model)
                raw_action = env.raw_obs['actions'][action]
                kind = base.BATTLE_KINDS[int(raw_action[base.A['battle_kind']]) - 1]
                spell = int(raw_action[base.A['spell_id']]) if kind == 'spell' else 0
                trace.append({'kind': kind, 'action_id': int(raw_action[base.A['action_id']]), 'spell_id': spell,
                              'target_cell': int(raw_action[base.A['target_cell']])})
                if spell:
                    spells.append(str(spell))
                begin = perf_counter()
                obs, reward, terminated, truncated, info = env.step(action)
                times.append(perf_counter() - begin)
                total += reward
                if writer:
                    ending = ('WIN' if info['native_reward'] > 0 else 'LOSS') if info['native_terminated'] else ('LIMIT' if info['native_truncated'] else '')
                    frame(f'{len(trace)}: {SPELLS.get(spell, kind)} | return {total:+.2f} {ending}')
                if terminated or truncated:
                    break
        finally:
            if writer:
                writer.close()
        rows.append({'id': case['id'], 'seed': case['seed'], 'context': case['context'], 'native_reward': info['native_reward'],
                     'truncated': info['native_truncated'], 'shaped_return': total, 'steps': len(trace), 'spells': spells,
                     'trace': trace, 'remaining_hp': (env.previous_hp / env.initial_hp).tolist(),
                     'mana_used': env.initial_mana - env.previous_mana, 'step_seconds': times,
                     'enemy_retreat': bool(info['state']['standalone_battle']['result'].get('attacker_result' if env.color == 2 else 'defender_result', 0) & 6),
                     'native_result': info['state']['standalone_battle']['result']})
    return summarize(rows), rows


class Validation(BaseCallback):
    def __init__(self, env, manifest, path, interval, eligible_after=0):
        super().__init__()
        self.env, self.manifest, self.path, self.interval = env, manifest, path, interval
        self.next_step, self.best, self.checkpoints = interval, (-1., -1.), []
        self.eligible_after = eligible_after

    def assess(self, step):
        score, _ = evaluate(self.env, self.manifest, model=self.model)
        self.checkpoints.append({'steps': step, 'validation': score, 'eligible': step > self.eligible_after})
        key = (score['win_rate'], score['own_hp'])
        if step > self.eligible_after and key > self.best:
            self.best, self.selected_steps = key, step
            self.model.save(self.path)
        print(f'{self.path.name} step={step} validation={score["win_rate"]:.3f} hp={score["own_hp"]:.3f} spells={score["spell_casts"]}', flush=True)

    def _on_step(self):
        if self.num_timesteps > self.next_step:
            self.assess(self.num_timesteps - 1)
            self.next_step += self.interval
        return True

    def _on_training_end(self):
        self.assess(self.num_timesteps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=base.ROOT / ('fheroes2.exe' if base.os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, default=base.ROOT / 'build/python-env-advanced')
    parser.add_argument('--steps', type=int, default=8192)
    parser.add_argument('--seeds', type=int, nargs='+', default=[7, 19])
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--model', type=Path, help='Evaluate trusted local model and record videos without training')
    args = parser.parse_args()
    if args.steps < 256 or args.steps % 256 or len(args.seeds) != len(set(args.seeds)) or any(not 0 <= s <= 0xFFFFFFFF for s in args.seeds) or (args.pilot and args.model):
        parser.error('Use unique seeds, steps multiple of 256; --pilot and --model are exclusive')
    output, executable = args.output.resolve(), args.executable.resolve(strict=True)
    if base.ROOT / 'build' not in output.parents or output.exists():
        parser.error('Choose a fresh directory inside ignored build/')
    output.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    validation, test, ood = cases('validation'), cases('test'), cases('ood')
    groups = [set(range(4096)), *({c['seed'] for c in group} for group in (validation, test, ood))]
    base.require(all(not a & b for i, a in enumerate(groups) for b in groups[i+1:]), 'Split leakage')
    plan = {'schema_version': 1, 'curriculum': 'advanced_battle_v1', 'features': list(FEATURES), 'spells': SPELLS,
            'steps': args.steps, 'learning_seeds': args.seeds, 'validation': validation, 'test': test, 'ood': ood,
            'train_native_seeds': [0, 4095], 'train_templates': [configuration(c, p, v) for c in CONTEXTS for p in range(3) for v in range(3)],
            'ppo': {'learning_rate': .001, 'n_steps': 256, 'batch_size': 64, 'n_epochs': 6, 'gamma': .99, 'ent_coef': .01},
            'reward': 'native + 0.5 enemy HP delta - 0.5 own HP delta - 0.002/decision - 0.1 normalized mana spent',
            'warmup_steps': min(2048, args.steps // 2), 'warmup': 'field/naval with Lightning Bolt and Magic Arrow only; then all contexts and seven spells',
            'restriction': 'Python retreat/surrender disabled for every policy; native AI retreat remains native',
            'horizon': '20 native rounds or 160 decisions, absorbing task end; native truncation reported separately',
            'selection': 'Only checkpoints strictly after warmup; greedy validation win rate then own HP; ties earliest checkpoint / learning seed',
            'video_cases': [next(c['id'] for c in test if c['context'] == context and c['profile'] == 1 and c['variant'] == 1) for context in CONTEXTS]}
    base.write_json(output / 'plan.json', plan)
    identity = base.experiment_identity(executable)
    import stable_baselines3, sb3_contrib, imageio, imageio_ffmpeg
    identity['libraries'] = {m.__name__: m.__version__ for m in (torch, stable_baselines3, sb3_contrib, imageio, imageio_ffmpeg)}
    for relative in ('python/examples/battle_advanced.py', 'python/examples/battle_ppo.py', 'python/tests/test_battle_advanced.py'):
        path = base.ROOT / relative
        if path.exists():
            identity['files_sha256'][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'identity': identity, 'plan_sha256': base.canonical_hash(plan), 'completed': False, 'pilot': args.pilot, 'runs': []}
    begin = perf_counter()
    with tempfile.TemporaryDirectory(dir=output) as directory:
        with AdvancedTask(executable, directory) as env:
            if args.model:
                selected_path = args.model.resolve(strict=True)
                chosen = previous.load_model(selected_path)
                report['selected'] = {'model': str(selected_path), 'sha256': hashlib.sha256(selected_path.read_bytes()).hexdigest()}
            else:
                report['validation_baselines'] = {m: evaluate(env, validation, mode=m)[0] for m in ('uniform', 'rule_no_spells', 'rule')}
                base.write_json(output / 'report.json', report)
                for seed in args.seeds:
                    with AdvancedTask(executable, directory, warmup_steps=plan['warmup_steps']) as train_env:
                        model = MaskablePPO(previous.CandidatePolicy, train_env, seed=seed, device='cpu', verbose=0, **plan['ppo'])
                        original = model.policy.actor[-1].weight.detach().clone()
                        path = output / f'advanced-seed-{seed}'
                        callback = Validation(env, validation, path, max(256, args.steps // 4), eligible_after=plan['warmup_steps'])
                        start = perf_counter()
                        model.learn(args.steps, callback=callback)
                        base.require(not torch.equal(original, model.policy.actor[-1].weight), 'Actor did not learn')
                        run = {'seed': seed, 'model': path.name + '.zip', 'selected_steps': callback.selected_steps,
                               'checkpoints': callback.checkpoints, 'training_seconds_including_validation': perf_counter() - start,
                               'training_episodes': len(train_env.training_resets), 'training_contexts': dict(Counter(r['context'] for r in train_env.training_resets)),
                               'training_spells': dict(train_env.cast_counts), 'training_native_seeds': sorted({r['seed'] for r in train_env.training_resets}),
                               'training_manifest_sha256': base.canonical_hash(train_env.training_resets)}
                        base.require(not set(run['training_native_seeds']) & set.union(*groups[1:]), 'Training leaked evaluation seeds')
                        if not args.pilot:
                            base.require({r['context'] for r in train_env.training_resets if not r['warmup']} == set(CONTEXTS), 'Training missed a hard context')
                        base.write_json(output / f'training-seed-{seed}.json', train_env.training_resets)
                        report['runs'].append(run)
                        base.write_json(output / 'report.json', report)
                def selection(run):
                    score = next(c['validation'] for c in run['checkpoints'] if c['steps'] == run['selected_steps'])
                    return score['win_rate'], score['own_hp']
                best = max(report['runs'], key=selection)
                report['selected'] = {k: best[k] for k in ('seed', 'model', 'selected_steps')}
                base.write_json(output / 'selection-before-test.json', report['selected'])
                chosen = previous.load_model(output / best['model'])
            if not args.pilot:
                report['evaluation'] = {}
                for split, manifest in (('test', test), ('ood', ood)):
                    report['evaluation'][split] = {}
                    for mode in ('uniform', 'rule_no_spells', 'rule', 'greedy', 'no_spells', 'stochastic'):
                        torch.manual_seed(72319)
                        score, rows = evaluate(env, manifest, model=chosen, mode=mode)
                        report['evaluation'][split][mode] = score
                        base.write_json(output / f'{split}-{mode}.json', rows)
                        base.write_json(output / 'report.json', report)
                        print(f'{split} {mode}: {score["wins"]}/{score["episodes"]} wins, spells={score["spell_casts"]}', flush=True)
                for run in report['runs']:
                    model = previous.load_model(output / run['model'])
                    run['test_greedy'], rows = evaluate(env, test, model=model)
                    base.write_json(output / f'test-seed-{run["seed"]}.json', rows)
                reference = json.loads((output / 'test-greedy.json').read_text())
                reloaded = previous.load_model(args.model if args.model else output / report['selected']['model'])
                _, rows = evaluate(env, test[:4], model=reloaded)
                report['reload_matches'] = all((a['trace'], a['native_result']) == (b['trace'], b['native_result']) for a,b in zip(reference, rows))
                base.require(report['reload_matches'], 'Reload changed native traces')
        if not args.pilot:
            with AdvancedTask(executable, directory, render=True) as video_env:
                report['videos'] = {}
                for mode in ('uniform', 'rule', 'greedy', 'no_spells'):
                    manifest = [c for c in test if c['id'] in plan['video_cases']]
                    score, rows = evaluate(video_env, manifest, model=chosen, mode=mode, video_directory=output / 'videos')
                    reference = {r['id']: r for r in json.loads((output / f'test-{mode}.json').read_text())}
                    base.require(all((r['trace'], r['native_result']) == (reference[r['id']]['trace'], reference[r['id']]['native_result']) for r in rows), 'Rendering changed results')
                    report['videos'][mode] = {'score': score, 'cases': rows}
    report.update(completed=True, wall_seconds=perf_counter() - begin)
    base.write_json(output / 'report.json', report)
    print('Completed:', output, flush=True)


if __name__ == '__main__':
    main()
