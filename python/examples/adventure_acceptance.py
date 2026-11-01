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

"""Complete seeded adventure episodes; budgets and exceptions are failures, never wins."""

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter
import traceback

from fheroes2_env import HeroesSession, EngineError
from adventure_policy import ExpeditionPolicy

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def world_hash(state):
    normalized = dict(state)
    normalized.pop('state_version', None)  # transport cursor varies with simulation batch size
    return digest(normalized)


def observation_hash(obs):
    value = hashlib.sha256()
    for name, array in sorted(obs.items()):
        value.update(name.encode())
        value.update(str((array.shape, array.dtype)).encode())
        value.update(array.tobytes())
    return value.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


@contextmanager
def profile(directory):
    with tempfile.TemporaryDirectory(dir=directory) as private:
        env = dict(os.environ, APPDATA=private, XDG_CONFIG_HOME=private, XDG_DATA_HOME=private,
                   FHEROES2_DATA=os.environ.get('FHEROES2_DATA', str(ROOT)), SDL_VIDEODRIVER='nonexistent-driver', SDL_AUDIODRIVER='nonexistent-driver')
        if os.name == 'nt':
            env.pop('HOME', None)
        else:
            env['HOME'] = private
        yield env


def runtime_check(game):
    value = game.runtime_info()
    require(value['headless'], 'Lost headless mode')
    require(not any(value[k] for k in ('video_initialized', 'audio_initialized', 'controller_initialized', 'interactive_input', 'animation_waits')),
            'Presentation/input initialized during headless gameplay')
    return value


def query_check(game, state, decision, frames, label):
    require(game.get_state(include_serialized=False) == state, 'World query changed state')
    require(game.get_decision() == decision, 'Decision query changed token')
    frame = game.render(view='adventure', width=320, height=240)
    require(frame.shape == (240, 320, 3) and any(frame.pixels), 'Invalid adventure RGB frame')
    require(game.get_state(include_serialized=False) == state and game.get_decision() == decision, 'Render changed state/token')
    if frames is not None:
        frame.save_ppm(frames / (label + '.ppm'))
    return hashlib.sha256(frame.pixels).hexdigest()


class WorldChanges:
    """Observed snapshot changes, not invented counts of hidden AI commands."""
    def __init__(self, state):
        self.previous = state
        self.counts = Counter()

    def observe(self, state):
        previous = self.previous
        require(state['date']['total_days'] >= previous['date']['total_days'], 'Date went backwards')
        old_heroes = {h['id']: h for h in previous['heroes']}
        self.counts['hero_position_changes'] += sum(h['position'] != old_heroes[h['id']]['position'] for h in state['heroes'])
        self.counts['hero_army_changes'] += sum(h['army'] != old_heroes[h['id']]['army'] for h in state['heroes'])
        old_castles = {c['id']: c for c in previous['castles']}
        self.counts['castle_owner_changes'] += sum(c['owner'] != old_castles[c['id']]['owner'] for c in state['castles'])
        self.counts['new_building_bits'] += sum(len(set(c['buildings']) - set(old_castles[c['id']]['buildings'])) for c in state['castles'])
        self.counts['boat_owner_or_position_changes'] += sum(a['boat_owner'] != b['boat_owner'] or (a['object_under_hero'] == 171) != (b['object_under_hero'] == 171)
                                                           for a, b in zip(state['map']['tiles'], previous['map']['tiles']))
        self.previous = state


def ai_episode(executable, map_path, seed, output, *, batch=12, all_ai_rules=False, max_days=512, frames=None):
    started = perf_counter()
    with profile(output) as environment:
        with HeroesSession(executable, env=environment, timeout=180) as game:
            game.new_game(map_path, seed=seed)
            state = game.get_state(include_serialized=False)
            ids = [p['id'] for p in state['players']]
            options = {'rule_profiles': {i: 'ai' for i in ids}} if all_ai_rules else {}
            decision = game.reset(map_path=map_path, seed=seed, controllers={i: 'builtin_ai' for i in ids}, **options)['decision']
            state = game.get_state(include_serialized=False)
            controls = [(p['id'], p['control']) for p in state['players']]
            initial_size = [state['map']['width'], state['map']['height']]
            changes = WorldChanges(state)
            events, history, images = Counter(), [], {}
            images['initial'] = query_check(game, state, decision, frames, 'initial')
            for tick in range(4096):
                if decision['phase'] == 'terminal':
                    break
                require(decision['phase'] == 'simulation', 'AI-only run yielded an external decision')
                require(state['date']['total_days'] <= max_days, 'AI day budget exhausted before native termination')
                result = game.advance_simulation(batch, token=decision['token'])
                decision = result['decision']
                state = game.get_state(include_serialized=False)
                changes.observe(state)
                events.update(e['type'] for e in result['events'])
                require([(p['id'], p['control']) for p in state['players']] == controls, 'Controller rewrote native rule profiles')
                history.append({'day': state['date']['total_days'], 'phase': decision['phase'],
                                'outcomes': decision['simulation']['outcomes'], 'world_sha256': world_hash(state)})
                if tick % 20 == 0:
                    print(f'AI {map_path.name} seed={seed} day={state["date"]["total_days"]}', flush=True)
                    runtime_check(game)
            require(decision['phase'] == 'terminal' and decision['simulation']['finished'], 'AI step budget exhausted')
            outcomes = decision['simulation']['outcomes']
            require(all(bool(v & 0x3F) != bool(v & 0x70F00) for v in outcomes.values()), 'Missing/ambiguous native participant outcome')
            images['terminal'] = query_check(game, state, decision, frames, 'terminal')
            runtime = runtime_check(game)
            before = deepcopy(state)
            try:
                game.advance_simulation(1, token=decision['token'])
            except EngineError as error:
                require(error.code == 'episode_finished', 'Wrong post-terminal rejection')
            else:
                raise AssertionError('Terminal simulation accepted a further turn')
            require(game.get_state(include_serialized=False) == before, 'Post-terminal rejection changed state')
            final_hash = world_hash(state)
            process = game._process
        require(process.poll() == 0, 'Native process was not reaped')
    write(output / 'history.json', history)
    return {'passed': True, 'mode': 'ai-only', 'map': map_path.name, 'seed': seed, 'size': initial_size,
            'batch': batch, 'all_ai_rules': all_ai_rules, 'native_controls': controls,
            'days': state['date']['total_days'], 'native_ai_turns': events['ai_turn_completed'],
            'outcomes': outcomes, 'winners': [int(k) for k, v in outcomes.items() if v & 0x3F],
            'events': dict(events), 'observed_changes': dict(changes.counts), 'final_world_sha256': final_hash,
            'frame_sha256': images, 'runtime': runtime, 'process_returncode': process.poll(), 'seconds': perf_counter() - started}


def gym_episode(executable, map_path, seed, output, *, max_steps=6000, max_days=256, frames=None):
    from fheroes2_env.gym_env import HeroesEnv
    started = perf_counter()
    with profile(output) as environment:
        with HeroesEnv(executable=executable, map_path=map_path, env=environment, timeout=180, max_steps=max_steps) as env:
            obs, info = env.reset(seed=seed)
            policy = ExpeditionPolicy()
            commands, events, phases = Counter(), Counter(), Counter()
            history, frames_seen, images = [], set(), {}
            trace = hashlib.sha256()
            changes = WorldChanges(info['state'])
            initial_hash = observation_hash(obs)
            for tick in range(max_steps):
                require(info['state']['date']['total_days'] <= max_days, 'Python policy day budget exhausted')
                phases[info['phase']] += 1
                if info['phase'] not in frames_seen:
                    images[info['phase']] = query_check(env._session, info['state'], env._decision, frames, info['phase'])
                    if info['phase'] == 'battle':
                        before = env._session.get_state(include_serialized=False)
                        frame = env._session.render(view='battle', width=320, height=240)
                        require(env._session.get_state(include_serialized=False) == before, 'Battle render changed world')
                        images['battle_view'] = hashlib.sha256(frame.pixels).hexdigest()
                        if frames is not None:
                            frame.save_ppm(frames / 'battle-view.ppm')
                    frames_seen.add(info['phase'])
                action = policy.choose(obs, info)
                require(obs['action_mask'][action], 'Policy chose padding')
                command = info['actions'][action]
                commands[command['action']] += 1
                obs, reward, terminated, truncated, info = env.step(action)
                require(info['action_accepted'], 'Native-validated command was rejected')
                changes.observe(info['state'])
                events.update(e['type'] for e in info['events'])
                record = {'step': tick + 1, 'day': info['state']['date']['total_days'], 'command': command,
                          'reward': reward, 'terminated': terminated, 'truncated': truncated, 'observation_sha256': observation_hash(obs)}
                history.append(record)
                trace.update(json.dumps(record, sort_keys=True).encode())
                if tick % 100 == 0:
                    print(f'Gym {map_path.name} seed={seed} step={tick + 1} day={record["day"]}', flush=True)
                    runtime_check(env._session)
                if terminated or truncated:
                    break
            require(terminated and not truncated and info['phase'] == 'terminal', 'Gym budget exhausted instead of native game over')
            outcome = info['state']['game_result']
            require(reward == (1.0 if outcome & 0x3F else -1.0), 'Gym reward disagrees with native outcome')
            require(not obs['action_mask'].any(), 'Terminal action mask is not empty')
            images['terminal'] = query_check(env._session, info['state'], env._decision, frames, 'terminal')
            runtime = runtime_check(env._session)
            final_hash = world_hash(info['state'])
            process = env._session._process
        require(process.poll() == 0, 'Gym native process was not reaped')
    write(output / 'history.json', history)
    return {'passed': True, 'mode': 'gym-expedition', 'map': map_path.name, 'seed': seed, 'steps': len(history),
            'days': info['state']['date']['total_days'], 'reward': reward, 'native_result': outcome,
            'terminated': terminated, 'truncated': truncated, 'commands': dict(commands), 'events': dict(events), 'phases': dict(phases),
            'initial_observation_sha256': initial_hash, 'trace_sha256': trace.hexdigest(), 'final_world_sha256': final_hash,
            'observed_changes': dict(changes.counts), 'frame_sha256': images, 'runtime': runtime,
            'process_returncode': process.poll(), 'seconds': perf_counter() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / ('fheroes2.exe' if os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', action='store_true')
    parser.add_argument('--regression-map', type=Path, help='Run only the full AI-only boat-summon regression on a supplied Broken Alliance map')
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / 'build' not in output.parents or output.exists():
        parser.error('Use a fresh ignored build/ directory')
    output.mkdir(parents=True)
    executable = args.executable.resolve(strict=True)
    specs = [('ai', name, seed, {}) for name in ('THEOTHER.MP2', 'BROKENA.MP2', '7_deserts.fh2m') for seed in (123, 124)]
    specs += [('ai', 'DRAGONW.MP2', 123, {}), ('ai', 'THEOTHER.MP2', 123, {'batch': 1}),
              ('ai', 'BROKENA.MP2', 123, {'all_ai_rules': True})]
    specs += [('gym', name, seed, {}) for name, seed in (('THEOTHER.MP2', 123), ('THEOTHER.MP2', 124),
                                                       ('7_deserts.fh2m', 123), ('7_deserts.fh2m', 124), ('BROKENA.MP2', 123), ('THEOTHER.MP2', 123))]
    if args.regression_map:
        specs = [('ai', args.regression_map.name, 123, {'all_ai_rules': True})]
    map_paths = {name: args.regression_map.resolve(strict=True) if args.regression_map else ROOT / 'maps' / name for _, name, _, _ in specs}
    paths = set(map_paths.values())
    fingerprints = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    source_paths = [Path(__file__), ROOT / 'python/examples/adventure_policy.py', ROOT / 'src/fheroes2/ai/ai_hero_action.cpp']
    report = {'completed': False, 'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'input_sha256': fingerprints,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}, 'episodes': []}
    for index, (mode, name, seed, options) in enumerate(specs):
        directory = output / f'{index:02d}-{mode}-{Path(name).stem}-{seed}'
        directory.mkdir()
        frames = directory if args.frames else None
        try:
            call = ai_episode if mode == 'ai' else gym_episode
            row = call(executable, map_paths[name], seed, directory, frames=frames, **options)
        except Exception as error:
            row = {'passed': False, 'mode': mode, 'map': name, 'seed': seed, 'error': str(error), 'traceback': traceback.format_exc()}
        report['episodes'].append(row)
        write(output / 'report.json', report)
        print('RESULT', index, row, flush=True)
    require(all(hashlib.sha256(p.read_bytes()).hexdigest() == fingerprints[str(p)] for p in paths), 'Input map changed')
    rows = report['episodes']
    require(all(r['passed'] for r in rows), 'One or more adventure episodes failed; inspect report.json')
    if not args.regression_map:
        require(rows[0]['final_world_sha256'] == rows[7]['final_world_sha256'], 'AI single-turn/batched replay differed')
        require(rows[9]['trace_sha256'] == rows[14]['trace_sha256'], 'Gym seeded replay differed')
        report.update(seeded_replay_equal=True, batch_replay_equal=True)
    report.update(completed=True, inputs_unchanged=True)
    write(output / 'report.json', report)
    print(f'All {len(rows)} complete native adventure episodes passed', flush=True)


if __name__ == '__main__':
    main()
