import re
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.common import xs_get_stats
from utils.derived_metrics import apply_derived_metrics
from utils.targets_yaml import load_groups


TARGETS = [str(Path(__file__).resolve().parents[1] / 'targets')]


class DispatchAccountingTest(unittest.TestCase):
    def setUp(self):
        self.loaded = load_groups(TARGETS, [
            'basic', 'dispatch_accounting', 'dispatch_histogram', 'rtl_dispatch',
        ])

    def test_acceptance_is_not_nostall_or_issue(self):
        pattern = self.loaded.gem5_targets['dispatch_uops']
        self.assertIsNotNone(re.fullmatch(pattern, 'system.cpu.iew.dispatchedInsts'))
        self.assertIsNotNone(re.fullmatch(pattern, 'system.cpu.iew.dispatchedInsts::total'))
        self.assertIsNone(re.fullmatch(pattern, 'system.cpu.iew.dispatchedInsts::0'))
        self.assertIsNone(re.fullmatch(pattern, 'system.cpu.iew.dispatchStallReason::NoStall'))
        rtl = re.compile(self.loaded.xs_targets['dispatch_uops'])
        self.assertIsNotNone(rtl.fullmatch(
            '[PERF ][time=42] SimTop.core.backend.ctrlBlock.dispatch: in_fire_count, 123'))
        self.assertIsNone(rtl.fullmatch(
            '[PERF ][time=42] SimTop.core.backend.ctrlBlock.rename: in_fire_count, 123'))

    def test_nostall_excess_is_preserved_and_not_called_dispatch(self):
        frame = pd.DataFrame({
            'committedInsts': [20.0], 'retired_uops': [19.0],
            'cycles': [10.0], 'dispatch_uops': [30.0],
            'dispatch_nostall_slots': [44.0], 'dispatch_histogram_samples': [10.0],
        })
        result = apply_derived_metrics(frame, self.loaded.derived)
        self.assertEqual(result.loc[0, 'dispatch_uops_per_inst'], 1.5)
        self.assertEqual(result.loc[0, 'dispatch_retire_delta'], 11)
        self.assertEqual(result.loc[0, 'dispatch_nostall_minus_fire'], 14)
        self.assertEqual(result.loc[0, 'dispatch_histogram_minus_cycles'], 0)

    def test_histogram_checks_do_not_use_mean_or_number_of_samples(self):
        # Four cycles: zero, three, three, eight dispatched uops => 14 uops.
        frame = pd.DataFrame({f'dispatch_hist_{i}': [0.0] for i in range(33)})
        frame['dispatch_hist_0'] = 1.0
        frame['dispatch_hist_3'] = 2.0
        frame['dispatch_hist_8'] = 1.0
        frame['dispatch_uops'] = 14.0
        frame['dispatch_histogram_samples'] = 4.0
        for side in ('gem5', 'xs'):
            derived = getattr(self.loaded, f'derived_{side}')
            result = apply_derived_metrics(frame.copy(), derived)
            result = apply_derived_metrics(result, self.loaded.derived)
            self.assertEqual(result.loc[0, 'dispatch_histogram_uops'], 14)
            self.assertEqual(result.loc[0, 'dispatch_histogram_minus_fire'], 0)
            self.assertEqual(result.loc[0, 'dispatch_zero_cycle_fraction'], 0.25)
        frame = frame.drop(columns='dispatch_hist_3')
        result = apply_derived_metrics(frame, self.loaded.derived_xs)
        self.assertTrue(pd.isna(result.loc[0, 'dispatch_histogram_uops']))

    def test_rtl_categories_are_not_assumed_equivalent_to_gem5(self):
        self.assertIn('rtl_dispatch_IntFlStall', self.loaded.xs_targets)
        self.assertIn('rtl_dispatch_BackendOtherCoreStall', self.loaded.xs_targets)
        self.assertNotIn('rtl_dispatch_IntFlStall', self.loaded.gem5_targets)
        self.assertNotIn('rtl_dispatch_NumStallReasons', self.loaded.xs_targets)
        result = apply_derived_metrics(pd.DataFrame({'cycles': [10]}), self.loaded.derived)
        self.assertTrue(pd.isna(result.loc[0, 'rtl_dispatch_partition_residual']))

    def test_rtl_aliases_share_values_without_faking_two_dumps(self):
        targets = {
            'committedInsts': r'commitInstr, (\d+)',
            'commitInstr': r'commitInstr, (\d+)',
            'cycles': r'cycles, (\d+)',
            'dispatch_nostall_slots': r'NoStall, (\d+)',
            'rtl_dispatch_NoStall': r'NoStall, (\d+)',
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'simulator_err.txt'
            path.write_text('commitInstr, 20\ncycles, 10\nNoStall, 30\n')
            self.assertIsNone(xs_get_stats(str(path), targets, diagnostics={}))
            path.write_text('commitInstr, 10\nNoStall, 5\n' + path.read_text())
            result = xs_get_stats(str(path), targets, diagnostics={})
            self.assertEqual(result['dispatch_nostall_slots'], 30)
            self.assertEqual(result['rtl_dispatch_NoStall'], 30)
            self.assertEqual(result['committedInsts'], 20)
            self.assertEqual(result['commitInstr'], 20)

    def test_redirect_split_uses_accepted_redirects_and_actual_roi(self):
        loaded = load_groups(TARGETS, ['intel_topdown'])
        self.assertIsNotNone(re.fullmatch(
            loaded.gem5_targets['br_mis_pred'], 'system.cpu.commit.branchMispredicts'))
        self.assertIsNotNone(re.fullmatch(
            loaded.gem5_targets['br_mis_pred'], 'system.cpu.commit.branchMispredicts::total'))
        self.assertIsNone(re.fullmatch(
            loaded.gem5_targets['br_mis_pred'], 'system.cpu.commit.branchMispredicts::0'))
        frame = pd.DataFrame({
            'committedInsts': [10.0], 'cycles': [10.0],
            'inst_spec': [30.0], 'recovery_bubble': [4.0],
            'br_mis_pred': [8.0], 'iew_br_mis_pred': [14.0], 'total_squash': [10.0],
        })
        result = apply_derived_metrics(frame, loaded.derived_gem5)
        self.assertAlmostEqual(result.loc[0, 'baseRetiring'], 0.125)
        self.assertAlmostEqual(result.loc[0, 'badSpecBound'], 0.3)
        self.assertAlmostEqual(result.loc[0, 'branchMissPrediction'], 0.24)
        self.assertAlmostEqual(result.loc[0, 'machineClears'], 0.06)


if __name__ == '__main__':
    unittest.main()
