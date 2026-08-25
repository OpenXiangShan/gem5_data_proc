import re
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.derived_metrics import apply_derived_metrics
from utils.targets_yaml import load_groups


REPO_ROOT = Path(__file__).resolve().parents[1]


class BackendSpecificMetricsTest(unittest.TestCase):
    def setUp(self):
        self.loaded = load_groups(
            [str(REPO_ROOT / "targets")],
            ["basic", "branch", "branch_reason", "override", "abtb"],
        )

    def test_final_branch_misses_use_non_overlapping_totals(self):
        gem5_total = re.compile(
            self.loaded.gem5_targets["BPAllWrong"] + r"\s+(\d+)"
        )

        self.assertIsNotNone(
            gem5_total.search(
                "system.cpu.branchPred.branchClassCountsTotal 123"
            )
        )
        self.assertIn(
            "commit_branch_mispredicts",
            self.loaded.xs_targets["BPAllWrong"],
        )
        self.assertNotIn(
            "commit_branch_mispredicts_type_",
            self.loaded.xs_targets["BPAllWrong"],
        )

    def test_rtl_s1_sources_are_recombined_like_gem5(self):
        gem5 = pd.DataFrame(
            {
                "committedInsts": [20_000_000.0],
                "commit_branch_mispredicts_s1_source_Fallthrough": [10.0],
                "commit_branch_mispredicts_s1_source_Ubtb": [20.0],
                "commit_branch_mispredicts_s1_source_Abtb": [70.0],
            }
        )
        rtl = pd.DataFrame(
            {
                "committedInsts": [20_000_000.0],
                "commit_branch_mispredicts_s1_source_Fallthrough": [10.0],
                "commit_branch_mispredicts_s1_source_Ubtb_raw": [20.0],
                "commit_branch_mispredicts_s1_source_UbtbUtage": [0.0],
                "commit_branch_mispredicts_s1_source_Abtb_raw": [30.0],
                "commit_branch_mispredicts_s1_source_AbtbUtage": [40.0],
            }
        )

        gem5 = apply_derived_metrics(gem5, self.loaded.derived_gem5)
        gem5 = apply_derived_metrics(gem5, self.loaded.derived)
        rtl = apply_derived_metrics(rtl, self.loaded.derived_xs)
        rtl = apply_derived_metrics(rtl, self.loaded.derived)

        self.assertEqual(
            rtl.loc[0, "commit_branch_mispredicts_s1_source_Abtb"], 70.0
        )
        self.assertEqual(
            rtl.loc[0, "s1_source_final_wrong"],
            gem5.loc[0, "s1_source_final_wrong"],
        )

    def test_abtb_and_override_patterns_use_event_semantics(self):
        rtl_hit = re.compile(self.loaded.xs_targets["abtbLookupHit"])
        rtl_override = re.compile(self.loaded.xs_targets["overrideCount"])
        gem5_miss = re.compile(
            self.loaded.gem5_targets["abtbLookupMiss"] + r"\s+(\d+)"
        )

        self.assertIsNotNone(
            rtl_hit.match(
                "[PERF ][time= 42] SimTop.cpu.l_soc.core_with_l2.core."
                "frontend.inner.bpu.abtb: predict_hit, 123"
            )
        )
        self.assertIsNone(
            rtl_hit.match(
                "[PERF ][time= 42] SimTop.cpu.l_soc.core_with_l2.core."
                "frontend.inner.bpu.mbtb: predict_hit, 123"
            )
        )
        self.assertIsNotNone(
            rtl_override.match(
                "[PERF ][time= 42] SimTop.cpu.l_soc.core_with_l2.core."
                "frontend.inner.bpu: s3Override, 456"
            )
        )
        self.assertIsNotNone(
            gem5_miss.search("system.cpu.branchPred.abtb.predMiss 789")
        )


class UniqueYamlKeyTest(unittest.TestCase):
    def test_duplicate_group_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "duplicate.yaml"
            path.write_text(
                "groups:\n"
                "  microtage:\n"
                "    gem5: {}\n"
                "  microtage:\n"
                "    xs: {}\n"
            )
            with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
                load_groups([tmp_dir], ["microtage"])


if __name__ == "__main__":
    unittest.main()
