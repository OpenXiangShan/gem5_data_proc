import tempfile
import unittest
from pathlib import Path

from run import (
    BUILTIN_CLUSTER_JSONS,
    DEFAULT_BENCHMARK_TYPE,
    _find_benchmark_type,
    _profile_for_benchmark_type,
)


class RunBenchmarkTypeTest(unittest.TestCase):
    def test_default_profile_is_gcc16(self):
        self.assertEqual(DEFAULT_BENCHMARK_TYPE, "gcc16")

    def test_gcc15_and_gcc16_presets_use_full_profiles(self):
        self.assertTrue(
            BUILTIN_CLUSTER_JSONS["gcc15"].endswith(
                "spec06_gcc15_rv64gcb_base_260604/json/checkpoints_all.json"
            )
        )
        self.assertTrue(
            BUILTIN_CLUSTER_JSONS["gcc16"].endswith(
                "spec06_gcc16_rva23_novec_260820/json/checkpoints_all.json"
            )
        )

    def test_ci_benchmark_types_map_to_profile_family(self):
        self.assertEqual(
            _profile_for_benchmark_type("gcc12-spec06-smt-0.3c"), "gcc12"
        )
        self.assertEqual(
            _profile_for_benchmark_type("gcc12-spec06-smt-1.0c"), "gcc12"
        )
        self.assertEqual(
            _profile_for_benchmark_type("spec06-base-gcc12-weekly"), "gcc12"
        )
        self.assertEqual(
            _profile_for_benchmark_type("gcc15-spec06-0.3c"), "gcc15"
        )
        self.assertEqual(
            _profile_for_benchmark_type("spec06-rva23-novec-gcc16-0.3c"),
            "gcc16",
        )
        self.assertEqual(
            _profile_for_benchmark_type("SPEC06-GCC16-BASE"), "gcc16"
        )

    def test_find_benchmark_type_from_run_or_spec_all_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "metadata.txt").write_text(
                "benchmark_type: gcc12-spec06-smt-1.0c\n"
            )
            spec_all = run_dir / "spec_all"
            spec_all.mkdir()

            self.assertEqual(
                _find_benchmark_type(str(run_dir)),
                "gcc12-spec06-smt-1.0c",
            )
            self.assertEqual(
                _find_benchmark_type(str(spec_all)),
                "gcc12-spec06-smt-1.0c",
            )


if __name__ == "__main__":
    unittest.main()
