import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import simpoint_cpt.compute_weighted as compute_weighted
from utils.spec_info import canonical_benchmark_name, spec_bmks


class SpecBenchmarkNamesTest(unittest.TestCase):
    def test_canonical_name_accepts_numbered_and_short_forms(self):
        self.assertEqual(canonical_benchmark_name('721.gcc'), 'gcc')
        self.assertEqual(canonical_benchmark_name('gcc'), 'gcc')
        self.assertEqual(canonical_benchmark_name('721.gcc-1'), 'gcc-1')

    def test_spec26_metadata_uses_short_names(self):
        benchmark_names = spec_bmks['26']['int'] + spec_bmks['26']['float']
        self.assertIn('gcc', benchmark_names)
        self.assertNotIn('721.gcc', benchmark_names)
        self.assertTrue(all(name == canonical_benchmark_name(name)
                            for name in benchmark_names))

        reftime_path = (
            Path(__file__).parents[1]
            / 'simpoint_cpt'
            / 'resources'
            / 'spec26_reftime.json'
        )
        with reftime_path.open() as reftime_file:
            reftime_names = set(json.load(reftime_file))
        self.assertEqual(reftime_names, set(benchmark_names))

    def test_weighting_normalizes_legacy_numbered_csv(self):
        options = SimpleNamespace(
            spec_version='26',
            int_only=False,
            fp_only=False,
            nix=False,
            score=None,
        )
        original_args = compute_weighted.args
        original_out_dir = compute_weighted.out_dir
        try:
            compute_weighted.args = options
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                csv_path = root / 'input.csv'
                json_path = root / 'weights.json'
                output_path = root / 'weighted.csv'
                workload = '706.stockfish_rate_ref'
                pd.DataFrame(
                    {
                        'bmk': ['706.stockfish'],
                        'workload': [workload],
                        'point': [1],
                        'cpi': [1.0],
                    }
                ).to_csv(csv_path)
                json_path.write_text(json.dumps({
                    workload: {
                        'insts': '100',
                        'points': {'1': '1.0'},
                    }
                }))
                compute_weighted.out_dir = str(root)

                compute_weighted.compute_weighted_metrics(
                    str(csv_path), str(json_path), str(output_path), options
                )

                weighted = pd.read_csv(output_path, index_col=0)
                self.assertIn('stockfish', weighted.index)
                self.assertNotIn('706.stockfish', weighted.index)
                self.assertEqual(weighted.loc['stockfish', 'cpi'], 1.0)
        finally:
            compute_weighted.args = original_args
            compute_weighted.out_dir = original_out_dir


if __name__ == '__main__':
    unittest.main()
