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

"""Single/multi-process masked PPO with the same advanced battle task and compact transport."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter

# A frozen pre-change package can be benchmarked without modifying the installed package.
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument('--package-root', type=Path)
_early, _ = _bootstrap.parse_known_args()
if _early.package_root:
    sys.path.insert(0, str(_early.package_root.resolve()))

import torch
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.callbacks import BaseCallback
import battle_advanced as advanced


class TrainingTask(advanced.AdvancedTask):
    def __init__(self, executable, directory, *, profile='battle', reuse_process=True, warmup_steps=2048):
        super().__init__(executable, directory, warmup_steps=warmup_steps)
        if profile == 'battle':
            from fheroes2_env.battle_env import BattleEnv
            self.env.close()
            self.env = BattleEnv(executable=executable, battle_config=advanced.configuration('field'),
                                 env=advanced.base.engine_environment(directory), reuse_process=reuse_process)
        else:
            self.env.reuse_process = reuse_process
        self._native_spawns, self._last_process = 0, None
        self._episode_starts, self._contexts = 0, advanced.Counter()
        self._reset_digest = hashlib.sha256()
        self._closed_native = None

    def reset(self, **kwargs):
        result = super().reset(**kwargs)
        if self.env._session._process is not self._last_process:
            self._native_spawns += 1
            self._last_process = self.env._session._process
        for record in self.training_resets:
            self._episode_starts += 1
            self._contexts[record['context']] += 1
            self._reset_digest.update(json.dumps(record, sort_keys=True).encode())
        self.training_resets.clear()  # bounded diagnostics for long-running workers
        return result

    def worker_status(self):
        return {'python_pid': os.getpid(), 'native_pid': self.env._session.pid if self.env._session else None,
                'native_spawns': self._native_spawns, 'episodes': self._episode_starts,
                'contexts': dict(self._contexts), 'reset_manifest_sha256': self._reset_digest.hexdigest(),
                'spells': dict(self.cast_counts), 'closed_native': self._closed_native}

    def close(self):
        process = self.env._session._process if self.env._session else None
        super().close()
        if process is not None:
            self._closed_native = {'pid': process.pid, 'returncode': process.poll()}


class WorkerFactory:
    def __init__(self, executable, directory, rank, profile, reuse, warmup):
        self.executable, self.directory, self.rank = executable, directory, rank
        self.profile, self.reuse, self.warmup = profile, reuse, warmup

    def __call__(self):
        torch.set_num_threads(1)
        directory = Path(self.directory) / f'worker-{self.rank}'
        directory.mkdir(parents=True, exist_ok=True)
        return TrainingTask(self.executable, directory, profile=self.profile, reuse_process=self.reuse, warmup_steps=self.warmup)


def vector_env(executable, directory, *, workers=1, profile='battle', reuse=True, warmup=2048):
    factories = [WorkerFactory(executable, directory, rank, profile, reuse, warmup // workers) for rank in range(workers)]
    return DummyVecEnv(factories) if workers == 1 else SubprocVecEnv(factories, start_method='spawn')


class Episodes(BaseCallback):
    def __init__(self):
        super().__init__()
        self.count, self.wins, self.truncated = 0, 0, 0

    def _on_step(self):
        for done, info in zip(self.locals['dones'], self.locals['infos']):
            if done:
                self.count += 1
                self.wins += info.get('native_reward', 0) > 0
                self.truncated += info.get('native_truncated', False)
        if self.num_timesteps % 2048 == 0:
            print(f'steps={self.num_timesteps} episodes={self.count} wins={self.wins}', flush=True)
        return True


def train(executable, output, *, workers=1, profile='battle', reuse=True, steps=8192, seed=7, packed=False):
    torch.set_num_threads(1)
    begin = perf_counter()
    with tempfile.TemporaryDirectory(dir=output) as directory:
        vec = vector_env(executable, directory, workers=workers, profile=profile, reuse=reuse, warmup=min(2048, steps // 2))
        try:
            policy = advanced.previous.CandidatePolicy
            if packed:
                from packed_policy import PackedCandidatePolicy
                policy = PackedCandidatePolicy
            model = advanced.MaskablePPO(policy, vec, seed=seed, device='cpu', verbose=0,
                                         n_steps=256 // workers, batch_size=64, n_epochs=6, gamma=.99, ent_coef=.01, learning_rate=.001)
            startup = perf_counter() - begin
            original = model.policy.actor[-1].weight.detach().clone()
            callback = Episodes()
            start = perf_counter()
            model.learn(steps, callback=callback)
            duration = perf_counter() - start
            advanced.base.require(not torch.equal(original, model.policy.actor[-1].weight), 'Actor did not update')
            statuses = vec.env_method('worker_status')
            digest = hashlib.sha256()
            for name, parameter in sorted(model.policy.state_dict().items()):
                digest.update(name.encode())
                digest.update(parameter.detach().cpu().numpy().tobytes())
            policy_sha256 = digest.hexdigest()
            advanced.base.require(len({r['native_pid'] for r in statuses}) == workers, 'Workers share a native engine')
            model.save(output / 'model')
            start = perf_counter()
            vec.env_method('close')
            closed = vec.env_method('worker_status')
            advanced.base.require(all(r['closed_native']['returncode'] is not None for r in closed), 'Native process was not reaped')
        finally:
            vec.close()
        close_seconds = perf_counter() - start
        score = None
        with advanced.AdvancedTask(executable, directory) as evaluation:
            score, rows = advanced.evaluate(evaluation, advanced.cases('validation'), model=model)
            advanced.base.write_json(output / 'validation.json', rows)
    return {'workers': workers, 'profile': profile, 'reuse_process': reuse, 'packed_actor': packed, 'seed': seed, 'timesteps': model.num_timesteps,
            'rollout_batch': 256, 'steps_per_worker_rollout': 256 // workers, 'ppo_epochs': 6, 'ppo_updates': model._n_updates,
            'startup_seconds': startup, 'learn_seconds': duration, 'close_seconds': close_seconds,
            'end_to_end_seconds_excluding_evaluation_and_model_save': startup + duration + close_seconds,
            'training_steps_per_second': steps / duration, 'episodes': callback.count, 'wins': callback.wins,
            'native_truncated': callback.truncated, 'workers_status': statuses, 'closed_workers': closed, 'validation': score,
            'policy_sha256': policy_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__, parents=[_bootstrap])
    parser.add_argument('--executable', type=Path, default=advanced.base.ROOT / ('fheroes2.exe' if os.name == 'nt' else 'fheroes2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=(1, 2, 4, 8), default=4)
    parser.add_argument('--profile', choices=('full', 'battle'), default='battle')
    parser.add_argument('--fresh', action='store_true', help='Restart native engine on every reset')
    parser.add_argument('--steps', type=int, default=8192)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--packed', action='store_true', help='Compute the candidate actor only for non-padding rows')
    args = parser.parse_args()
    output = args.output.resolve()
    if advanced.base.ROOT / 'build' not in output.parents or output.exists() or args.steps < 256 or args.steps % 256:
        parser.error('Choose a fresh build/ directory and a positive multiple of 256 training decisions')
    output.mkdir(parents=True)
    executable = args.executable.resolve(strict=True)
    identity = advanced.base.experiment_identity(executable)
    import fheroes2_env
    package = Path(fheroes2_env.__file__).resolve().parent
    identity['actual_package'] = str(package)
    identity['actual_package_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(package.glob('*.py'))}
    identity['vector_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    advanced.base.write_json(output / 'plan.json', {'workers': args.workers, 'profile': args.profile, 'fresh': args.fresh,
                                                   'steps': args.steps, 'seed': args.seed, 'packed': args.packed, 'identity': identity})
    report = train(executable, output, workers=args.workers, profile=args.profile, reuse=not args.fresh, steps=args.steps, seed=args.seed, packed=args.packed)
    advanced.base.write_json(output / 'report.json', report)
    print(report, flush=True)


if __name__ == '__main__':
    main()
