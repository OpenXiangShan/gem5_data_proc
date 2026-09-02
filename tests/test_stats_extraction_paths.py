import unittest

from utils.stats_extraction import workload_point_frompath


class WorkloadPointFromPathTest(unittest.TestCase):
    def test_flattened_legacy_names(self):
        cases = {
            "deepsjeng_77439/m5out/stats.txt": ("deepsjeng", "77439", 1),
            "xz_cld_11329/m5out/stats.txt": ("xz_cld", "11329", 1),
            "gcc_cpdecl_2233/m5out/stats.txt": ("gcc_cpdecl", "2233", 1),
        }

        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(workload_point_frompath(path), expected)

    def test_flattened_name_preserves_complete_workload(self):
        path = (
            "gcc_rate_refrate_04_ref32.opts-O3_"
            "-fselective-scheduling_-fselective-scheduling2_3383/"
            "m5out/stats.txt"
        )

        self.assertEqual(
            workload_point_frompath(path),
            (
                "gcc_rate_refrate_04_ref32.opts-O3_"
                "-fselective-scheduling_-fselective-scheduling2",
                "3383",
                1,
            ),
        )

    def test_flattened_name_with_input_index_and_dots(self):
        path = (
            "perlbench_rate_refrate_02_splitmail.6400.12.26.16.100.0_19983/"
            "m5out/stats.txt"
        )

        self.assertEqual(
            workload_point_frompath(path),
            (
                "perlbench_rate_refrate_02_splitmail.6400.12.26.16.100.0",
                "19983",
                1,
            ),
        )

    def test_legacy_weight_suffix(self):
        self.assertEqual(
            workload_point_frompath("gcc_cpdecl_2233_0.25/m5out/stats.txt"),
            ("gcc_cpdecl", "2233", 1),
        )

    def test_two_layer_layout(self):
        self.assertEqual(
            workload_point_frompath("gcc_cpdecl/2233/m5out/stats.txt"),
            ("gcc_cpdecl", "2233", 2),
        )


if __name__ == "__main__":
    unittest.main()
