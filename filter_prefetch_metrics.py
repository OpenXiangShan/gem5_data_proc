#!/usr/bin/env python3
"""Keep only comparable prefetch accuracy and coverage metrics in a CSV."""

import argparse
from pathlib import Path

import pandas as pd


COMMON_METRICS = (
    'l1_stream_accuracy',
    'l1_stream_coverage',
    'l1_stride_accuracy',
    'l1_stride_coverage',
    'l1_total_accuracy',
    'l1_total_coverage',
    'l2_stream_accuracy',
    'l2_stream_coverage',
    'l2_stride_accuracy',
    'l2_stride_coverage',
    'l2_sms_accuracy',
    'l2_sms_coverage',
    'l2_bop_accuracy',
    'l2_bop_coverage',
    'l2_total_accuracy',
    'l2_total_coverage',
)

GEM5_ONLY_METRICS = (
    'gem5_l2_cmc_accuracy_exact',
    'gem5_l2_cmc_coverage',
)


def filter_prefetch_metrics(input_csv: Path, output_csv: Path, platform: str) -> list[str]:
    df = pd.read_csv(input_csv, index_col=0)
    identity_columns = [col for col in ('bmk', 'workload', 'point') if col in df.columns]
    requested_metrics = list(COMMON_METRICS)
    if platform == 'gem5':
        requested_metrics.extend(GEM5_ONLY_METRICS)

    selected_metrics = [col for col in requested_metrics if col in df.columns]
    df.loc[:, identity_columns + selected_metrics].to_csv(output_csv)
    return selected_metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Filter a prefetch CSV to accuracy and coverage metrics only.'
    )
    parser.add_argument('input_csv', type=Path)
    parser.add_argument('output_csv', type=Path)
    parser.add_argument('--platform', choices=('gem5', 'rtl'), required=True)
    args = parser.parse_args()

    selected = filter_prefetch_metrics(args.input_csv, args.output_csv, args.platform)
    print(f'Wrote {args.output_csv} with {len(selected)} prefetch metrics.')


if __name__ == '__main__':
    main()
