#!/usr/bin/env python3

import argparse
import os
import os.path as osp
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


DEFAULT_CLUSTER_JSON = (
    "/nfs/share/zyy/spec06_rv64gcb_O3_20m_gcc12.2.0-intFpcOff-jeMalloc/"
    "zstd-checkpoint-0-0-0/cluster-0-0.json"
)


def _find_first_file(root: str, filename: str) -> Optional[str]:
    for dirpath, _, files in os.walk(root):
        if filename in files:
            return osp.join(dirpath, filename)
    return None


def _detect_format(stat_dir: str, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    if _find_first_file(stat_dir, "simulator_err.txt") is not None:
        return "xs"
    return "gem5"


def _run(argv: List[str]) -> None:
    print("+", " ".join(argv))
    subprocess.run(argv, check=True)


def main() -> None:
    repo_root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="One-shot runner: batch.py -> compute_weighted.py")
    parser.add_argument("stat_dir", help="stats directory (GEM5 results dir or XS results dir)")
    parser.add_argument(
        "--fmt",
        choices=["auto", "gem5", "xs"],
        default="auto",
        help="stats format (auto detects simulator_err.txt for xs)",
    )
    parser.add_argument(
        "-j",
        "--json",
        default=DEFAULT_CLUSTER_JSON,
        help="SimPoint cluster json path (default: repo script default)",
    )
    parser.add_argument(
        "--out-dir",
        default="results",
        help="output directory for csv/weighted/score",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="override output tag name (default: basename of stat dir or input tag)",
    )

    # Forward any unknown args to batch.py, so we don't need to maintain 2 CLIs.
    # This also avoids the "options after stat_dir" pitfall from argparse.REMAINDER.
    opt, batch_args = parser.parse_known_args()
    if batch_args and batch_args[0] == "--":
        batch_args = batch_args[1:]

    if not osp.isdir(opt.stat_dir):
        raise SystemExit(f"stat_dir is not a directory: {opt.stat_dir}")

    stat_dir = osp.abspath(opt.stat_dir)
    inferred_tag = osp.basename(stat_dir.rstrip("/"))
    tag = opt.tag or inferred_tag

    fmt = _detect_format(stat_dir, opt.fmt)
    os.makedirs(opt.out_dir, exist_ok=True)

    csv_path = osp.join(opt.out_dir, f"{tag}.csv")
    weighted_path = osp.join(opt.out_dir, f"{tag}-weighted.csv")
    score_path = osp.join(opt.out_dir, f"{tag}-score.csv")

    batch = [sys.executable, str(repo_root / "batch.py"), "-s", stat_dir]
    if fmt == "xs":
        if "-X" not in batch_args and "--xiangshan" not in batch_args:
            batch += ["-X"]

    batch += batch_args
    batch += ["-o", csv_path]

    _run(batch)

    cw_base = [
        sys.executable,
        str(repo_root / "simpoint_cpt" / "compute_weighted.py"),
        "-r",
        csv_path,
        "-j",
        opt.json,
        "--out-dir",
        opt.out_dir,
    ]

    _run(cw_base + ["-o", weighted_path])
    _run(cw_base + ["--score", score_path])


if __name__ == "__main__":
    main()
