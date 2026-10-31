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

"""Train and evaluate a masked NumPy REINFORCE policy in real native battle episodes."""

import argparse
import cProfile
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import pstats
import subprocess
import tempfile
from time import perf_counter

import numpy as np

from fheroes2_env.gym_env import HeroesEnv
from fheroes2_env import HeroesSession
from fheroes2_env.gym_candidates import BATTLE_KINDS
from fheroes2_env.gym_observation import ACTION_FIELDS, UNIT_FIELDS

ROOT = Path(__file__).resolve().parents[2]
A = {name: index for index, name in enumerate(ACTION_FIELDS)}
U = {name: index for index, name in enumerate(UNIT_FIELDS)}
FEATURES = ("bias", *BATTLE_KINDS, "log_count", "log_own_hp", "log_enemy_hp", "hp_balance", "shots", "speed", "wide", "flying",
            "nearest_enemy", "move_approach", "destination_distance", "target_log_hp", "target_attack", "target_defense", "attack", "defense")
FAMILIES = ("ranged", "melee", "flying")
TRAIN_TERRAINS = ("grass", "snow", "water")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def xy(cell):
    row, column = divmod(int(cell), 11)
    return np.array((column + .5 * (row % 2), row * .8660254037844386))


def action_features(obs):
    """Only public numeric observations; no reward, info, seed or future simulation."""
    slots = np.flatnonzero(obs["action_mask"])
    require(len(slots) > 0, "No legal actions in a live battle")
    units = obs["battle_units"][obs["battle_unit_mask"].astype(bool)]
    alive = units[units[:, U["alive"]] != 0]
    uid = int(obs["battle"][4])
    current = next(unit for unit in alive if int(unit[U["uid"]]) == uid)
    color = int(obs["battle"][5])
    own = alive[alive[:, U["current_color"]] == color]
    enemy = alive[alive[:, U["current_color"]] != color]
    require(len(enemy) > 0, "No visible enemy in a live battle")
    lookup = {int(unit[U["uid"]]): unit for unit in alive}
    enemy_points = np.array([xy(unit[U["head"]]) for unit in enemy])
    start = xy(current[U["head"]])
    distance = lambda point: float(np.sqrt(((enemy_points - point) ** 2).sum(axis=1)).min())
    before_distance = distance(start)
    own_hp, enemy_hp = float(own[:, U["hit_points"]].sum()), float(enemy[:, U["hit_points"]].sum())
    common = [math.log1p(float(current[U["count"]])) / 8, math.log1p(own_hp) / 8, math.log1p(enemy_hp) / 8,
              (own_hp - enemy_hp) / max(own_hp + enemy_hp, 1), min(float(current[U["shots"]]) / 24, 1),
              float(current[U["speed"]]) / 15, float(current[U["wide"]]), float(current[U["flying"]]), before_distance / 12]
    result = np.zeros((len(slots), len(FEATURES)), dtype=np.float64)
    for index, slot in enumerate(slots):
        action = obs["actions"][slot]
        kind = int(action[A["battle_kind"]]) - 1
        require(0 <= kind < len(BATTLE_KINDS), "Non-battle action offered to battle policy")
        result[index, 0] = 1
        result[index, 1 + kind] = 1
        result[index, 8:17] = common
        destination = int(action[A["destination"]])
        point = xy(destination) if BATTLE_KINDS[kind] in ("move", "attack") and destination >= 0 else start
        after_distance = distance(point)
        target = lookup.get(int(action[A["target_uid"]])) if BATTLE_KINDS[kind] in ("attack", "shoot") else None
        result[index, 17:] = ((before_distance - after_distance) / 12, after_distance / 12,
                             0 if target is None else math.log1p(float(target[U["hit_points"]])) / 8,
                             0 if target is None else float(target[U["attack"]]) / 30,
                             0 if target is None else float(target[U["defense"]]) / 30,
                             float(current[U["attack"]]) / 30, float(current[U["defense"]]) / 30)
    require(np.isfinite(result).all(), "Non-finite policy features")
    return slots, result


class Policy:
    """Shared candidate-scoring MLP. Padding is never part of its softmax."""
    def __init__(self, seed=0, hidden=16):
        rng = np.random.default_rng(seed)
        self.params = {"w1": rng.normal(0, .2, (len(FEATURES), hidden)), "b1": np.zeros(hidden), "w2": np.zeros(hidden)}
        self.first = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.second = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.updates = 0

    def forward(self, features):
        hidden = np.tanh(features @ self.params["w1"] + self.params["b1"])
        logits = hidden @ self.params["w2"]
        logits -= logits.max()
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum()
        return probabilities, hidden

    def gradients(self, features, selected, advantage, entropy=.01):
        probabilities, hidden = self.forward(features)
        logs = np.log(np.maximum(probabilities, 1e-300))
        h = -float(probabilities @ logs)
        delta = -advantage * probabilities
        delta[selected] += advantage
        delta -= entropy * probabilities * (logs + h)
        dh = delta[:, None] * self.params["w2"] * (1 - hidden ** 2)
        return {"w1": features.T @ dh, "b1": dh.sum(axis=0), "w2": hidden.T @ delta}, float(advantage * logs[selected] + entropy * h)

    def update(self, episodes, baseline, *, learning_rate=.01, entropy=.01):
        gradients = {key: np.zeros_like(value) for key, value in self.params.items()}
        for episode in episodes:
            advantage = episode["return"] - baseline
            for features, action in episode["trajectory"]:
                values, _ = self.gradients(features, action, advantage, entropy)
                for key in gradients:
                    gradients[key] += values[key] / len(episodes)
        norm = math.sqrt(sum(float((value ** 2).sum()) for value in gradients.values()))
        self.updates += 1
        for key, gradient in gradients.items():
            gradient *= min(1, 5 / max(norm, 1e-12))
            self.first[key] = .9 * self.first[key] + .1 * gradient
            self.second[key] = .999 * self.second[key] + .001 * gradient ** 2
            m = self.first[key] / (1 - .9 ** self.updates)
            v = self.second[key] / (1 - .999 ** self.updates)
            self.params[key] += learning_rate * m / (np.sqrt(v) + 1e-8)
        require(all(np.isfinite(value).all() for value in self.params.values()), "Non-finite learned parameters")

    def export(self):
        return {"schema_version": 1, "algorithm": "masked_reinforce", "features": list(FEATURES),
                "updates": self.updates, "parameters": {key: value.tolist() for key, value in self.params.items()}}

    @classmethod
    def restore(cls, data):
        require(data["schema_version"] == 1 and data["features"] == list(FEATURES), "Unsupported model feature schema")
        hidden = len(data["parameters"]["w2"])
        require(1 <= hidden <= 1024, "Invalid hidden-layer size")
        result = cls(hidden=hidden)
        for key, initial in result.params.items():
            value = np.asarray(data["parameters"][key], dtype=np.float64)
            require(value.shape == initial.shape and np.isfinite(value).all(), f"Invalid parameter array: {key}")
            result.params[key] = value
        result.updates = int(data["updates"])
        return result


def configuration(family, terrain, variant=0):
    pairs = {"ranged": (3, 10 + variant * 2, 1, 45 + variant * 15),
             "melee": (6, 6 + variant, 12, 24 + variant * 6),
             "flying": (33, 7 + variant, 48, 20 + variant * 4)}
    own_id, own_count, enemy_id, enemy_count = pairs[family]
    return {"terrain": terrain, "max_rounds": 10,
            "attacker": {"army": [{"monster_id": own_id, "count": own_count}], "controller": "python", "hero": {"id": 1}},
            "defender": {"army": [{"monster_id": enemy_id, "count": enemy_count}], "controller": "builtin_ai"}}


def evaluation_cases(split="validation", per_family=3):
    require(split in ("validation", "test", "ood"), "Unknown evaluation split")
    base = {"validation": 10000, "test": 20000, "ood": 30000}[split]
    terrains = TRAIN_TERRAINS if split != "ood" else ("desert", "swamp", "lava")
    return [{"id": f"{split}/{family}/{terrain}/{index}", "seed": base + family_index * 100 + terrain_index * 20 + index,
             "family": family, "terrain": terrain, "variant": index % 3,
             "config": configuration(family, terrain, index % 3)}
            for family_index, family in enumerate(FAMILIES) for terrain_index, terrain in enumerate(terrains) for index in range(per_family)]


def compact_options():
    return {"max_map_size": 2, "max_castles": 1, "max_battle_units": 8, "max_actions": 256,
            "max_text_bytes": 1, "max_answer_bytes": 1}


def engine_environment(directory):
    environment = dict(os.environ)
    if os.name == "nt":
        environment.pop("HOME", None)
    else:
        environment["HOME"] = str(directory)
    environment.update(APPDATA=str(directory), XDG_CONFIG_HOME=str(directory), XDG_DATA_HOME=str(directory),
                       FHEROES2_DATA=os.environ.get("FHEROES2_DATA", str(ROOT)),
                       SDL_VIDEODRIVER="nonexistent-driver", SDL_AUDIODRIVER="nonexistent-driver")
    return environment


def create_env(executable, directory, *, compact=True, render=False):
    return HeroesEnv(executable=executable, battle_config=configuration("ranged", "grass"), env=engine_environment(directory),
                     max_steps=80, render_mode="rgb_array" if render else None,
                     **(compact_options() if compact else {}))


def heuristic(features):
    for name in ("shoot", "attack"):
        candidates = np.flatnonzero(features[:, 1 + BATTLE_KINDS.index(name)] == 1)
        if len(candidates):
            return int(candidates[0])
    moves = np.flatnonzero(features[:, 1 + BATTLE_KINDS.index("move")] == 1)
    if len(moves):
        return int(moves[np.argmax(features[moves, FEATURES.index("move_approach")])])
    return 0


def rollout(env, case, *, policy=None, mode="stochastic", rng=None, training=False, render_directory=None):
    rng = np.random.default_rng(case["seed"] + 900000) if rng is None else rng
    start = perf_counter()
    obs, info = env.reset(seed=case["seed"], options={"battle_config": case["config"]})
    reset_seconds = perf_counter() - start
    require(info["phase"] == "battle", "Curriculum battle ended before the learner's first decision")
    trajectory, step_times, inference_times, actions, action_ids = [], [], [], [], []
    initial_bytes = sum(array.nbytes for array in obs.values())
    while True:
        start = perf_counter()
        slots, features = action_features(obs)
        if mode == "uniform":
            selected = int(rng.choice(len(slots), p=np.full(len(slots), 1 / len(slots))))
        elif mode == "heuristic":
            selected = heuristic(features)
        else:
            probabilities, _ = policy.forward(features)
            selected = int(np.argmax(probabilities)) if mode == "greedy" else int(rng.choice(len(slots), p=probabilities))
        inference_times.append(perf_counter() - start)
        if training:
            trajectory.append((features, selected))
        action = int(slots[selected])
        require(obs["action_mask"][action] == 1, "Policy selected a masked slot")
        kind = BATTLE_KINDS[int(obs["actions"][action, A["battle_kind"]]) - 1]
        actions.append(kind)
        action_ids.append(int(obs["actions"][action, A["action_id"]]))
        if render_directory is not None:
            frame = env.render()
            height, width, _ = frame.shape
            (render_directory / f"step-{len(actions):03}.ppm").write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + frame.tobytes())
        start = perf_counter()
        obs, reward, terminated, truncated, info = env.step(action)
        step_times.append(perf_counter() - start)
        require(info["action_accepted"], "Native env rejected a masked policy action")
        if terminated or truncated:
            break
    return {"id": case["id"], "seed": case["seed"], "family": case["family"], "terrain": case["terrain"],
            "return": float(reward), "terminated": bool(terminated), "truncated": bool(truncated), "steps": len(step_times),
            "actions": actions, "action_ids": action_ids, "reset_seconds": reset_seconds, "step_seconds": step_times,
            "inference_seconds": inference_times, "observation_bytes": initial_bytes,
            "trajectory": trajectory, "native_result": info["state"]["standalone_battle"]["result"]}


def timing(values):
    if not values:
        return {"samples": 0}
    array = np.asarray(values)
    return {"samples": len(values), "mean_ms": float(array.mean() * 1000), "median_ms": float(np.median(array) * 1000),
            "p95_ms": float(np.percentile(array, 95) * 1000), "operations_per_second": float(len(array) / array.sum())}


def wilson(wins, total):
    z = 1.959963984540054
    p, z2 = wins / total, z * z
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    half = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / (1 + z2 / total)
    return [center - half, center + half]


def summarize(rows):
    wins = sum(row["terminated"] and row["return"] > 0 for row in rows)
    return {"episodes": len(rows), "wins": wins, "losses": sum(row["terminated"] and row["return"] < 0 for row in rows),
            "truncated": sum(row["truncated"] for row in rows), "win_rate": wins / len(rows), "win_rate_wilson_95": wilson(wins, len(rows)),
            "mean_return": float(np.mean([row["return"] for row in rows])), "steps": sum(row["steps"] for row in rows),
            "reset": timing([row["reset_seconds"] for row in rows]), "step": timing([value for row in rows for value in row["step_seconds"]]),
            "features_and_inference": timing([value for row in rows for value in row["inference_seconds"]]),
            "observation_bytes": rows[0]["observation_bytes"],
            "by_family": {family: {"episodes": len(selected := [row for row in rows if row["family"] == family]),
                                     "wins": sum(row["return"] > 0 for row in selected)} for family in sorted({row["family"] for row in rows})}}


def evaluate(env, cases, *, policy=None, mode="greedy"):
    rows = [rollout(env, case, policy=policy, mode=mode) for case in cases]
    return summarize(rows), [{key: value for key, value in row.items() if key not in ("trajectory", "step_seconds", "inference_seconds")} for row in rows]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def train(env, *, seed, episodes, validation, output, checkpoint_every=100, batch_size=8, learning_rate=.01, entropy=.01):
    rng = np.random.default_rng(seed)
    policy = Policy(seed)
    initial = policy.export()
    baseline, batch, rows, checkpoints = 0.0, [], [], []
    best_key, best = (-1.0, -2.0), None
    begin = perf_counter()
    update_seconds = 0.0
    for index in range(episodes):
        family = FAMILIES[int(rng.integers(3))]
        terrain = TRAIN_TERRAINS[int(rng.integers(3))]
        variant = int(rng.integers(3))
        case = {"id": f"train/{seed}/{index}", "family": family, "terrain": terrain, "seed": int(rng.integers(4096)),
                "config": configuration(family, terrain, variant)}
        episode = rollout(env, case, policy=policy, rng=rng, training=True)
        batch.append(episode)
        rows.append({key: value for key, value in episode.items() if key != "trajectory"})
        if len(batch) == batch_size or index == episodes - 1:
            start = perf_counter()
            policy.update(batch, baseline, learning_rate=learning_rate, entropy=entropy)
            update_seconds += perf_counter() - start
            baseline = .9 * baseline + .1 * float(np.mean([row["return"] for row in batch]))
            batch.clear()
        if (index + 1) % checkpoint_every == 0 or index == episodes - 1:
            score, _ = evaluate(env, validation, policy=policy, mode="stochastic")
            checkpoint = {"episode": index + 1, "validation": score, "model_sha256": canonical_hash(policy.export())}
            recent = rows[-50:]
            checkpoint["train_recent"] = {"episodes": len(recent), "mean_return": float(np.mean([row["return"] for row in recent])),
                                           "win_rate": sum(row["return"] > 0 for row in recent) / len(recent)}
            checkpoints.append(checkpoint)
            write_json(output / f"seed-{seed}-episode-{index + 1}.json", policy.export())
            key = (score["win_rate"], score["mean_return"])
            if key > best_key:
                best_key, best = key, {"model": policy.export(), "episode": index + 1, "validation": score}
            print(f"seed={seed} episode={index + 1} train_last={np.mean([r['return'] for r in rows[-50:]]):.3f} validation_win={score['win_rate']:.3f}", flush=True)
    require(canonical_hash(initial["parameters"]) != canonical_hash(policy.export()["parameters"]), "Training did not change the model")
    return best, {"seed": seed, "episodes": episodes, "training": summarize(rows), "checkpoints": checkpoints,
                  "selected_episode": best["episode"], "selected_validation": best["validation"],
                  "initial_model_sha256": canonical_hash(initial), "final_model_sha256": canonical_hash(policy.export()),
                  "optimizer_seconds": update_seconds, "wall_seconds_including_validation": perf_counter() - begin,
                  "train_native_seeds": sorted({row["seed"] for row in rows})}


def paired_improvement(trained, baseline, samples=5000):
    require([row["id"] for row in trained] == [row["id"] for row in baseline], "Evaluation cases are not paired")
    delta = np.array([float(a["return"] > 0) - float(b["return"] > 0) for a, b in zip(trained, baseline)])
    rng = np.random.default_rng(56391)
    bootstrap = delta[rng.integers(len(delta), size=(samples, len(delta)))].mean(axis=1)
    return {"paired_episodes": len(delta), "win_rate_delta": float(delta.mean()),
            "paired_bootstrap_95": np.percentile(bootstrap, (2.5, 97.5)).tolist(), "bootstrap_samples": samples}


def raw_action(battle):
    for kind in ("shoot", "attack"):
        command = next((action for action in battle["actions"] if action["kind"] == kind), None)
        if command:
            return command
    unit = next(unit for unit in battle["units"] if unit["uid"] == battle["current_unit_uid"])
    enemies = [u for u in battle["units"] if u["alive"] and u["current_color"] != battle["current_color"]]
    moves = [action for action in battle["actions"] if action["kind"] == "move"]
    if moves:
        points = np.array([xy(enemy["head"]) for enemy in enemies])
        distance = lambda point: float(np.sqrt(((points - point) ** 2).sum(axis=1)).min())
        before = distance(xy(unit["head"]))
        return max(moves, key=lambda action: (before - distance(xy(action["destination"]))) / 12)
    return next(action for action in battle["actions"] if action["kind"] == "skip")


def benchmark(executable, directory, cases):
    results, receipts = {}, {}
    for label, compact in (("gym_default", False), ("gym_compact", True)):
        with create_env(executable, directory, compact=compact) as env:
            # Warm filesystem and Python allocations outside the measured sample.
            rollout(env, cases[0], mode="heuristic")
            begin = perf_counter()
            score, rows = evaluate(env, cases, mode="heuristic")
            wall = perf_counter() - begin
            score["wall_seconds"] = wall
            score["end_to_end_steps_per_second_with_resets"] = score["steps"] / wall
            results[label], receipts[label] = score, rows
    require([(r["id"], r["action_ids"], r["native_result"]) for r in receipts["gym_default"]]
            == [(r["id"], r["action_ids"], r["native_result"]) for r in receipts["gym_compact"]],
            "Compact/default benchmark executed different workloads")
    raw_resets, raw_steps, raw_receipts = [], [], []
    environment = engine_environment(directory)
    with HeroesSession(executable, env=environment, timeout=60) as game:
        begin = perf_counter()
        for case in cases:
            start = perf_counter()
            decision = game.reset(battle_config=case["config"], seed=case["seed"])["decision"]
            raw_resets.append(perf_counter() - start)
            action_ids = []
            while decision["phase"] == "battle":
                action = raw_action(decision["battle"])
                action_ids.append(action["action_id"])
                start = perf_counter()
                decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
                raw_steps.append(perf_counter() - start)
            raw_receipts.append((case["id"], action_ids, game.get_state(include_serialized=False)["standalone_battle"]["result"]))
        results["raw_session"] = {"reset": timing(raw_resets), "step": timing(raw_steps), "episodes": len(cases),
                                  "wall_seconds": perf_counter() - begin,
                                  "contract": "Native decision/action transport; no Gym observation encoding or info deepcopy"}
    require(raw_receipts == [(r["id"], r["action_ids"], r["native_result"]) for r in receipts["gym_compact"]],
            "Raw/Gym benchmark executed different workloads")
    with create_env(executable, directory) as env:
        profiler = cProfile.Profile()
        profiler.enable()
        evaluate(env, cases[:9], mode="heuristic")
        profiler.disable()
        stats = pstats.Stats(profiler)
        keys = (("gym_env.py", "_refresh"), ("gym_observation.py", "encode"), ("gym_env.py", "_info"),
                ("session.py", "request"), ("copy.py", "deepcopy"))
        results["profile"] = [{"file": file, "function": function, "calls": value[1], "self_seconds": value[2], "cumulative_seconds": value[3]}
                               for (filename, _, function), value in stats.stats.items() for file, name in keys
                               if filename.endswith(file) and function == name]
    results["matched_native_action_traces"] = True
    return results


def experiment_identity(executable):
    import gymnasium
    files = [Path(__file__).resolve(), ROOT / "python/tests/test_battle_rl.py"] + sorted((ROOT / "python/src/fheroes2_env").glob("*.py"))
    assets = {}
    for relative in ("DATA/HEROES2.AGG", "DATA/HEROES2X.AGG", "files/data/resurrection.h2d"):
        path = Path(os.environ.get("FHEROES2_DATA", ROOT)) / relative
        if path.is_file():
            with path.open("rb") as stream:
                assets[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "files_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()},
            "asset_sha256": assets,
            "python": platform.python_version(), "numpy": np.__version__, "gymnasium": gymnasium.__version__,
            "platform": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count(), "device": "cpu_numpy",
            "created_utc": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--output", type=Path, default=ROOT / "build/python-env-first-rl")
    parser.add_argument("--episodes", type=int, default=400)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 19, 41])
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--test-per-family", type=int, default=10)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--pilot", action="store_true", help="Train/validate only; never open the final test split")
    modes.add_argument("--evaluate-only", type=Path, help="Evaluate saved weights on the sealed test manifest")
    modes.add_argument("--demo", type=Path, help="Save a held-out episode as PPM frames using saved weights")
    args = parser.parse_args()
    if (not 1 <= args.episodes <= 100000 or not 1 <= args.checkpoint_every <= 100000 or not 1 <= args.test_per_family <= 20
            or not args.seeds or len(set(args.seeds)) != len(args.seeds) or any(not 0 <= seed <= 0xFFFFFFFF for seed in args.seeds)):
        parser.error("Invalid episode/checkpoint/test counts or duplicate learning seeds")
    executable = args.executable.resolve(strict=True)
    experiment_start = perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    validation, test = evaluation_cases("validation", 3), evaluation_cases("test", args.test_per_family)
    ood = evaluation_cases("ood", 3)
    require(not {c["seed"] for c in validation} & {c["seed"] for c in test}, "Validation/test seed overlap")
    plan = {"schema_version": 1, "dataset": "first_battle_v1", "algorithm": "masked_reinforce",
            "hidden_units": 16, "parameters": len(FEATURES) * 16 + 32, "features": list(FEATURES),
            "episodes_per_run": args.episodes, "learning_seeds": args.seeds, "gamma": 1.0,
            "learning_rate": .01, "entropy": .01, "batch_episodes": 8, "baseline": "previous-batch EMA, state independent",
            "training_native_seed_range": [0, 4095], "validation_cases": validation, "test_cases": test, "ood_cases": ood,
            "checkpoint_selection": "highest stochastic validation win rate, then mean return, then earliest checkpoint",
            "learning_criterion": {"minimum_win_rate_gain": .15, "paired_bootstrap_lower_bound_above_zero": True,
                                   "at_least_two_learning_seeds_improve": True},
            "reward": "Unchanged native Gym terminal +1/-1; draw/truncation 0; no dense reward shaping",
            "compact_profile": compact_options(), "render_during_training": False}
    write_json(args.output / "plan.json", plan)
    report = {"schema_version": 1, "identity": experiment_identity(executable), "plan_sha256": canonical_hash(plan),
              "run_completed": False, "learning_detected": None, "runs": [], "pilot": args.pilot}
    profiles = args.output / "profiles"
    profiles.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=profiles) as directory:
        if args.demo:
            model = Policy.restore(json.loads(args.demo.read_text(encoding="utf-8")))
            with create_env(executable, directory, render=True) as env:
                rollout(env, test[0], policy=model, mode="greedy", render_directory=args.output)
            return
        with create_env(executable, directory) as env:
            if args.evaluate_only:
                model = Policy.restore(json.loads(args.evaluate_only.read_text(encoding="utf-8")))
                score, receipts = evaluate(env, test, policy=model)
                write_json(args.output / "evaluation.json", {"identity": report["identity"], "score": score, "cases": receipts})
                print(json.dumps(score, indent=2))
                return
            # Baselines and tuning use validation only until every training run and checkpoint choice is frozen.
            report["validation_baselines"] = {mode: evaluate(env, validation, mode=mode)[0] for mode in ("uniform", "heuristic")}
            write_json(args.output / "report.json", report)
            selected = []
            for seed in args.seeds:
                best, training = train(env, seed=seed, episodes=args.episodes, validation=validation,
                                       output=args.output / "checkpoints", checkpoint_every=args.checkpoint_every)
                selected.append(best)
                report["runs"].append(training)
                write_json(args.output / f"model-seed-{seed}.json", best["model"])
                write_json(args.output / "report.json", report)
            best_index = max(range(len(selected)), key=lambda i: (selected[i]["validation"]["win_rate"], selected[i]["validation"]["mean_return"]))
            report["selected_learning_seed"] = args.seeds[best_index]
            model_document = deepcopy(selected[best_index]["model"])
            model_document["experiment"] = {"plan_sha256": canonical_hash(plan), "learning_seed": args.seeds[best_index],
                                             "checkpoint_episode": selected[best_index]["episode"], "selected_using": "validation_only"}
            write_json(args.output / "model.json", model_document)
            if not args.pilot:
                report["test_baselines"] = {}
                for mode in ("uniform", "heuristic"):
                    score, receipts = evaluate(env, test, mode=mode)
                    report["test_baselines"][mode] = score
                    write_json(args.output / f"test-{mode}.json", receipts)
                baseline = json.loads((args.output / "test-uniform.json").read_text())
                improvements = []
                for index, best in enumerate(selected):
                    policy = Policy.restore(best["model"])
                    for mode in ("greedy", "stochastic"):
                        score, receipts = evaluate(env, test, policy=policy, mode=mode)
                        report["runs"][index]["test_" + mode] = score
                        write_json(args.output / f"test-seed-{args.seeds[index]}-{mode}.json", receipts)
                        if mode == "greedy":
                            comparison = paired_improvement(receipts, baseline)
                            improvements.append(comparison)
                            report["runs"][index]["paired_improvement"] = comparison
                require(all(not set(run["train_native_seeds"]) & {c["seed"] for c in test + validation + ood} for run in report["runs"]), "Training leaked evaluation seeds")
                selected_comparison = improvements[best_index]
                report["learning_detected"] = (selected_comparison["win_rate_delta"] >= .15 and selected_comparison["paired_bootstrap_95"][0] > 0
                                               and sum(value["win_rate_delta"] > 0 for value in improvements) >= min(2, len(improvements)))
                best_policy = Policy.restore(selected[best_index]["model"])
                report["ood"] = {mode: evaluate(env, ood, policy=best_policy, mode=mode)[0] for mode in ("greedy", "uniform", "heuristic")}
        if not args.pilot:
            report["benchmark"] = benchmark(executable, directory, [case for case in test if int(case["id"].rsplit("/", 1)[1]) < 3])
    report["run_completed"] = True
    report["wall_seconds"] = perf_counter() - experiment_start
    write_json(args.output / "report.json", report)
    print("Completed; learning_detected=", report["learning_detected"], flush=True)


if __name__ == "__main__":
    main()
