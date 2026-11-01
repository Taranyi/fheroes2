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

"""Strategic adventure Gym task around the unchanged native session API."""

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import gymnasium as gym
from gymnasium import spaces
import numpy as np

from fheroes2_env import HeroesSession
from fheroes2_env.gym_candidates import ProfileLimitError
from adventure_policy import ExpeditionPolicy, battle_action
import battle_rl as base

ROOT = Path(__file__).resolve().parents[2]
GAMMA = .99
MAX_ACTIONS = 512
ROUTE_RADIUS = 8
KINDS = ('turn.end', 'hero.move', 'castle.build', 'castle.recruit', 'army.transfer',
         'castle.refresh_heroes', 'castle.hire', 'castle.buy_boat', 'hero.buy_spell_book', 'hero.cast')
FEATURES = ('bias', *(f'kind:{kind}' for kind in KINDS), 'day', 'gold', 'income', 'heroes', 'castles',
            'explored', 'army', 'mobile', 'xp', 'hero_move', 'hero_attack', 'hero_defense', 'hero_level', 'hero_ship',
            'hero_army', 'dx', 'dy', 'dest_unseen', 'dest_road', 'dest_water', 'dest_object', 'dest_visit',
            'distance', 'closer', 'hero_castle', 'dest_castle', 'dest_enemy_hero', 'dest_monster', 'dest_resource',
            'dest_chest', 'dest_artifact', 'quantity', 'building', 'castle_army', 'has_visitor', 'spell', 'refresh_used',
            'wood', 'ore', 'mercury', 'sulfur', 'crystal', 'gems', 'hero_race', 'castle_race', 'enemy_units', 'scout_gain')
F = {name: i for i, name in enumerate(FEATURES)}


def metrics(state, player):
    own = next(p for p in state['players'] if p['id'] == player)
    heroes = [h for h in state['heroes'] if h['active'] and h['owner'] == player]
    castles = [c for c in state['castles'] if c['owner'] == player]
    count = lambda slots: sum(t['count'] for t in slots if t is not None)
    mobile = sum(count(h['army']) for h in heroes)
    army = mobile + sum(count(c['garrison']) for c in castles)
    revealed = sum(not (t['fog_colors'] & player) for t in state['map']['tiles'])
    return {'day': state['date']['total_days'], 'gold': own['funds']['gold'], 'income': own['daily_income']['gold'],
            'heroes': len(heroes), 'castles': len(castles), 'explored': revealed,
            'map_tiles': len(state['map']['tiles']), 'army': army, 'mobile': mobile,
            'xp': sum(h['experience'] for h in heroes)}


def potential(m):
    # A fixed state potential, not a bonus per trade, click, split, cast or visit.
    return (5.0 * m['explored'] / m['map_tiles'] + 1.5 * m['castles'] + .15 * m['heroes']
            + .25 * math.log1p(m['army']) + .15 * math.log1p(m['mobile'])
            + .2 * math.log1p(m['income'] / 500) + .25 * math.log1p(m['xp'] / 1000))


def scouting_gain(state, x, y, radius, player):
    """Current fog in the native scouting footprint; no world mutation/lookahead RPC."""
    if radius <= 0:
        return 0
    # Maps::getSquaredScoutingRadiusLimit in maps.cpp, used only as an observation.
    limit = {7: 66, 8: 90}.get(radius, (radius + 1) ** 2 - (radius if radius < 6 else 0))
    width, height = state['map']['width'], state['map']['height']
    return sum(bool(state['map']['tiles'][ny * width + nx]['fog_colors'] & player)
               for ny in range(max(0, y - radius), min(height, y + radius + 1))
               for nx in range(max(0, x - radius), min(width, x + radius + 1))
               if (nx - x) ** 2 + (ny - y) ** 2 < limit)


def reward_parts(before, after, native, terminated, mode):
    return {'native': 5.0 * native,
            'potential': (GAMMA * (0.0 if terminated else potential(after)) - potential(before)) if mode == 'dense' else 0.0,
            'decision': -.005, 'days': -.02 * (after['day'] - before['day'])}


class AdventureTask(gym.Env):
    """A documented macro menu, not lossless replacement for the full HeroesEnv.

    The learner chooses strategic commands. Recruitment/transfer uses the maximum
    legal quantity. A fixed rule controller resolves battles and native choices.
    Both sides' full native state remains available in info['state'].
    """
    metadata = {'render_modes': ['rgb_array'], 'render_fps': 12}

    def __init__(self, executable, directory, *, reward_mode='dense', max_steps=384, max_days=64, observer=None, rich_info=True):
        super().__init__()
        if reward_mode not in ('dense', 'sparse'):
            raise ValueError('Unknown reward mode')
        self.executable, self.directory = Path(executable), Path(directory)
        self.reward_mode, self.max_steps, self.max_days = reward_mode, max_steps, max_days
        self.observer = observer
        self.rich_info = rich_info
        self.action_space = spaces.Discrete(MAX_ACTIONS)
        self.observation_space = spaces.Box(-10, 10, (MAX_ACTIONS, len(FEATURES)), dtype=np.float32)
        self.render_mode = 'rgb_array'
        self.game = None
        self.closed_process = None
        self._needs_reset = True
        self._reset_count = 0
        self._training_seeds = hashlib.sha256()

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options is not None and (not isinstance(options, dict) or set(options) - {'map_path'}):
            raise ValueError('Only map_path is an evaluation reset option')
        if not options:
            native_seed = int(self.np_random.integers(0, 4096))
            path = ROOT / 'maps/THEOTHER.MP2'
            self._training_seeds.update(str(native_seed).encode() + b'\n')
        else:
            if seed is None:
                raise ValueError('Evaluation needs an explicit native seed')
            native_seed, path = seed, Path(options['map_path'])
        if self.game is None:
            self.game = HeroesSession(self.executable, env=base.engine_environment(self.directory), timeout=180)
        self.steps, self.native_steps = 0, 0
        self.commands_count, self.visits, self.refreshed = Counter(), Counter(), set()
        self.noops = set()
        self.trace = hashlib.sha256()
        self._needs_reset = True
        self.decision = self.game.reset(map_path=path, seed=native_seed)['decision']
        self.player = self.decision['player_id']
        self.seed_value, self.map_path = native_seed, path
        self._pump([])
        self.state = self.game.get_state(include_serialized=False)
        self.current_metrics = metrics(self.state, self.player)
        self.initial_metrics = dict(self.current_metrics)
        self._refresh()
        self._reset_count += 1
        self._needs_reset = self.decision['phase'] == 'terminal'
        return self.obs.copy(), self._info(0.0, {}, [])

    def _native(self, command, events):
        if self.observer:
            self.observer(self, command)
        result = self.game.step(command['action'], params=command['params'], token=self.decision['token'])
        self.decision = result['decision']
        self.native_steps += 1
        events.extend(result['events'])
        self.trace.update(json.dumps(command, sort_keys=True).encode())
        return result

    def _pump(self, events):
        for _ in range(10000):
            phase = self.decision['phase']
            if self.decision.get('army_meeting') is not None:
                command = {'action': 'hero.end_meeting', 'params': {}}
            elif phase in ('adventure', 'terminal'):
                return
            elif phase == 'battle':
                command = {'action': 'battle.act', 'params': {'action_id': battle_action(self.decision['battle'])}}
            elif phase == 'choice':
                choice = self.decision['pending_choice']
                if choice.get('input_type') == 'text':
                    command = {'action': 'choice.answer_text', 'params': {'choice_id': choice['choice_id'], 'text': ''}}
                else:
                    value = choice['options'][0] if choice['options'] else choice['minimum']
                    command = {'action': 'choice.answer', 'params': {'choice_id': choice['choice_id'], 'value': value}}
            else:
                raise ProfileLimitError(f'Unexpected strategic task phase {phase}')
            self._native(command, events)
        raise RuntimeError('Automatic battle/choice budget exhausted; not an episode result')

    def _refresh(self):
        self.commands = []
        if self.decision['phase'] != 'terminal':
            proposed = [{'action': 'turn.end', 'params': {}}]
            def add(action, **params):
                proposed.append({'action': action, 'params': params})
            heroes = {h['id']: h for h in self.state['heroes'] if h['active'] and h['owner'] == self.player}
            castles = [c for c in self.state['castles'] if c['owner'] == self.player]
            for h in sorted(heroes.values(), key=lambda x: x['id']):
                for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
                    for distance in range(1, ROUTE_RADIUS + 1):
                        x, y = h['position']['x'] + distance * dx, h['position']['y'] + distance * dy
                        if 0 <= x < self.state['map']['width'] and 0 <= y < self.state['map']['height']:
                            add('hero.move', hero_id=h['id'], x=x, y=y)
                if h['can_buy_spell_book']:
                    add('hero.buy_spell_book', hero_id=h['id'])
                for spell in h['adventure_spell_options']:
                    if spell['can_cast']:
                        add('hero.cast', hero_id=h['id'], spell_id=spell['spell_id'])
            for c in sorted(castles, key=lambda x: x['id']):
                cid = c['id']
                options = self.game.get_castle_options(cid)
                for b in options['buildings']:
                    if b['can_build']:
                        add('castle.build', castle_id=cid, building_id=b['building_id'])
                for dwelling in options['dwellings']:
                    if dwelling['max_recruitable']:
                        add('castle.recruit', castle_id=cid, dwelling_id=dwelling['dwelling_id'], count=dwelling['max_recruitable'])
                if (self.current_metrics['day'], cid) not in self.refreshed:
                    add('castle.refresh_heroes', castle_id=cid)
                if options['hero_hiring']['can_hire']:
                    for offer in options['hero_hiring']['offers']:
                        if offer['available']:
                            add('castle.hire', castle_id=cid, hero_id=offer['hero_id'])
                if options['boat']['can_buy']:
                    add('castle.buy_boat', castle_id=cid)
                visitor = heroes.get(c['visiting_hero_id'])
                if visitor:
                    for source, troop in enumerate(c['garrison']):
                        if troop is None:
                            continue
                        same = [i for i, other in enumerate(visitor['army']) if other is not None and other['monster_id'] == troop['monster_id']]
                        empty = [i for i, other in enumerate(visitor['army']) if other is None]
                        if same or empty:
                            add('army.transfer', source={'kind': 'castle', 'id': cid, 'slot': source},
                                target={'kind': 'hero', 'id': visitor['id'], 'slot': (same or empty)[0]}, count=troop['count'])
            for start in range(0, len(proposed), 128):
                batch = proposed[start:start + 128]
                self.commands.extend(c for c, ok in zip(batch, self.game.check_actions(batch, token=self.decision['token']))
                                     if ok and json.dumps(c, sort_keys=True) not in self.noops)
            # Explicit macro profile: adjacent destinations, interactable objects,
            # and the furthest native-legal destination in each of eight rays.
            # The engine validates and executes the entire route, including cost.
            furthest = {}
            for index, command in enumerate(self.commands):
                if command['action'] == 'hero.move':
                    p = command['params']
                    h = heroes[p['hero_id']]['position']
                    dx, dy = p['x'] - h['x'], p['y'] - h['y']
                    ray = (p['hero_id'], (dx > 0) - (dx < 0), (dy > 0) - (dy < 0))
                    furthest[ray] = index  # proposals are ordered near to far
            keep = set(furthest.values())
            self.commands = [c for i, c in enumerate(self.commands) if c['action'] != 'hero.move'
                             or i in keep
                             or max(abs(c['params']['x'] - heroes[c['params']['hero_id']]['position']['x']),
                                    abs(c['params']['y'] - heroes[c['params']['hero_id']]['position']['y'])) == 1
                             or self.state['map']['tiles'][c['params']['y'] * self.state['map']['width']
                                                          + c['params']['x']]['object_under_hero'] >= 128]
            if not self.commands:
                raise ProfileLimitError('No legal strategic command')
        if len(self.commands) > MAX_ACTIONS:
            raise ProfileLimitError('Strategic action profile exceeded capacity; no actions dropped')
        self.obs = self._features()

    def _features(self):
        result = np.zeros(self.observation_space.shape, dtype=np.float32)
        if not self.commands:
            return result
        m, width = self.current_metrics, self.state['map']['width']
        heroes = {h['id']: h for h in self.state['heroes'] if h['active'] and h['owner'] == self.player}
        castles = {c['id']: c for c in self.state['castles']}
        friends = next(p['friends'] for p in self.state['players'] if p['id'] == self.player)
        targets = [c['id'] for c in castles.values() if c['owner'] == 0 or not c['owner'] & friends]
        distances = {water: ExpeditionPolicy.distances(self.state, targets, water) for water in {h['is_shipmaster'] for h in heroes.values()}}
        own = next(p for p in self.state['players'] if p['id'] == self.player)
        context = {'bias': 1, 'day': m['day'] / 28, 'gold': math.log1p(m['gold']) / 10,
                   'income': m['income'] / 5000, 'heroes': m['heroes'] / 8, 'castles': m['castles'] / 10,
                   'explored': m['explored'] / m['map_tiles'], 'army': math.log1p(m['army']) / 10,
                   'mobile': math.log1p(m['mobile']) / 10, 'xp': math.log1p(m['xp']) / 12}
        context.update({name: math.log1p(own['funds'][name]) / 5 for name in ('wood', 'ore', 'mercury', 'sulfur', 'crystal', 'gems')})
        for i, c in enumerate(self.commands):
            values = dict(context)
            kind, p = c['action'], c['params']
            values['kind:' + kind] = 1
            h = heroes.get(p.get('hero_id'))
            if h:
                values.update(hero_move=h['move_points'] / max(h['max_move_points'], 1), hero_attack=h['attack'] / 20,
                              hero_defense=h['defense'] / 20, hero_level=h['level'] / 20, hero_ship=h['is_shipmaster'],
                              hero_army=math.log1p(sum(t['count'] for t in h['army'] if t)) / 10,
                              hero_castle=h['castle_id'] is not None, hero_race=h['race'] / 32)
            if kind == 'hero.move':
                index = p['y'] * width + p['x']
                tile = self.state['map']['tiles'][index]
                field = distances[h['is_shipmaster']]
                before = field.get(h['position']['index'], width * 2)
                after = field.get(index, width * 2)
                obj = tile['object_under_hero']
                values.update(dx=p['x'] - h['position']['x'], dy=p['y'] - h['position']['y'],
                              dest_unseen=bool(tile['fog_colors'] & self.player), dest_road=tile['road'], dest_water=tile['water'],
                              dest_object=obj / 256, dest_visit=min(self.visits[(h['id'], index)], 10) / 10,
                              distance=after / width, closer=(before - after) / 8, dest_castle=index in castles,
                              dest_enemy_hero=obj == 183, dest_monster=obj == 152, dest_resource=obj == 155,
                              dest_chest=obj == 134, dest_artifact=obj == 169)
                values['scout_gain'] = scouting_gain(self.state, p['x'], p['y'], h['scouting_distance'], self.player) / 50
                enemy = next((other for other in self.state['heroes'] if other['active'] and not other['owner'] & friends
                              and other['position']['index'] == index), None)
                values['enemy_units'] = math.log1p(sum(t['count'] for t in enemy['army'] if t)) / 10 if enemy else 0
            castle = castles.get(p.get('castle_id'))
            if castle:
                values.update(castle_army=math.log1p(sum(t['count'] for t in castle['garrison'] if t)) / 10,
                              has_visitor=castle['visiting_hero_id'] is not None,
                              refresh_used=(m['day'], castle['id']) in self.refreshed, castle_race=castle['race'] / 32)
            values['quantity'] = math.log1p(p.get('count', 0)) / 10
            values['building'] = p.get('building_id', 0).bit_length() / 32
            values['spell'] = p.get('spell_id', 0) / 64
            for name, value in values.items():
                value = float(value)
                if not math.isfinite(value):
                    raise ProfileLimitError('Non-finite strategic feature')
                result[i, F[name]] = min(10., max(-10., value))
        return result

    def step(self, action):
        if self._needs_reset:
            raise gym.error.ResetNeeded('Reset before stepping')
        if not self.action_space.contains(action):
            raise ValueError('Action outside the strategic space')
        index = int(action)
        self.steps += 1
        if index >= len(self.commands):
            truncated = self.steps >= self.max_steps
            self._needs_reset = truncated
            info = self._info(0., {'invalid': -.005}, [])
            info['action_accepted'] = False
            return self.obs.copy(), -.005, False, truncated, info
        before = self.current_metrics
        command = self.commands[index]
        if command['action'] == 'castle.refresh_heroes':
            self.refreshed.add((before['day'], command['params']['castle_id']))
        if command['action'] == 'hero.move':
            p = command['params']
            self.visits[(p['hero_id'], p['y'] * self.state['map']['width'] + p['x'])] += 1
        self.commands_count[command['action']] += 1
        events = []
        try:
            old_state = dict(self.state)
            old_state.pop('state_version', None)
            self._native(command, events)
            self._pump(events)
            self.state = self.game.get_state(include_serialized=False)
            new_state = dict(self.state)
            new_state.pop('state_version', None)
            # Recruitment-offer refresh also changes native RNG/cache state that
            # is not a tile/hero/funds mutation; it is separately limited daily.
            stalled = command['action'] == 'hero.move' and old_state == new_state
            if stalled:
                self.noops.add(json.dumps(command, sort_keys=True))
            else:
                self.noops.clear()
            self.current_metrics = metrics(self.state, self.player)
            terminated = self.decision['phase'] == 'terminal'
            native = 0.
            if terminated:
                outcome = self.state['game_result']
                win, loss = bool(outcome & 0x3F), bool(outcome & 0x70F00)
                if win == loss:
                    raise ProfileLimitError(f'Unknown native adventure outcome {outcome}')
                native = 1. if win else -1.
            truncated = not terminated and (self.steps >= self.max_steps or self.current_metrics['day'] > self.max_days)
            parts = reward_parts(before, self.current_metrics, native, terminated, self.reward_mode)
            parts['stalled'] = -.02 if stalled else 0.
            self._refresh()
            self._needs_reset = terminated or truncated
            return self.obs.copy(), sum(parts.values()), terminated, truncated, self._info(native, parts, events)
        except BaseException:
            self._needs_reset = True
            raise

    def _info(self, native, parts, events):
        info = {'profile': 'adventure-strategic', 'phase': self.decision['phase'], 'player_id': self.player, 'seed': self.seed_value,
                'metrics': dict(self.current_metrics), 'native_result': self.state['game_result'],
                'native_reward': native, 'native_steps': self.native_steps, 'reward_parts': dict(parts),
                'event_counts': dict(Counter(e['type'] for e in events)), 'action_accepted': True, 'strategic_steps': self.steps}
        if self.rich_info:
            info.update(state=deepcopy(self.state), actions=deepcopy(self.commands), events=deepcopy(events))
        return info

    def action_masks(self):
        return self.obs[:, 0] != 0

    def status(self):
        return {'python_pid': base.os.getpid(), 'native_pid': self.game.pid if self.game else None,
                'current_native_steps': getattr(self, 'native_steps', 0), 'current_strategic_steps': getattr(self, 'steps', 0),
                'resets': self._reset_count, 'train_seed_sha256': self._training_seeds.hexdigest(), 'closed_process': self.closed_process}

    def render(self):
        if self.game is None:
            raise gym.error.ResetNeeded('Reset before rendering')
        frame = self.game.render(view='adventure', width=640, height=480)
        return frame.to_numpy().copy()

    def close(self):
        if self.game is not None:
            process = self.game._process
            self.game.close()
            self.closed_process = {'pid': process.pid, 'returncode': process.poll()}
            self.game = None
        self._needs_reset = True
