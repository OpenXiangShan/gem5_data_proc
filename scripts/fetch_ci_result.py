#!/usr/bin/env python3
"""Fetch GEM5 CI results from GitHub Actions and process them."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = "OpenXiangShan/GEM5"
GEM5_RESULTS_DIR = Path(os.environ.get("GEM5_RESULTS_DIR", "/nfs/home/yanyue/workspace/GEM5_results/CI_scores"))
SCRIPT_DIR = Path(__file__).parent.parent


def run_cmd(cmd: list[str]) -> str:
    """Run command and return output."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_run_id(url: str) -> str:
    """Extract run_id from GitHub Actions URL."""
    # https://github.com/OpenXiangShan/GEM5/actions/runs/20570962447
    match = re.search(r"/actions/runs/(\d+)", url)
    if not match:
        print(f"Error: Cannot parse run_id from URL: {url}", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def get_job_id(run_id: str) -> str:
    """Get job_id from run_id."""
    output = run_cmd(["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/jobs"])
    data = json.loads(output)
    if not data.get("jobs"):
        print("Error: No jobs found", file=sys.stderr)
        sys.exit(1)
    return str(data["jobs"][0]["id"])


def get_ci_path(job_id: str) -> str:
    """Extract performance data path from job logs."""
    output = run_cmd(["gh", "api", f"repos/{REPO}/actions/jobs/{job_id}/logs"])
    match = re.search(r"Archiving performance data to (/nfs/home/share/gem5_ci/performance_data/\S+)", output)
    if not match:
        print("Error: Cannot find performance data path in logs", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description="Fetch GEM5 CI results")
    parser.add_argument("url", help="GitHub Actions run URL")
    parser.add_argument("-n", "--name", help="Custom name for the result directory")
    parser.add_argument("--no-process", action="store_true", help="Skip running gem5-topdown-tag.sh")
    args = parser.parse_args()

    # Check results directory
    if not GEM5_RESULTS_DIR.exists():
        print(f"Warning: Results directory does not exist: {GEM5_RESULTS_DIR}", file=sys.stderr)
        print(f"  Set GEM5_RESULTS_DIR environment variable to change it.", file=sys.stderr)
        sys.exit(1)
    print(f"Results directory: {GEM5_RESULTS_DIR}")

    # Extract path from CI
    print(f"Fetching CI results from: {args.url}")
    run_id = get_run_id(args.url)
    print(f"Run ID: {run_id}")

    job_id = get_job_id(run_id)
    print(f"Job ID: {job_id}")

    ci_path = get_ci_path(job_id)
    print(f"CI Path: {ci_path}")

    # Get name
    if args.name:
        name = args.name
    else:
        default_name = Path(ci_path).name
        name = input(f"Enter name for result directory [{default_name}]: ").strip()
        if not name:
            name = default_name

    # Check if destination exists
    final_dir = GEM5_RESULTS_DIR / name
    if final_dir.exists():
        overwrite = input(f"{final_dir} already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)
        shutil.rmtree(final_dir)

    # Copy to temp directory first
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "ci_result"
        print(f"Copying {ci_path} -> {tmp_path}")
        shutil.copytree(ci_path, tmp_path)

        # Extract spec_all.tar.gz
        tar_file = tmp_path / "spec_all.tar.gz"
        if tar_file.exists():
            print(f"Extracting {tar_file}")
            with tarfile.open(tar_file, "r:gz") as tar:
                tar.extractall(tmp_path)

            # Move spec_all to final destination with user's name
            extracted_dir = tmp_path / "spec_all"
            if extracted_dir.exists():
                print(f"Moving to {final_dir}")
                shutil.move(str(extracted_dir), str(final_dir))
            else:
                print("Warning: spec_all directory not found after extraction")
        else:
            print(f"Warning: {tar_file} not found, copying entire directory")
            shutil.copytree(tmp_path, final_dir)

    print("Done.")

    # Run processing script
    if not args.no_process and final_dir and final_dir.exists():
        print(f"\nRunning gem5-topdown-tag.sh {final_dir}")
        subprocess.run(
            ["bash", "example-scripts/gem5-topdown-tag.sh", str(final_dir)],
            cwd=SCRIPT_DIR
        )


if __name__ == "__main__":
    main()
