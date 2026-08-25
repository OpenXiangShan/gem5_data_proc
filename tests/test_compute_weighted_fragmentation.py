import tempfile
import unittest
import warnings
from types import SimpleNamespace

import pandas as pd

import simpoint_cpt.compute_weighted as compute_weighted


class ComputeWeightedFragmentationTest(unittest.TestCase):
    def test_wide_input_does_not_emit_performance_warning(self):
        workload_df = pd.DataFrame(
            {
                "bmk": ["sample"],
                "workload": ["sample"],
                "point": [1],
                "ipc": [2.0],
            }
        )
        with warnings.catch_warnings(record=True) as setup_warnings:
            warnings.simplefilter("always", pd.errors.PerformanceWarning)
            for index in range(105):
                workload_df[f"metric_{index}"] = index
        self.assertTrue(
            any(
                issubclass(warning.category, pd.errors.PerformanceWarning)
                for warning in setup_warnings
            )
        )

        original_args = compute_weighted.args
        original_out_dir = compute_weighted.out_dir
        try:
            compute_weighted.args = SimpleNamespace(nix=False, score="score.csv")
            with tempfile.TemporaryDirectory() as tmp_dir:
                compute_weighted.out_dir = tmp_dir
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", pd.errors.PerformanceWarning)
                    compute_weighted.proc_input(
                        workload_df,
                        {
                            "sample": {
                                "insts": "100",
                                "points": {"1": "1.0"},
                            }
                        },
                        "sample",
                    )
        finally:
            compute_weighted.args = original_args
            compute_weighted.out_dir = original_out_dir

        performance_warnings = [
            warning
            for warning in caught
            if issubclass(warning.category, pd.errors.PerformanceWarning)
        ]
        self.assertEqual(performance_warnings, [])


if __name__ == "__main__":
    unittest.main()
