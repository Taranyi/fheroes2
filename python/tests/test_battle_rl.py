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

"""Validate policy gradients, held-out splits, real training and fair env timings."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_world_state as support

try:
    import numpy as np
    import gymnasium
except ImportError:
    np = None

SPEC = importlib.util.spec_from_file_location("battle_rl", support.ROOT / "python/examples/battle_rl.py")
RL = None
if np is not None:
    RL = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(RL)


@unittest.skipIf(RL is None, "Install optional gym extra")
class BattleRLTests(unittest.TestCase):
    def test_policy_gradient_matches_finite_differences_with_entropy(self):
        policy = RL.Policy(seed=17, hidden=3)
        rng = np.random.default_rng(31)
        policy.params["w2"] = rng.normal(0, .2, 3)
        features = rng.normal(0, .3, (5, len(RL.FEATURES)))
        gradients, _ = policy.gradients(features, 3, .7, entropy=.03)
        for name, indices in (("w1", ((0, 0), (5, 2), (23, 1))), ("b1", ((0,), (2,))), ("w2", ((0,), (2,)))):
            for index in indices:
                original = policy.params[name][index]
                policy.params[name][index] = original + 1e-6
                _, upper = policy.gradients(features, 3, .7, entropy=.03)
                policy.params[name][index] = original - 1e-6
                _, lower = policy.gradients(features, 3, .7, entropy=.03)
                policy.params[name][index] = original
                self.assertAlmostEqual(gradients[name][index], (upper - lower) / 2e-6, places=6)

    def test_initial_policy_is_uniform_and_reward_updates_and_json_roundtrip_are_real(self):
        policy = RL.Policy(seed=5)
        features = np.zeros((3, len(RL.FEATURES)))
        features[0, 1] = features[1, 2] = features[2, 3] = 1
        initial = policy.export()
        probabilities, _ = policy.forward(features)
        np.testing.assert_array_equal(probabilities, np.full(3, 1 / 3))
        for _ in range(8):
            policy.update([{"return": 1.0, "trajectory": [(features, 2)]}], baseline=0)
        self.assertGreater(policy.forward(features)[0][2], 1 / 3)
        self.assertNotEqual(policy.export()["parameters"], initial["parameters"])
        restored = RL.Policy.restore(json.loads(json.dumps(policy.export())))
        np.testing.assert_array_equal(policy.forward(features)[0], restored.forward(features)[0])
        bad = deepcopy(policy.export())
        bad["parameters"]["w2"][0] = float("nan")
        with self.assertRaises(AssertionError):
            RL.Policy.restore(bad)

    def test_evaluation_native_seeds_are_disjoint_and_pairing_is_checked(self):
        validation, test, ood = (RL.evaluation_cases(name, 3) for name in ("validation", "test", "ood"))
        groups = [set(range(4096)), *({case["seed"] for case in cases} for cases in (validation, test, ood))]
        for index, group in enumerate(groups):
            for other in groups[index + 1:]:
                self.assertFalse(group & other)
        good = [{"id": str(i), "return": 1.0} for i in range(12)]
        bad = [{"id": str(i), "return": -1.0} for i in range(12)]
        self.assertEqual(RL.paired_improvement(good, bad)["paired_bootstrap_95"], [1.0, 1.0])
        bad[0]["id"] = "different"
        with self.assertRaises(AssertionError):
            RL.paired_improvement(good, bad)

    def test_native_masked_rollout_and_small_training_produce_reloadable_weights(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / "build") as directory:
            with RL.create_env(support.EXECUTABLE, directory) as env:
                case = RL.evaluation_cases("validation", 1)[0]
                obs, _ = env.reset(seed=case["seed"], options={"battle_config": case["config"]})
                slots, features = RL.action_features(obs)
                self.assertEqual(features.shape, (len(slots), len(RL.FEATURES)))
                self.assertTrue(np.all(obs["action_mask"][slots] == 1))
                self.assertTrue(np.isfinite(features).all())
                best, report = RL.train(env, seed=7, episodes=16, validation=RL.evaluation_cases("validation", 1),
                                        output=Path(directory) / "weights", checkpoint_every=8)
                self.assertEqual(report["training"]["episodes"], 16)
                self.assertTrue(all(0 <= seed < 4096 for seed in report["train_native_seeds"]))
                self.assertGreater(best["model"]["updates"], 0)
                score, receipts = RL.evaluate(env, [case], policy=RL.Policy.restore(best["model"]))
                self.assertEqual(score["episodes"], 1)
                self.assertTrue(receipts[0]["terminated"] or receipts[0]["truncated"])

    def test_native_benchmark_runs_matching_action_traces_with_different_observation_sizes(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / "build") as directory:
            cases = [RL.evaluation_cases("validation", 1)[index] for index in (0, 4, 8)]
            result = RL.benchmark(support.EXECUTABLE, directory, cases)
            self.assertTrue(result["matched_native_action_traces"])
            self.assertGreater(result["gym_default"]["observation_bytes"], result["gym_compact"]["observation_bytes"])
            self.assertEqual(result["gym_default"]["steps"], result["gym_compact"]["steps"])
            self.assertGreater(result["raw_session"]["step"]["samples"], 0)


if __name__ == "__main__":
    unittest.main()
