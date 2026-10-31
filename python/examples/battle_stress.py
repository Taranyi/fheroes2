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

"""Reproduce a bounded native battle matrix, spell probes, replay and process stress."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import tempfile
import threading
from time import perf_counter

from fheroes2_env import HeroesSession, EngineError

ROOT = Path(__file__).resolve().parents[2]
LAND = ("grass", "snow", "swamp", "lava", "desert", "dirt", "wasteland", "beach")
TERRAINS = (*LAND, "water")
RACES = ("knight", "barbarian", "sorceress", "warlock", "wizard", "necromancer")
PROFILES = ("melee", "ranged", "flying", "undead", "elemental", "immunity", "mixed", "five_slots")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def semantic(state):
    result = deepcopy(state)
    result.pop("state_version", None)
    result.pop("serialized", None)
    result["standalone_battle"]["configuration"].pop("capture_final_frame", None)
    return result


def stacks(*pairs):
    return [None if pair is None else {"monster_id": pair[0], "count": pair[1]} for pair in pairs]


def hero(hero_id, *, spells=(), skills=(), artifacts=()):
    return {"id": hero_id, "attack": 5, "defense": 5, "power": 6, "knowledge": 10,
            "spell_points": 120, "spells": list(spells),
            "skills": [{"id": key, "level": level} for key, level in skills],
            "artifacts": [{"id": value} for value in artifacts]}


def army_profile(name):
    """Concrete native IDs; no random/editor creatures and no fixture files."""
    armies = {
        "melee": (stacks((4, 18), (6, 10), (8, 4)), stacks((12, 35), (15, 12), (16, 6))),
        "ranged": (stacks((3, 12), (25, 8), (44, 3)), stacks((14, 20), (19, 8), (56, 3))),
        "flying": (stacks((33, 6), (36, 2), (40, 5)), stacks((29, 2), (43, 5), (54, 8))),
        "undead": (stacks((56, 6), (54, 8), (48, 80)), stacks((11, 4), (3, 16), (1, 100))),
        "elemental": (stacks((63, 8), (64, 8), (65, 8), (66, 8)), stacks((22, 20), (42, 8), (47, 2))),
        "immunity": (stacks((38, 2), (22, 20), (42, 8)), stacks((57, 2), (62, 8), (66, 10))),
        "mixed": (stacks(None, (3, 10), None, (61, 4), (1, 50)), stacks((49, 40), None, (55, 5), None, (58, 15))),
        "five_slots": (stacks((1, 50), (3, 12), (24, 12), (35, 3), (61, 3)),
                       stacks((12, 60), (19, 8), (42, 6), (56, 5), (57, 2))),
    }
    attacker, defender = armies[name]
    config = {"terrain": "grass", "max_rounds": 60,
              "attacker": {"army": attacker, "controller": "builtin_ai", "gold": 20000},
              "defender": {"army": defender, "controller": "builtin_ai", "gold": 20000}}
    if name != "melee":
        config["attacker"]["hero"] = hero(1, spells=(3, 11, 16, 43), skills=((2, 3),), artifacts=(64, 69))
        config["defender"]["hero"] = hero(46, spells=(3, 13, 20, 40), skills=((13, 3),))
    if name in ("elemental", "five_slots"):
        for side in ("attacker", "defender"):
            config[side]["hero"]["spells"] = list(range(1, 49))
    if name == "undead":
        config["attacker"]["hero"] = hero(46, spells=(9, 36, 37, 40), skills=((13, 3), (12, 3)))
        config["defender"]["hero"] = hero(1, spells=(9, 21, 22, 43), skills=((7, 3),))
    if name == "immunity":
        config["attacker"]["hero"]["artifacts"] = [{"id": value} for value in (56, 57, 59, 61)]
        config["defender"]["hero"]["artifacts"] = [{"id": value} for value in (46, 47, 48)]
        for side in ("attacker", "defender"):
            config[side]["hero"]["spells"] = [3, 4, 14, 21, 22, 27, 28, 31, 32, 33, 36, 37]
    if name == "mixed":
        config["attacker"].pop("hero", None)
    return config


def make_cases(profile="quick"):
    require(profile in ("quick", "full"), "Unknown stress profile")
    cases = []
    names = PROFILES if profile == "full" else ("melee", "five_slots")
    seeds = (0, 1, 2026) if profile == "full" else (2026,)
    for terrain in TERRAINS:
        for name in names:
            for seed in seeds:
                config = army_profile(name)
                config["terrain"] = terrain
                cases.append({"id": f"field/{terrain}/{name}/{seed}", "seed": seed, "family": "naval" if terrain == "water" else "field",
                              "army_profile": name, "config": config})
    for terrain_index, terrain in enumerate(LAND if profile == "full" else ("grass",)):
        for race_index, race in enumerate(RACES):
            for mask in range(8):
                for force in range(2 if profile == "full" else 1):
                    name = "ranged" if force == 0 else "flying"
                    config = army_profile(name)
                    config["terrain"] = terrain
                    # Both a visiting hero and a captain/uncommanded garrison are exercised.
                    captain = force == 0 and mask % 2 == 0
                    if force == 0:
                        config["defender"].pop("hero", None)
                    config["siege"] = {"race": race, "left_turret": bool(mask & 1), "right_turret": bool(mask & 2),
                                       "moat": bool(mask & 4), "captain": captain,
                                       "fortification": race == "knight" and (force + mask) % 2 == 1}
                    seed = 7300 + terrain_index * 1000 + race_index * 100 + mask * 3 + force
                    cases.append({"id": f"siege/{terrain}/{race}/{mask}/{force}", "seed": seed, "family": "siege", "army_profile": name, "config": config})
    for context in ("field", "siege", "naval"):
        for index, counts in enumerate(((1, 1), (1, 100000), (100000, 1), (100000, 100000)) if profile == "full" else ((100000, 100000),)):
            config = {"terrain": "water" if context == "naval" else "grass", "max_rounds": 20,
                      "attacker": {"army": stacks((47, counts[0])), "controller": "builtin_ai", "hero": hero(1, spells=range(1, 49))},
                      "defender": {"army": stacks((57, counts[1])), "controller": "builtin_ai", "hero": hero(46, spells=range(1, 49))}}
            for side in ("attacker", "defender"):
                config[side]["hero"].update(attack=99, defense=99, power=99, knowledge=99, spell_points=100000)
            if context == "siege":
                config["siege"] = {"race": "knight", "fortification": True}
            cases.append({"id": f"boundary/{context}/{index}", "seed": 91000 + index, "family": "boundary", "army_profile": "boundary_count", "config": config})
    return cases


def probe_cases(profile="quick"):
    spells = range(1, 49) if profile == "full" else (4, 5, 9, 25, 40, 41, 44, 48)
    result = []
    for terrain, siege in (("grass", False), ("snow", True), ("water", False)):
        for spell in spells:
            config = {"terrain": terrain, "max_rounds": 30,
                      "attacker": {"army": stacks((29, 2), (3, 25), (49, 30), (47, 2), (61, 2)), "controller": "python",
                                   "hero": hero(1, spells=(spell,))},
                      "defender": {"army": stacks((29, 2), (3, 25), (48, 40), (56, 3), (1, 50)), "controller": "python",
                                   "hero": hero(2, spells=(11, 16, 43))}}
            config["attacker"]["hero"].update(power=15, spell_points=500)
            if siege:
                config["siege"] = {"race": "knight", "fortification": True}
            result.append({"id": f"spell/{'siege' if siege else terrain}/{spell}", "seed": 31000 + spell,
                           "family": "spell", "army_profile": "spell_probe", "target_spell": spell, "config": config})
    return result


def agent_cases():
    result = []
    contexts = [(terrain, None) for terrain in TERRAINS] + [("grass", race) for race in RACES]
    for index, (terrain, race) in enumerate(contexts):
        for external in (1, 2):
            config = army_profile(PROFILES[index % len(PROFILES)])
            config["terrain"] = terrain
            for color, side in enumerate(("attacker", "defender"), start=1):
                config[side]["controller"] = "python" if color == external else "builtin_ai"
                # Exercise native rule profiles independently from controller assignment too.
                config[side]["rule_profile"] = "ai" if (color + index) % 2 else "human"
            if race:
                config["siege"] = {"race": race, "fortification": race == "knight"}
            result.append({"id": f"agent/{race or terrain}/{external}", "seed": 47000 + index, "family": "agent",
                           "army_profile": PROFILES[index % len(PROFILES)], "config": config})
    for index, race in enumerate(RACES):
        for external in (1, 2):
            config = army_profile("mixed")
            config["siege"] = {"race": race}
            config["attacker"]["controller"] = "python" if external == 1 else "builtin_ai"
            config["defender"]["controller"] = "python" if external == 2 else "builtin_ai"
            result.append({"id": f"agent-uncommanded/{race}/{external}", "seed": 48000 + index, "family": "agent",
                           "army_profile": "mixed", "config": config})
    return result


@contextmanager
def isolated(executable, *, timeout=30):
    work = ROOT / "build/python-env-battle-stress/profiles"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        env = dict(os.environ)
        if os.name == "nt":
            env.pop("HOME", None)
        else:
            env["HOME"] = directory
        env.update(APPDATA=directory, XDG_CONFIG_HOME=directory, XDG_DATA_HOME=directory,
                   FHEROES2_DATA=os.environ.get("FHEROES2_DATA", str(ROOT)),
                   SDL_VIDEODRIVER="nonexistent-driver", SDL_AUDIODRIVER="nonexistent-driver")
        with HeroesSession(executable, env=env, timeout=timeout) as game:
            yield game
        require(game.closed and game.returncode == 0, "Native process did not close cleanly")
        require(not list(Path(directory).iterdir()), "Battle wrote unexpected profile files")


def check_board(battle):
    require((battle["width"], battle["height"], len(battle["board"])) == (11, 9, 99), "Invalid native board dimensions")
    units = {unit["uid"]: unit for unit in battle["units"]}
    require(len(units) == len(battle["units"]), "Duplicate unit UID")
    require([cell["index"] for cell in battle["board"]] == list(range(99)), "Board index order changed")
    for unit in units.values():
        require(unit["count"] >= 0 and unit["hit_points"] >= 0 and unit["shots"] >= 0, "Negative unit data")
        require(unit["army_color"] in (1, 2), "Unit lost its owning force")
        if unit["alive"]:
            require(unit["count"] > 0 and unit["hit_points"] > 0, "Alive unit has no count/HP")
            require(0 <= unit["head"] < 99 and battle["board"][unit["head"]]["unit_uid"] == unit["uid"], "Live head/board occupancy mismatch")
            if unit["wide"]:
                require(0 <= unit["tail"] < 99 and abs(unit["tail"] - unit["head"]) == 1, "Invalid wide unit placement")
                require(battle["board"][unit["tail"]]["unit_uid"] == unit["uid"], "Live tail/board occupancy mismatch")
    for cell in battle["board"]:
        if cell["unit_uid"] is not None:
            require(cell["unit_uid"] in units and units[cell["unit_uid"]]["alive"], "Cell refers to missing/dead unit")
    require([action["action_id"] for action in battle["actions"]] == list(range(len(battle["actions"]))), "Noncontiguous legal-action IDs")
    require(all(action.get("target_uid") != battle["current_unit_uid"] for action in battle["actions"] if action["kind"] in ("shoot", "attack")),
            "Legal-action list contains a self-attack")


def check_final(state, config):
    require(state["phase"] == "terminal", "Battle failed to reach a terminal boundary")
    standalone = state["standalone_battle"]
    outcome = standalone["result"]
    require(outcome is not None and 1 <= outcome["rounds"] <= config["max_rounds"], "Invalid result/round bound")
    if outcome["truncated"]:
        require(outcome["winner_player_id"] == 0 and outcome["reason"] == "round_limit", "Truncation reported a winner")
        require(outcome["rounds"] == config["max_rounds"], "Round limit stopped at the wrong boundary")
    else:
        attacker, defender = outcome["attacker_result"], outcome["defender_result"]
        require(not (attacker & 128 and defender & 128), "Both forces won")
        winner = 1 if attacker & 128 else (2 if defender & 128 else 0)
        require(outcome["winner_player_id"] == winner, "Native result flags disagree with winner")
    perspective = standalone["configuration"]["perspective_player_id"]
    expected = 0 if outcome["truncated"] or not outcome["winner_player_id"] else (1 if outcome["winner_player_id"] == perspective else 256)
    require(state["game_result"] == expected, "Reward perspective disagrees with native outcome")
    require(len(standalone["sides"]) == 2, "Missing final force")
    for side in standalone["sides"]:
        require(len(side["army"]) == 5, "Army slot count changed")
        for troop in side["army"]:
            require(troop is None or troop["count"] > 0, "Invalid surviving troop")
    check_board(state["battle"])
    require(state["battle"]["actions"] == [], "Terminal battle offers legal actions")
    for player in state["players"]:
        side = config["attacker" if player["id"] == 1 else "defender"]
        expected_human = side.get("rule_profile", "human" if side.get("controller", "builtin_ai") == "python" else "ai") == "human"
        require(player["is_human"] == expected_human, "Controller assignment rewrote the native rule profile")


def choose_action(battle, random_source, *, target=None, target_cast=False):
    actions = battle["actions"]
    if target and not target_cast and battle["current_color"] == 1:
        spell = next((a for a in actions if a["kind"] == "spell" and a["spell_id"] == target), None)
        if spell:
            return spell
    # The opposing agent supplies buffs for dispel probes and actual damage for healing/resurrection.
    if target and battle["current_color"] == 2:
        spell = next((a for a in actions if a["kind"] == "spell" and a["spell_id"] in (11, 16, 43)), None)
        if spell:
            return spell
    for kind in ("shoot", "attack"):
        attacks = [action for action in actions if action["kind"] == kind]
        if attacks:
            return random_source.choice(attacks)
    enemies = [unit for unit in battle["units"] if unit["alive"] and unit["current_color"] != battle["current_color"]]
    moves = [action for action in actions if action["kind"] == "move"]
    if moves and enemies:
        def xy(index):
            row, col = divmod(index, 11)
            return col + .5 * (row % 2), row * .866
        def distance(action):
            x, y = xy(action["destination"])
            return min((x - xy(enemy["head"])[0]) ** 2 + (y - xy(enemy["head"])[1]) ** 2 for enemy in enemies)
        return min(moves, key=distance)
    return next(action for action in actions if action["kind"] == "skip")


def play(game, case, *, hot=False, render=False):
    begin = perf_counter()
    config = deepcopy(case["config"])
    config["capture_final_frame"] = render
    if hot:
        prepared = game.configure_battle(config, seed=case["seed"])
        decision = game.step("battle.start", token=prepared["decision"]["token"])["decision"]
    else:
        decision = game.reset(battle_config=config, seed=case["seed"])["decision"]
    trajectory = hashlib.sha256()
    random_source = random.Random(case["seed"])
    casts = []
    mana_checks = 0
    steps = 0
    while decision["phase"] == "battle":
        check_board(decision["battle"])
        trajectory.update(bytes.fromhex(digest(decision["battle"])))
        if render and steps % 17 == 0:
            before, pending = game.get_state(include_serialized=False), game.get_decision()
            frame = game.render(view="battle", width=192, height=144)
            require(len(frame.pixels) == 192 * 144 * 3, "Invalid RGB byte count")
            require(game.get_state(include_serialized=False) == before and game.get_decision() == pending, "Render changed gameplay")
        action = choose_action(decision["battle"], random_source, target=case.get("target_spell"), target_cast=case.get("target_spell") in casts)
        previous_round = decision["battle"]["round"]
        commander_key = "attacker_commander" if decision["player_id"] == 1 else "defender_commander"
        before_mana = decision["battle"][commander_key]["spell_points"] if action["kind"] == "spell" else None
        if action["kind"] == "spell":
            casts.append(action["spell_id"])
        decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
        if before_mana is not None and decision["battle"]["round"] == previous_round:
            require(decision["battle"][commander_key]["spell_points"] == before_mana - action["spell_points"], "Spell charged mana incorrectly")
            mana_checks += 1
        steps += 1
        require(steps <= 2500, "External policy exceeded its decision budget")
    state = game.get_state(include_serialized=False)
    check_final(state, config)
    runtime = game.runtime_info()
    require(runtime["headless"] and not runtime["video_initialized"] and not runtime["audio_initialized"] and not runtime["interactive_input"], "Presentation initialized in headless stress run")
    frame_hash = None
    if render:
        before = game.get_state(include_serialized=False)
        frame_hash = hashlib.sha256(game.render(view="battle", width=192, height=144).pixels).hexdigest()
        require(game.get_state(include_serialized=False) == before, "Final render changed gameplay")
    target = case.get("target_spell")
    if target:
        if target == 48 and not config.get("siege"):
            require(target not in casts, "Earthquake was offered outside siege")
        else:
            require(target in casts, f"Spell probe never exercised spell {target}")
    return {"id": case["id"], "passed": True, "seed": case["seed"], "family": case["family"], "army_profile": case["army_profile"],
            "elapsed_ms": (perf_counter() - begin) * 1000, "steps": steps, "spells_executed_by_python": sorted(set(casts)),
            "spell_mana_checks": mana_checks, "target_spell": target, "target_cast": target in casts if target else None,
            "state_sha256": digest(semantic(state)), "trajectory_sha256": trajectory.hexdigest(),
            "frame_sha256": frame_hash, "result": state["standalone_battle"]["result"]}


def run_case(executable, case, *, render=False):
    try:
        with isolated(executable) as game:
            return play(game, case, render=render)
    except Exception as error:
        return {"id": case["id"], "passed": False, "seed": case["seed"], "config": case["config"],
                "error": {"type": type(error).__name__, "message": str(error)}}


def run_matrix(executable, cases, workers=4):
    rows = []
    begin = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_case, executable, case) for case in cases]
        for future in as_completed(futures):
            rows.append(future.result())
            if len(rows) % 50 == 0:
                print(f"Completed {len(rows)}/{len(cases)} cases", flush=True)
    rows.sort(key=lambda row: row["id"])
    return {"passed": all(row["passed"] for row in rows), "scheduled": len(cases), "completed": len(rows),
            "failures": sum(not row["passed"] for row in rows), "wall_seconds": perf_counter() - begin,
            "manifest_sha256": digest(cases), "cases": rows}


def balanced_cases(cases, count):
    selected = []
    for terrain in TERRAINS:
        selected.append(next(case for case in cases if case["config"]["terrain"] == terrain and case["family"] != "siege"))
    for race in RACES:
        selected.append(next(case for case in cases if case["config"].get("siege", {}).get("race") == race))
    for name in sorted({case["army_profile"] for case in cases}):
        if not any(case["army_profile"] == name for case in selected):
            selected.append(next(case for case in cases if case["army_profile"] == name))
    for index in range(len(cases)):
        if len(selected) >= count:
            break
        candidate = cases[index * 37 % len(cases)]
        if candidate["id"] not in {case["id"] for case in selected}:
            selected.append(candidate)
    return selected[:count]


def run_replay(executable, cases):
    rows = []
    for case in cases:
        try:
            with isolated(executable) as game:
                original = play(game, case)
                game.step("session.stop", token=game.get_decision()["token"])
                hot = play(game, case, hot=True, render=True)
            fresh = run_case(executable, case)
            require(fresh["passed"], f"Fresh replay failed: {fresh}")
            for field in ("state_sha256", "trajectory_sha256", "result"):
                require(original[field] == hot[field] == fresh[field], f"Replay/render changed {field} for {case['id']}")
            rows.append({"id": case["id"], "passed": True, "state_sha256": original["state_sha256"],
                         "trajectory_sha256": original["trajectory_sha256"], "frame_sha256": hot["frame_sha256"],
                         "spells_executed_by_python": hot["spells_executed_by_python"]})
        except Exception as error:
            rows.append({"id": case["id"], "passed": False, "seed": case["seed"], "config": case["config"], "error": str(error)})
    return {"passed": all(row["passed"] for row in rows), "battles": len(cases) * 3, "comparisons": len(cases), "cases": rows}


def process_metrics(pid):
    """Read only a process owned by this test. No optional monitoring package needed."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        size = ctypes.c_size_t
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(name, size) for name in
                ("peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        kernel.GetProcessHandleCount.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            counters, handles = Counters(), wintypes.DWORD()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.GetProcessHandleCount(handle, ctypes.byref(handles)):
                raise ctypes.WinError(ctypes.get_last_error())
            return {"rss_bytes": counters.rss, "private_bytes": counters.private, "handles": handles.value}
        finally:
            kernel.CloseHandle(handle)
    if platform.system() == "Linux":
        status = (Path("/proc") / str(pid) / "status").read_text()
        rss = next(int(line.split()[1]) * 1024 for line in status.splitlines() if line.startswith("VmRSS:"))
        rollup = (Path("/proc") / str(pid) / "smaps_rollup").read_text()
        private = sum(int(line.split()[1]) * 1024 for line in rollup.splitlines() if line.startswith(("Private_Clean:", "Private_Dirty:")))
        return {"rss_bytes": rss, "private_bytes": private, "handles": len(list((Path("/proc") / str(pid) / "fd").iterdir()))}
    return None


def run_hot(executable, cases, iterations=200, memory_limit_mib=64):
    """Reuse one native process, so reset cannot hide Arena/cache/resource leaks."""
    pool = balanced_cases(cases, 24)
    samples, outcomes = [], {"wins": 0, "draws": 0, "truncated": 0}
    begin = perf_counter()
    with isolated(executable) as game:
        pid = game.pid
        # Explicitly warm all selected image/AI caches before measuring steady-state growth.
        for case in pool:
            play(game, case, hot=True, render=True)
            game.step("session.stop", token=game.get_decision()["token"])
        baseline = process_metrics(pid)
        for index in range(iterations):
            case = pool[index % len(pool)]
            row = play(game, case, hot=True, render=index % 8 == 0)
            outcome = row["result"]
            outcomes["truncated" if outcome["truncated"] else ("wins" if outcome["winner_player_id"] else "draws")] += 1
            game.step("session.stop", token=game.get_decision()["token"])
            require(game.pid == pid and not game.closed, "Hot loop silently restarted the engine")
            if index % 10 == 0 or index == iterations - 1:
                samples.append({"iteration": index + 1, "metrics": process_metrics(pid)})
        final = process_metrics(pid)
    growth = None
    if baseline is not None:
        growth = {"private_bytes": final["private_bytes"] - baseline["private_bytes"], "rss_bytes": final["rss_bytes"] - baseline["rss_bytes"],
                  "handles": final["handles"] - baseline["handles"],
                  "peak_private_growth_bytes": max(sample["metrics"]["private_bytes"] for sample in samples) - baseline["private_bytes"]}
        require(growth["private_bytes"] <= memory_limit_mib * 1024 * 1024, f"Hot-loop private memory growth exceeded bound: {growth}")
        require(growth["handles"] <= 4, f"Hot-loop native handle growth exceeded bound: {growth}")
    return {"passed": True, "iterations": iterations, "warmup_battles": len(pool), "same_process": True,
            "wall_seconds": perf_counter() - begin, "baseline": baseline, "final": final, "growth": growth,
            "samples": samples, "outcomes": outcomes, "limits": {"private_growth_mib": memory_limit_mib, "handle_growth": 4},
            "metrics_supported": baseline is not None, "clean_exit": True}


def short_external_case(index=0):
    config = {"terrain": TERRAINS[index % len(TERRAINS)], "max_rounds": 30,
              "attacker": {"army": stacks((3, 15)), "controller": "python", "hero": hero(1)},
              "defender": {"army": stacks((1, 10)), "controller": "python", "hero": hero(2)}}
    if index % 3 == 1:
        config["terrain"] = LAND[index % len(LAND)]
        config["siege"] = {"race": RACES[index % len(RACES)], "left_turret": False, "right_turret": False, "moat": False}
    return {"id": f"lifecycle/{index}", "config": config, "family": "lifecycle", "army_profile": "ranged", "seed": 80000 + index}


def run_resets(executable, iterations=100):
    modes = ("pending", "stop", "terminal", "closed", "killed")
    counts = dict.fromkeys(modes, 0)
    with isolated(executable) as game:
        for index in range(iterations):
            case = short_external_case(index)
            decision = game.reset(battle_config=case["config"], seed=case["seed"])["decision"]
            require(decision["phase"] == "battle", "Lifecycle setup finished before a Python decision")
            original = digest(semantic(game.get_state(include_serialized=False)))
            token = decision["token"]
            mode = modes[index % len(modes)]
            counts[mode] += 1
            if mode == "stop":
                game.step("session.stop", token=token)
            elif mode == "terminal":
                while decision["phase"] == "battle":
                    action = choose_action(decision["battle"], random.Random(index))
                    decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
            elif mode == "closed":
                game.close()
            elif mode == "killed":
                # Only this harness's own native child is terminated, to test crash recovery.
                os.kill(game.pid, signal.SIGTERM)
            decision = game.reset(seed=case["seed"])["decision"]
            require(digest(semantic(game.get_state(include_serialized=False))) == original, f"Reset changed initial state after {mode}")
            require(decision["token"]["session_id"] != token["session_id"], "Reset reused the old native session")
            before = game.get_state(include_serialized=False)
            try:
                game.battle_action(0, token=token)
            except EngineError as error:
                require(error.code == "wrong_session", "Old token rejected with an unexpected error")
            else:
                raise AssertionError("An old process token was accepted after reset")
            require(game.get_state(include_serialized=False) == before, "Old token changed reset state")
    return {"passed": True, "cycles": iterations, "native_resets": iterations * 2,
            "modes": counts, "expected_process_terminations": counts["killed"], "clean_final_exit": True}


def run_parallel(executable, workers=4, iterations=12):
    barrier = threading.Barrier(workers)
    tokens = [None] * workers

    def worker(worker_id):
        rows = []
        with isolated(executable) as game:
            for index in range(iterations):
                case = short_external_case(index)
                decision = game.reset(battle_config=case["config"], seed=case["seed"])["decision"]
                if index == 0:
                    tokens[worker_id] = decision["token"]
                    barrier.wait(timeout=30)
                    before = game.get_state(include_serialized=False)
                    try:
                        game.battle_action(0, token=tokens[(worker_id + 1) % workers])
                    except EngineError as error:
                        require(error.code == "wrong_session", "Another session's token was not isolated")
                    else:
                        raise AssertionError("Foreign session token was accepted")
                    require(game.get_state(include_serialized=False) == before, "Foreign token changed a parallel session")
                # Finish this pending native stack without resetting again.
                random_source = random.Random(case["seed"])
                while decision["phase"] == "battle":
                    check_board(decision["battle"])
                    action = choose_action(decision["battle"], random_source)
                    decision = game.battle_action(action["action_id"], token=decision["token"])["decision"]
                state = game.get_state(include_serialized=False)
                check_final(state, case["config"])
                rows.append(digest(semantic(state)))
        return rows

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(worker, range(workers)))
    require(all(result == results[0] for result in results), "Identical parallel seeded sessions diverged")
    return {"passed": True, "workers": workers, "battles": workers * iterations,
            "matching_seeded_results": True, "foreign_tokens_rejected": True, "clean_exits": workers}


def coverage(cases):
    return {"cases": len(cases), "terrains": sorted({case["config"]["terrain"] for case in cases}),
            "races": sorted({case["config"]["siege"]["race"] for case in cases if case["config"].get("siege")}),
            "army_profiles": sorted({case["army_profile"] for case in cases}),
            "siege_flag_combinations": sorted({sum((int(case["config"]["siege"].get(field, True)) << i) for i, field in enumerate(("left_turret", "right_turret", "moat")))
                                                for case in cases if case["config"].get("siege")}),
            "configured_spell_ids": sorted({spell for case in cases for side in ("attacker", "defender")
                                             for spell in case["config"][side].get("hero", {}).get("spells", [])})}


def identity(executable):
    files = [Path(__file__).resolve(), ROOT / "python/tests/test_battle_stress.py"]
    files += sorted((ROOT / "python/src/fheroes2_env").glob("*.py"))
    source_files = sorted((ROOT / "src/fheroes2").rglob("*.cpp")) + sorted((ROOT / "src/fheroes2").rglob("*.h"))
    assets = {}
    data_root = Path(os.environ.get("FHEROES2_DATA", ROOT))
    for relative in ("DATA/HEROES2.AGG", "DATA/HEROES2X.AGG", "files/data/resurrection.h2d"):
        path = data_root / relative
        if path.is_file():
            with path.open("rb") as stream:
                assets[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "asset_sha256": assets,
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "harness_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()},
            "native_sources_sha256": digest({str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}),
            "platform": platform.platform(), "python": platform.python_version(), "logical_cpus": os.cpu_count(),
            "created_utc": datetime.now(timezone.utc).isoformat()}


def summarize(report):
    """Keep durable evidence small; the detailed local report retains every case receipt."""
    result = deepcopy(report)
    result["report_kind"] = "summary"
    result["full_report_canonical_sha256"] = digest(report)
    for section in result["sections"].values():
        rows = section.pop("cases", None)
        if rows is not None:
            section["case_receipts_sha256"] = digest(rows)
            section["failed_cases"] = [row for row in rows if not row["passed"]]
            section["spells_executed_by_python"] = sorted({spell for row in rows for spell in row.get("spells_executed_by_python", [])})
            section["spell_mana_checks"] = sum(row.get("spell_mana_checks", 0) for row in rows)
            section["python_decisions"] = sum(row.get("steps", 0) for row in rows)
            if any("result" in row for row in rows):
                section["outcomes"] = {"winner_1": sum(row.get("result", {}).get("winner_player_id") == 1 for row in rows),
                                       "winner_2": sum(row.get("result", {}).get("winner_player_id") == 2 for row in rows),
                                       "truncated": sum(bool(row.get("result", {}).get("truncated")) for row in rows)}
    return result


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def compare_reports(left, right):
    require(left["passed"] and right["passed"], "Cross-build comparison requires two successful full reports")
    require(left["identity"]["native_sources_sha256"] == right["identity"]["native_sources_sha256"], "Native source versions differ")
    require(left["identity"]["asset_sha256"] == right["identity"]["asset_sha256"], "Game data versions differ")
    mismatches, compared = [], 0
    for name in ("matrix", "probes", "agents", "replay"):
        a = {row["id"]: row for row in left["sections"][name]["cases"]}
        b = {row["id"]: row for row in right["sections"][name]["cases"]}
        require(a.keys() == b.keys(), f"Cross-build {name} manifests differ")
        for case_id, row in a.items():
            for field in ("state_sha256", "trajectory_sha256", "result"):
                if row.get(field) != b[case_id].get(field):
                    mismatches.append({"section": name, "id": case_id, "field": field})
            compared += 1
    return {"schema_version": 1, "report_kind": "cross_build_comparison", "passed": not mismatches,
            "native_sources_sha256": left["identity"]["native_sources_sha256"],
            "left_build": left["build_label"], "right_build": right["build_label"],
            "left_executable_sha256": left["identity"]["executable_sha256"], "right_executable_sha256": right["identity"]["executable_sha256"],
            "left_full_report_canonical_sha256": digest(left), "right_full_report_canonical_sha256": digest(right),
            "compared_cases": compared, "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=ROOT / ("fheroes2.exe" if os.name == "nt" else "fheroes2"))
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--build-label", choices=("release", "debug", "custom"), default="custom")
    parser.add_argument("--section", choices=("all", "matrix", "probes", "agents", "replay", "hot", "resets", "parallel"), default="all")
    parser.add_argument("--case", help="Run just one generated matrix/probe case ID")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--hot-iterations", type=int)
    parser.add_argument("--reset-iterations", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "build/python-env-battle-stress/report.json")
    parser.add_argument("--summary", type=Path, help="Also write a compact, independently hashable report summary")
    parser.add_argument("--compare-reports", type=Path, nargs=2, help="Compare two completed full reports without running an engine")
    args = parser.parse_args()
    if args.compare_reports:
        comparison = compare_reports(*(json.loads(path.read_text(encoding="utf-8")) for path in args.compare_reports))
        write_report(args.output, comparison)
        print(f"Cross-build cases: {comparison['compared_cases']}, mismatches: {len(comparison['mismatches'])}")
        if not comparison["passed"]:
            raise SystemExit(1)
        return
    if not 2 <= args.workers <= 8 or args.hot_iterations is not None and not 1 <= args.hot_iterations <= 10000 or args.reset_iterations is not None and not 1 <= args.reset_iterations <= 1000:
        parser.error("Use workers 2..8, hot-iterations 1..10000 and reset-iterations 1..1000")
    executable = args.executable.resolve(strict=True)
    cases, probes, agents = make_cases(args.profile), probe_cases(args.profile), agent_cases()
    if args.case:
        selected = [case for case in cases + probes + agents if case["id"] == args.case]
        if not selected:
            parser.error("Unknown case ID for this profile")
        sections = ("case",)
    else:
        sections = ("matrix", "probes", "agents", "replay", "hot", "resets", "parallel") if args.section == "all" else (args.section,)
    report = {"schema_version": 1, "identity": identity(executable), "profile": args.profile,
              "build_label": args.build_label,
              "matrix_manifest_coverage": coverage(cases), "sections": {}, "passed": False}
    if args.case:
        report["selected_case_coverage"] = coverage(selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for section in sections:
        print(f"Starting {section} ({args.profile})", flush=True)
        begin = perf_counter()
        try:
            if section in ("matrix", "probes", "agents", "case"):
                selected_cases = {"matrix": cases, "probes": probes, "agents": agents, "case": selected if args.case else []}[section]
                result = run_matrix(executable, selected_cases, args.workers)
            elif section == "replay":
                replay_cases = balanced_cases(cases, 24 if args.profile == "full" else 12)
                for terrain, is_siege, spell in (("grass", False, 4), ("water", False, 5), ("snow", True, 9),
                                                 ("grass", False, 40), ("water", False, 41), ("snow", True, 44)):
                    replay_cases.append(next(case for case in probes if case["target_spell"] == spell
                                             and case["config"]["terrain"] == terrain and bool(case["config"].get("siege")) == is_siege))
                result = run_replay(executable, replay_cases)
            elif section == "hot":
                result = run_hot(executable, cases, args.hot_iterations or (200 if args.profile == "full" else 30))
            elif section == "resets":
                result = run_resets(executable, args.reset_iterations or (100 if args.profile == "full" else 15))
            else:
                result = run_parallel(executable, args.workers, 12 if args.profile == "full" else 3)
        except Exception as error:
            result = {"passed": False, "error": {"type": type(error).__name__, "message": str(error)}}
        result["wall_seconds"] = perf_counter() - begin
        report["sections"][section] = result
        report["passed"] = len(report["sections"]) == len(sections) and all(value["passed"] for value in report["sections"].values())
        write_report(args.output, report)
        if args.summary:
            write_report(args.summary, summarize(report))
        print(f"Saved {section}: passed={result['passed']} ({result['wall_seconds']:.2f}s)", flush=True)
        if not result["passed"]:
            print(json.dumps(result.get("error", [row for row in result.get("cases", []) if not row["passed"]][:5]), ensure_ascii=False), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
