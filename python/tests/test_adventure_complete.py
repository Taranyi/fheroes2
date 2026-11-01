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

"""Real full-map regression: native AI, native time loss and active seeded Gym replay."""

from pathlib import Path
import sys
import tempfile
import unittest

import test_world_state as support

sys.path.insert(0, str(support.ROOT / 'python/examples'))
import adventure_acceptance as acceptance

try:
    import gymnasium
except ImportError:
    gymnasium = None


class CompleteAdventureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.WorldStateTests.setUpClass()
        if not (support.ROOT / 'maps/BROKENA.MP2').exists():
            raise unittest.SkipTest('Install the original Broken Alliance map')

    def test_native_ai_summon_boat_regression_reaches_actual_map_victory(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            row = acceptance.ai_episode(support.EXECUTABLE, support.ROOT / 'maps/BROKENA.MP2', 123,
                                        Path(directory), all_ai_rules=True, max_days=512)
            self.assertTrue(row['passed'])
            self.assertTrue(row['winners'])
            self.assertGreater(row['events']['battle_completed'], 0)
            self.assertGreater(row['observed_changes']['castle_owner_changes'], 0)
            self.assertGreater(row['observed_changes']['boat_owner_or_position_changes'], 0)
            self.assertEqual(row['process_returncode'], 0)

    def test_native_fh2m_time_limit_is_a_real_loss_not_a_runner_budget(self):
        path = support.ROOT / 'maps/7_deserts.fh2m'
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            row = acceptance.ai_episode(support.EXECUTABLE, path, 123, Path(directory), max_days=32)
            self.assertTrue(row['passed'])
            self.assertTrue(row['outcomes']['1'] & 0x800)  # GameOver::LOSS_TIME
            self.assertFalse(row['winners'])
            self.assertIn((1, 1), row['native_controls'])  # native human rules, builtin AI controller

    def test_an_insufficient_harness_budget_is_explicit_failure(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            with self.assertRaisesRegex(AssertionError, 'day budget exhausted'):
                acceptance.ai_episode(support.EXECUTABLE, support.ROOT / 'maps/THEOTHER.MP2', 123,
                                      Path(directory), max_days=1)

    @unittest.skipIf(gymnasium is None, 'Install the optional gym extra')
    def test_active_gym_full_game_replays_with_matching_observations_rewards_and_commands(self):
        with tempfile.TemporaryDirectory(dir=support.ROOT / 'build') as directory:
            rows = []
            for index in range(2):
                output = Path(directory) / str(index)
                output.mkdir()
                rows.append(acceptance.gym_episode(support.EXECUTABLE, support.ROOT / 'maps/THEOTHER.MP2', 123,
                                                   output, max_steps=1200))
            self.assertEqual(rows[0]['trace_sha256'], rows[1]['trace_sha256'])
            self.assertEqual(rows[0]['final_world_sha256'], rows[1]['final_world_sha256'])
            for row in rows:
                self.assertTrue(row['terminated'])
                self.assertFalse(row['truncated'])
                self.assertEqual(row['process_returncode'], 0)
                self.assertTrue({'adventure', 'battle', 'choice'} <= row['phases'].keys())
                for command in ('hero.move', 'castle.build', 'castle.recruit', 'army.transfer', 'battle.act', 'choice.answer'):
                    self.assertGreater(row['commands'][command], 0)


if __name__ == '__main__':
    unittest.main()
