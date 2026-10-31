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

"""Check masked probability, value and gradient equivalence of candidate packing."""

import sys
import unittest
from pathlib import Path

READY = False
try:
    import torch
    import numpy as np
    from gymnasium import spaces
    import sb3_contrib
except ImportError:
    pass
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'examples'))
    from battle_ppo import CandidatePolicy
    from packed_policy import PackedCandidatePolicy
    READY = True


@unittest.skipUnless(READY, 'Install optional battle-rl extra')
class PackedPolicyTests(unittest.TestCase):
    def test_probabilities_values_and_gradients_match_with_variable_masks(self):
        torch.set_num_threads(1)
        torch.manual_seed(439)
        observation = spaces.Box(-np.inf, np.inf, (512, 97), dtype=np.float32)
        actions = spaces.Discrete(512)
        original = CandidatePolicy(observation, actions, lambda _: .001)
        with torch.no_grad():
            original.actor[-1].weight.normal_(0, .2)
        packed = PackedCandidatePolicy(observation, actions, lambda _: .001)
        packed.load_state_dict(original.state_dict())
        x = torch.randn(4, 512, 97) * .2
        mask = torch.zeros(4, 512, dtype=torch.bool)
        for row, count in enumerate((9, 35, 150, 230)):
            x[row, :count, 0] = 1
            x[row, count:] = 0
            mask[row, :count] = True
        mask[:, 0] = False  # an additional caller restriction, e.g. spell ablation
        a = original.get_distribution(x, mask).distribution.probs.clone()
        b = packed.get_distribution(x, mask).distribution.probs.clone()
        torch.testing.assert_close(a, b, rtol=1e-6, atol=1e-7)
        self.assertTrue(torch.all(b[~mask] == 0))
        torch.testing.assert_close(original.predict_values(x), packed.predict_values(x), rtol=0, atol=0)
        for policy in (original, packed):
            values, logs, entropy = policy.evaluate_actions(x, torch.ones(4, dtype=torch.int64), mask)
            loss = -logs.mean() + values.square().mean() - .01 * entropy.mean()
            loss.backward()
        for (name, a), (_, b) in zip(original.named_parameters(), packed.named_parameters()):
            with self.subTest(parameter=name):
                torch.testing.assert_close(a.grad, b.grad, rtol=1e-5, atol=1e-6)


if __name__ == '__main__':
    unittest.main()
