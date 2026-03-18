#!/usr/bin/env python3

import argparse
import os
import os.path as osp
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


BUILTIN_CLUSTER_JSONS: Dict[str, str] = {
    "gcc12": (
        "/nfs/share/zyy/spec06_rv64gcb_O3_20m_gcc12.2.0-intFpcOff-jeMalloc/"
        "zstd-checkpoint-0-0-0/cluster-0-0.json"
    ),
    "gcc15": (
        "/nfs/home/share/checkpoints_profiles/spec06_gcc15_rv64gcb_base_260122/"
        "checkpoint-0-0-0/cluster-0-0.json"
    ),
    "xscc": (
        "/nfs/home/share/checkpoints_profiles/spec06_xscc_v1_rv64gcb_base_260122/"
        "checkpoint-0-0-0/cluster-0-0.json"
    ),
}
DEFAULT_SLICE = "gcc15"


def _find_first_file(root: str, filename: str) -> Optional[str]:
    for dirpath, _, files in os.walk(root):
        if filename in files:
            return osp.join(dirpath, filename)
    return None


def _extract_spec_all_stats(archive_path: str, out_dir: str) -> str:
    out_abs = osp.abspath(out_dir)
    extracted = 0

    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar:
            if not member.isfile():
                continue
            if not member.name.endswith("/stats.txt"):
                continue

            target_path = osp.abspath(osp.join(out_abs, member.name))
            if osp.commonpath([out_abs, target_path]) != out_abs:
                raise SystemExit(f"unsafe tar entry path: {member.name}")

            parent_dir = osp.dirname(target_path)
            os.makedirs(parent_dir, exist_ok=True)

            src = tar.extractfile(member)
            if src is None:
                continue

            with src, open(target_path, "wb") as dst:
                dst.write(src.read())
            extracted += 1

    if extracted == 0:
        raise SystemExit(f"no 'stats.txt' found in archive: {archive_path}")

    spec_all_dir = osp.join(out_abs, "spec_all")
    if osp.isdir(spec_all_dir):
        return spec_all_dir
    return out_abs


def _detect_format(stat_dir: str, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    if _find_first_file(stat_dir, "simulator_err.txt") is not None:
        return "xs"
    return "gem5"


def _run_pipeline(
    repo_root: Path,
    stat_dir: str,
    fmt: str,
    out_dir: str,
    tag: str,
    json_path: str,
    batch_args: List[str],
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    csv_path = osp.join(out_dir, f"{tag}.csv")
    weighted_path = osp.join(out_dir, f"{tag}-weighted.csv")
    score_path = osp.join(out_dir, f"{tag}-score.csv")

    batch = [sys.executable, str(repo_root / "batch.py"), "-s", stat_dir]
    if fmt == "xs":
        if "-X" not in batch_args and "--xiangshan" not in batch_args:
            batch += ["-X"]
        if "--json-filter" not in batch_args:
            # Mixed RTL result directories may contain points from multiple
            # checkpoint/profile sets. Reuse the weighting JSON as a whitelist
            # so batch.py only extracts stats for the intended SimPoint slice.
            batch += ["--json-filter", json_path]

    batch += batch_args
    batch += ["-o", csv_path]
    _run(batch, cwd=repo_root)

    cw_base = [
        sys.executable,
        "-m",
        "simpoint_cpt.compute_weighted",
        "-r",
        csv_path,
        "-j",
        json_path,
        "--out-dir",
        out_dir,
    ]
    _run(cw_base + ["-o", weighted_path], cwd=repo_root)
    _run(cw_base + ["--score", score_path], cwd=repo_root)


def _run(argv: List[str], cwd: Optional[Path] = None) -> None:
    print("+", " ".join(argv))
    subprocess.run(argv, check=True, cwd=str(cwd) if cwd is not None else None)


def main() -> None:
    repo_root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="One-shot runner: batch.py -> compute_weighted.py")
    parser.add_argument(
        "stat_dir",
        help="stats directory (GEM5 results dir or XS results dir)",
    )
    parser.add_argument(
        "--fmt",
        choices=["auto", "gem5", "xs"],
        default="auto",
        help="stats format (auto detects simulator_err.txt for xs)",
    )
    parser.add_argument(
        "--slice",
        choices=sorted(BUILTIN_CLUSTER_JSONS.keys()),
        default=DEFAULT_SLICE,
        help=f"built-in SimPoint slice preset (default: {DEFAULT_SLICE})",
    )
    parser.add_argument(
        "-j",
        "--json",
        default=None,
        help="SimPoint cluster json path (overrides --slice)",
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

    stat_dir = osp.abspath(opt.stat_dir)
    if not osp.isdir(stat_dir):
        raise SystemExit(f"stat_dir is not a directory: {opt.stat_dir}")

    json_path = osp.abspath(opt.json) if opt.json else BUILTIN_CLUSTER_JSONS[opt.slice]
    if not osp.isfile(json_path):
        raise SystemExit(f"cluster json does not exist: {json_path}")

    tag = opt.tag or osp.basename(stat_dir.rstrip("/"))
    working_stat_dir = stat_dir
    fmt = _detect_format(stat_dir, opt.fmt)
    archive_path = osp.join(stat_dir, "spec_all.tar.gz")
    spec_all_dir = osp.join(stat_dir, "spec_all")

    if fmt == "gem5":
        # CI gem5 outputs may be either unpacked (spec_all/) or archived (spec_all.tar.gz).
        if osp.isdir(spec_all_dir):
            working_stat_dir = spec_all_dir
            print(f"Detected unpacked directory: {spec_all_dir}")
        elif osp.isfile(archive_path):
            tmpdir = tempfile.mkdtemp(prefix="gem5_ci_stats_")
            working_stat_dir = _extract_spec_all_stats(archive_path, tmpdir)
            print(f"Detected archive: {archive_path}")
            print(f"Extracted stats to: {tmpdir}")
            print(f"Stats root for parsing: {working_stat_dir}")
    elif osp.isfile(archive_path) and opt.fmt == "xs":
        raise SystemExit("spec_all.tar.gz auto-extract only supports gem5 stats")

    _run_pipeline(
        repo_root=repo_root,
        stat_dir=working_stat_dir,
        fmt=fmt,
        out_dir=opt.out_dir,
        tag=tag,
        json_path=json_path,
        batch_args=batch_args,
    )
    print(f"Stats root for parsing: {working_stat_dir}")


if __name__ == "__main__":
    main()
