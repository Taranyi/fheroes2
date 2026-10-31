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

"""Reproduce native acceptance scenarios, longer Gym rollouts and local timing measurements."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from time import perf_counter

from fheroes2_env import HeroesSession, EngineError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "build/python-env-baseline/fixtures"
SPEC = importlib.util.spec_from_file_location("acceptance_battle_policy", ROOT / "python/examples/battle.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summary(samples):
    ordered = sorted(samples)
    return {"samples": len(samples), "mean_ms": statistics.mean(samples) * 1000,
            "median_ms": statistics.median(samples) * 1000,
            "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * .95))] * 1000,
            "min_ms": min(samples) * 1000, "max_ms": max(samples) * 1000}


def measured(samples, call):
    begin = perf_counter()
    result = call()
    samples.append(perf_counter() - begin)
    return result


@contextmanager
def isolated(executable):
    work = ROOT / "build/python-env-acceptance/profiles"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        environment = dict(os.environ)
        if os.name == "nt":
            environment.pop("HOME", None)
        else:
            environment["HOME"] = directory
        environment.update(APPDATA=directory, XDG_CONFIG_HOME=directory, XDG_DATA_HOME=directory,
                           FHEROES2_DATA=str(ROOT), SDL_VIDEODRIVER="nonexistent-driver", SDL_AUDIODRIVER="nonexistent-driver")
        yield environment, Path(directory)


def read_only_frame(game, view, **params):
    before, decision = game.get_state(), game.get_decision()
    frame = game.render(view=view, **params)
    assert frame.width == 640 and frame.height == 480 and any(frame.pixels)
    assert game.get_state() == before and game.get_decision() == decision
    return hashlib.sha256(frame.pixels).hexdigest()


def scenario(executable):
    path = FIXTURES / "battles-boss-day1.sav"
    source_hash = digest(path)
    with isolated(executable) as (environment, directory):
        with HeroesSession(executable, env=environment, timeout=60) as game:
            decision = game.reset(save=path, seed=2026)["decision"]
            events, phases, images = [], {decision["phase"]}, {}
            initial = game.get_state(include_serialized=False)
            for view, selectors in (("adventure", {}), ("hero", {"hero_id": 52}), ("castle", {"castle_id": 896})):
                images[view] = read_only_frame(game, view, **selectors)
            def act(action, **params):
                nonlocal decision
                result = game.step(action, token=decision["token"], params=params)
                decision = result["decision"]
                events.extend(e["type"] for e in result["events"])
                phases.add(decision["phase"])
                return result
            act("castle.build", castle_id=896, building_id=1 << 22)
            dwelling = next(d for d in game.get_castle_options(896)["dwellings"] if d["max_recruitable"] > 0)
            act("castle.recruit", castle_id=896, dwelling_id=dwelling["dwelling_id"], count=1)
            army = next(h for h in game.get_state(include_serialized=False)["heroes"] if h["id"] == 52)["army"]
            source = next(i for i, troop in enumerate(army) if troop is not None and troop["count"] > 3)
            target = next(i for i, troop in enumerate(army) if troop is None)
            a, b = {"kind": "hero", "id": 52, "slot": source}, {"kind": "hero", "id": 52, "slot": target}
            act("army.transfer", source=a, target=b, count=3)
            act("army.transfer", source=b, target=a, count=3)
            act("hero.move", hero_id=52, x=32, y=25)
            count = 0
            while decision["phase"] in ("choice", "battle"):
                count += 1
                assert count <= 500, "Native scenario exceeded the decision budget"
                if decision["phase"] == "battle":
                    if "battle" not in images:
                        images["battle"] = read_only_frame(game, "battle")
                    candidate = POLICY.select_action(decision["battle"], use_spells=True)
                    act("battle.act", action_id=candidate["action_id"])
                else:
                    choice = decision["pending_choice"]
                    value = choice["options"][0] if choice["options"] else choice["minimum"]
                    act("choice.answer", choice_id=choice["choice_id"], value=value)
            assert decision["phase"] == "adventure" and {"battle", "choice"} <= phases
            assert {"castle_built", "castle_recruited", "army_transferred", "battle_completed", "choice_answered"} <= set(events)
            act("turn.end")
            assert "ai_turn_completed" in events
            final = game.get_state(include_serialized=False)
            hero = next(h for h in final["heroes"] if h["id"] == 52)
            assert hero["active"] and hero["level"] > next(h for h in initial["heroes"] if h["id"] == 52)["level"]
            runtime = game.runtime_info()
            assert not any(runtime[k] for k in ("video_initialized", "audio_initialized", "controller_initialized", "interactive_input"))
            process, worker = game._process, game._worker
        assert process.poll() == 0 and not worker.is_alive() and not list(directory.iterdir())
    assert digest(path) == source_hash
    return {"passed": True, "phases": sorted(phases), "native_decisions": count, "hero_level": hero["level"],
            "final_day": final["date"]["total_days"], "event_types": sorted(set(events)), "frame_sha256": images,
            "runtime": runtime, "process_reaped": True, "input_unchanged": True}


def stress(executable, episodes, max_steps):
    from fheroes2_env.gym_env import HeroesEnv
    records = []
    with isolated(executable) as (environment, directory):
        for mode in ("random", "battle"):
            path = FIXTURES / ("other-side-day1.sav" if mode == "random" else "battles-boss-day1.sav")
            with HeroesEnv(executable=executable, save=path, env=environment, max_steps=max_steps, timeout=60) as game:
                for episode in range(episodes if mode == "random" else max(2, episodes // 3)):
                    seed = 1000 + episode
                    record = {"mode": mode, "seed": seed, "steps": 0, "reward": 0., "phases": [], "error": None}
                    phases = set()
                    try:
                        obs, info = game.reset(seed=seed)
                        phases.add(info["phase"])
                        for step in range(max_steps):
                            if mode == "random":
                                action = game.action_space.sample(mask=obs["action_mask"])
                            elif step == 0:
                                action = next(i for i, c in enumerate(info["actions"]) if c == {"action": "hero.move", "params": {"hero_id": 52, "x": 32, "y": 25}})
                            elif info["phase"] == "battle":
                                candidate = POLICY.select_action(info["state"]["battle"], use_spells=True)
                                action = next(i for i, c in enumerate(info["actions"]) if c["params"].get("action_id") == candidate["action_id"])
                            else:
                                action = 0  # first native choice, or end adventure turn
                            obs, reward, terminated, truncated, info = game.step(action)
                            assert info["action_accepted"], "A sampled native mask slot was rejected"
                            assert game.observation_space.contains(obs)
                            record["steps"] = step + 1
                            record["reward"] += reward
                            phases.add(info["phase"])
                            if terminated or truncated:
                                record.update(terminated=terminated, truncated=truncated, final_day=info["state"]["date"]["total_days"])
                                break
                        else:
                            raise AssertionError("Episode did not report its attempt limit")
                    except EngineError as error:
                        record["error"] = {"code": error.code, "message": str(error)}
                    record["phases"] = sorted(phases)
                    records.append(record)
                    print(json.dumps(record), flush=True)
        assert not list(directory.iterdir()), "Headless runs wrote profile files"
    return {"passed": not any(r["error"] for r in records), "episodes": records,
            "total_steps": sum(r["steps"] for r in records), "render_requests": 0}


def benchmarks(executable, samples):
    from fheroes2_env.gym_env import HeroesEnv
    data = {}
    with isolated(executable) as (environment, directory):
        with HeroesSession(executable, env=environment, timeout=60) as game:
            for name, source in (("reset_save", {"save": FIXTURES / "other-side-day1.sav"}),
                                 ("reset_map", {"map_path": ROOT / "maps/THEOTHER.MP2"})):
                times = []
                game.reset(**source, seed=42)  # warm filesystem/cache, excluded
                for _ in range(samples):
                    measured(times, lambda: game.reset(**source, seed=42))
                data[name] = summary(times)
            game.reset(save=FIXTURES / "other-side-day1.sav", seed=42)
            for name, call in (("hello_roundtrip", game.hello), ("get_state", lambda: game.get_state(include_serialized=False))):
                times = []
                call()
                for _ in range(samples * 3):
                    measured(times, call)
                data[name] = summary(times)
            times = []
            for _ in range(samples):
                decision = game.reset(save=FIXTURES / "other-side-day1.sav", seed=42)["decision"]
                measured(times, lambda: game.end_turn(token=decision["token"]))
            data["native_end_turn_with_ai"] = summary(times)
            for view, selectors in (("adventure", {}), ("hero", {"hero_id": 52}), ("castle", {"castle_id": 896})):
                game.reset(save=FIXTURES / "other-side-day1.sav", seed=42)
                before = game.get_state()
                cold = []
                measured(cold, lambda: game.render(view=view, **selectors))
                times = []
                for _ in range(samples):
                    measured(times, lambda: game.render(view=view, **selectors))
                assert game.get_state() == before
                data["render_" + view] = dict(summary(times), first_request_ms=cold[0] * 1000, width=640, height=480)
            decision = game.reset(save=FIXTURES / "battles-boss-day1.sav", seed=42)["decision"]
            decision = game.move_hero(52, 32, 25, token=decision["token"])["decision"]
            while decision["phase"] == "choice":
                choice = decision["pending_choice"]
                decision = game.answer_choice(choice["choice_id"], choice["options"][0], token=decision["token"])["decision"]
            assert decision["phase"] == "battle"
            before = game.get_state()
            cold, times = [], []
            measured(cold, lambda: game.render(view="battle"))
            for _ in range(samples):
                measured(times, lambda: game.render(view="battle"))
            assert game.get_state() == before
            data["render_battle"] = dict(summary(times), first_request_ms=cold[0] * 1000, width=640, height=480)
        with HeroesEnv(executable=executable, save=FIXTURES / "other-side-day1.sav", env=environment, max_steps=20) as game:
            resets, steps = [], []
            game.reset(seed=42)
            for _ in range(samples):
                measured(resets, lambda: game.reset(seed=42))
                measured(steps, lambda: game.step(0))  # complete observation/mask/info, native AI turn
            data["gym_reset"] = summary(resets)
            data["gym_step_end_turn_with_ai"] = dict(summary(steps), steps_per_second=len(steps) / sum(steps))
        def worker(seed):
            with HeroesSession(executable, env=environment, timeout=60) as game:
                states = []
                for _ in range(samples):
                    decision = game.reset(save=FIXTURES / "other-side-day1.sav", seed=seed)["decision"]
                    decision = game.end_turn(token=decision["token"])["decision"]
                    states.append(game.get_state())
                assert all(state == states[0] for state in states)
                return len(states)
        begin = perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(worker, (71, 72)))
        data["two_parallel_sessions"] = {"completed_resets_and_ai_turns": sum(counts), "wall_seconds": perf_counter() - begin,
                                         "each_seed_reproducible": True, "same_profile_directory_no_writes": True}
        assert not list(directory.iterdir())
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("all", "scenario", "stress", "benchmark"), default="all")
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=250)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "build/python-env-acceptance/report.json")
    args = parser.parse_args()
    if not 1 <= args.episodes <= 1000 or not 1 <= args.max_steps <= 100000 or not 2 <= args.samples <= 10000:
        parser.error("Use episodes 1..1000, max-steps 1..100000, samples 2..10000")
    executable = args.executable.resolve(strict=True)
    report = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else {}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    identity = {"source_commit": revision, "executable_sha256": digest(executable)}
    if report and any(report.get(key) != value for key, value in identity.items()):
        parser.error("Existing report belongs to a different source/build; select a new --output")
    report.update(identity, schema_version=1, platform=platform.platform(), processor=platform.processor(),
                  logical_cpus=os.cpu_count(), python=platform.python_version(), updated_utc=datetime.now(timezone.utc).isoformat())
    inputs = [FIXTURES / name for name in ("other-side-day1.sav", "battles-boss-day1.sav")]
    inputs += [ROOT / name for name in ("maps/THEOTHER.MP2", "DATA/HEROES2.AGG", "DATA/HEROES2X.AGG", "files/data/resurrection.h2d")]
    input_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in inputs}
    if report.get("input_sha256") not in (None, input_hashes):
        parser.error("Existing report uses different input files; select a new --output")
    report["input_sha256"] = input_hashes
    sections = ("scenario", "stress", "benchmark") if args.section == "all" else (args.section,)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for section in sections:
        print(f"Starting {section}", flush=True)
        try:
            if section == "scenario":
                report[section] = scenario(executable)
            elif section == "stress":
                report[section] = stress(executable, args.episodes, args.max_steps)
            else:
                report[section] = benchmarks(executable, args.samples)
        except Exception as error:
            report[section] = {"passed": False, "error": {"type": type(error).__name__, "message": str(error)}}
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {section}: {args.output}", flush=True)
    if any(report.get(section, {}).get("passed") is False for section in sections):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
