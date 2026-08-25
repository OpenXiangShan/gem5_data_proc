import re
import unittest
from pathlib import Path

import pandas as pd

from utils.derived_metrics import apply_derived_metrics
from utils.targets_yaml import load_groups


REPO_ROOT = Path(__file__).resolve().parents[1]


class SmtMetricNormalizationTest(unittest.TestCase):
    def test_committed_insts_matches_single_and_smt_total_only(self):
        loaded = load_groups(
            [str(REPO_ROOT / "targets")], ["basic", "branch"]
        )
        committed_pattern = re.compile(
            loaded.gem5_targets["committedInsts"] + r"\s+(\d+)"
        )
        branches_pattern = re.compile(
            loaded.gem5_targets["branches"] + r"\s+(\d+)"
        )

        self.assertIsNotNone(
            committed_pattern.search("system.cpu.committedInsts 20000000")
        )
        self.assertIsNotNone(
            committed_pattern.search("system.cpu.committedInsts::total 40000000")
        )
        self.assertIsNone(
            committed_pattern.search("system.cpu.committedInsts::0 20000000")
        )
        self.assertIsNone(
            committed_pattern.search("system.cpu.committedInsts::1 20000000")
        )
        self.assertIsNotNone(
            branches_pattern.search("system.cpu.commit.branches 2000000")
        )
        self.assertIsNotNone(
            branches_pattern.search("system.cpu.commit.branches::total 4000000")
        )
        self.assertIsNone(
            branches_pattern.search("system.cpu.commit.branches::0 2000000")
        )

    def test_branch_mpki_uses_dynamic_committed_insts(self):
        loaded = load_groups(
            [str(REPO_ROOT / "targets")], ["basic", "branch", "microtage"]
        )
        frame = pd.DataFrame(
            {
                "BpBWrong": [100.0, 200.0],
                "BpIWrong": [20.0, 40.0],
                "BpCallWrong": [0.0, 0.0],
                "BpRetWrong": [0.0, 0.0],
                "BPAllWrong": [120.0, 240.0],
                "condPredwrong": [40.0, 80.0],
                "committedInsts": [20_000_000.0, 40_000_000.0],
                "branches": [2_000_000.0, 4_000_000.0],
            },
            index=["single", "smt"],
        )

        result = apply_derived_metrics(frame, loaded.derived)

        self.assertEqual(
            result.loc["single", "cond_MPKI"],
            result.loc["smt", "cond_MPKI"],
        )
        self.assertEqual(
            result.loc["single", "microtage_MPKI"],
            result.loc["smt", "microtage_MPKI"],
        )
        self.assertEqual(
            result.loc["single", "branch_MPKI"],
            result.loc["smt", "branch_MPKI"],
        )
        self.assertEqual(
            result.loc["single", "branch_mispredict_rate"],
            result.loc["smt", "branch_mispredict_rate"],
        )


if __name__ == "__main__":
    unittest.main()
