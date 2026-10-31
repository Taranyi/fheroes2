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

"""Bounded CI checks for the reproducible native combination/stress runner."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_world_state as support

SPEC = importlib.util.spec_from_file_location("battle_stress", support.ROOT / "python/examples/battle_stress.py")
STRESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STRESS)


class BattleStressTests(unittest.TestCase):
    def test_full_manifest_covers_required_cartesian_dimensions_and_boundary_counts(self):
        cases = STRESS.make_cases("full")
        self.assertEqual(len(cases), len({case["id"] for case in cases}))
        field = [case for case in cases if case["family"] in ("field", "naval")]
        siege = [case for case in cases if case["family"] == "siege"]
        boundary = [case for case in cases if case["family"] == "boundary"]
        self.assertEqual((len(field), len(siege), len(boundary)), (216, 768, 12))
        self.assertEqual({(case["config"]["terrain"], case["army_profile"], case["seed"]) for case in field},
                         {(terrain, army, seed) for terrain in STRESS.TERRAINS for army in STRESS.PROFILES for seed in (0, 1, 2026)})
        for terrain in STRESS.LAND:
            for race in STRESS.RACES:
                selected = [case for case in siege if case["config"]["terrain"] == terrain and case["config"]["siege"]["race"] == race]
                self.assertEqual(len(selected), 16)
                self.assertEqual({(s["config"]["siege"]["left_turret"], s["config"]["siege"]["right_turret"], s["config"]["siege"]["moat"]) for s in selected},
                                 {(bool(mask & 1), bool(mask & 2), bool(mask & 4)) for mask in range(8)})
                self.assertEqual({bool(case["config"]["defender"].get("hero")) for case in selected}, {True, False})
        self.assertEqual({case["target_spell"] for case in STRESS.probe_cases("full")}, set(range(1, 49)))
        self.assertEqual(STRESS.coverage(cases)["siege_flag_combinations"], list(range(8)))

    def test_bounded_native_matrix_checks_fields_siege_naval_and_large_stacks(self):
        cases = STRESS.make_cases("full")
        ids = ("field/water/five_slots/2026", "field/snow/undead/0", "field/lava/immunity/1",
               "siege/swamp/wizard/7/0", "siege/dirt/knight/4/1", "boundary/naval/3")
        selected = [case for case in cases if case["id"] in ids]
        self.assertEqual(len(selected), len(ids))
        report = STRESS.run_matrix(support.EXECUTABLE, selected, workers=2)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["completed"], len(ids))

    def test_native_probe_targets_are_really_cast_and_charged(self):
        probes = STRESS.probe_cases("full")
        ids = ("spell/grass/4", "spell/grass/5", "spell/water/9", "spell/water/40", "spell/water/41", "spell/grass/32", "spell/siege/32", "spell/water/32",
               "spell/siege/44", "spell/siege/48", "spell/grass/48")
        report = STRESS.run_matrix(support.EXECUTABLE, [case for case in probes if case["id"] in ids], workers=2)
        self.assertTrue(report["passed"], report)
        for row in report["cases"]:
            self.assertGreater(row["spell_mana_checks"], 0)
            self.assertEqual(row["target_cast"], row["id"] != "spell/grass/48")

    def test_native_agent_routing_and_rule_profiles_across_terrain_and_castles(self):
        cases = STRESS.agent_cases()
        self.assertEqual(len(cases), 42)
        selected = [case for case in cases if case["id"] in ("agent/water/2", "agent/knight/1", "agent/wizard/2", "agent/necromancer/1", "agent/necromancer/2")
                    or case["id"].startswith("agent-uncommanded/")]
        report = STRESS.run_matrix(support.EXECUTABLE, selected, workers=2)
        self.assertTrue(report["passed"], report)

    def test_native_replay_remains_equal_after_hot_reconfiguration_and_render(self):
        matrix = STRESS.make_cases("full")
        probes = STRESS.probe_cases("full")
        selected = [next(case for case in matrix if case["id"] == "field/water/undead/1"),
                    next(case for case in matrix if case["id"] == "siege/grass/knight/7/0"),
                    next(case for case in probes if case["id"] == "spell/grass/5")]
        report = STRESS.run_replay(support.EXECUTABLE, selected)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["battles"], 9)

    def test_native_hot_process_exits_and_resource_samples_are_bounded(self):
        report = STRESS.run_hot(support.EXECUTABLE, STRESS.make_cases("quick"), iterations=10)
        self.assertTrue(report["same_process"])
        self.assertTrue(report["clean_exit"])
        if report["metrics_supported"]:
            self.assertLessEqual(report["growth"]["handles"], 4)

    def test_native_reset_recovers_pending_stopped_finished_closed_and_killed_process(self):
        report = STRESS.run_resets(support.EXECUTABLE, iterations=5)
        self.assertTrue(report["passed"])
        self.assertEqual(set(report["modes"].values()), {1})
        self.assertEqual(report["expected_process_terminations"], 1)

    def test_native_parallel_sessions_reject_each_others_tokens_and_match_seeded_results(self):
        report = STRESS.run_parallel(support.EXECUTABLE, workers=2, iterations=3)
        self.assertTrue(report["matching_seeded_results"])
        self.assertTrue(report["foreign_tokens_rejected"])
        self.assertEqual(report["clean_exits"], 2)

    def test_observation_corruption_and_native_rejection_cannot_be_reported_as_success(self):
        with STRESS.isolated(support.EXECUTABLE) as game:
            case = STRESS.short_external_case()
            decision = game.reset(battle_config=case["config"], seed=case["seed"])["decision"]
            broken = deepcopy(decision["battle"])
            alive = next(unit for unit in broken["units"] if unit["alive"])
            broken["board"][alive["head"]]["unit_uid"] = None
            with self.assertRaisesRegex(AssertionError, "occupancy"):
                STRESS.check_board(broken)
            broken = deepcopy(decision["battle"])
            broken["actions"].append({"action_id": len(broken["actions"]), "kind": "shoot", "target_uid": broken["current_unit_uid"]})
            with self.assertRaisesRegex(AssertionError, "self-attack"):
                STRESS.check_board(broken)
        bad = deepcopy(case)
        bad["config"]["attacker"]["army"] = []
        row = STRESS.run_case(support.EXECUTABLE, bad)
        self.assertFalse(row["passed"])
        self.assertEqual(row["config"], bad["config"])
        self.assertEqual(row["error"]["type"], "EngineError")

    def test_cli_writes_verifiable_full_and_compact_reports(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / "build") as directory:
            full, summary = Path(directory) / "full.json", Path(directory) / "summary.json"
            completed = subprocess.run([sys.executable, str(support.ROOT / "python/examples/battle_stress.py"),
                                        "--executable", str(support.EXECUTABLE), "--case", "field/grass/melee/2026",
                                        "--output", str(full), "--summary", str(summary)],
                                       text=True, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report, compact = json.loads(full.read_text()), json.loads(summary.read_text())
            self.assertTrue(report["passed"])
            self.assertTrue(compact["passed"])
            self.assertEqual(compact["full_report_canonical_sha256"], STRESS.digest(report))
            self.assertEqual(compact["sections"]["case"]["case_receipts_sha256"], STRESS.digest(report["sections"]["case"]["cases"]))


if __name__ == "__main__":
    unittest.main()
