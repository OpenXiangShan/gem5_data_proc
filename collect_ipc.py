#!/usr/bin/env python3
"""
收集指定切片在不同时间点的 IPC 和运行时间数据
"""

import os
import re
import glob

# ============================================================
# 配置区域 - 修改这里的切片列表
# ============================================================
# BENCHMARKS = [
#     "perlbench_diffmail_18104",
#     "bzip2_source_8439",
#     "gcc_cpdecl_2233",
#     "mcf_12253",
#     "gobmk_score2_13713",
#     "hmmer_nph3_2887",
#     "sjeng_84999",
#     "libquantum_22269",
#     "h264ref_foreman.baseline_793",
#     "omnetpp_20261",
#     "astar_rivers_9999",
#     "xalancbmk_25293",
# ]

BENCHMARKS = [
    "bwaves_37801",
    "gamess_gradient_39862",
    "milc_17368",
    "zeusmp_78888",
    "gromacs_35112",
    "cactusADM_128904",
    "leslie3d_68289",
    "namd_13387",
    "dealII_55586",
    "soplex_ref_14255",
    "povray_10202",
    "calculix_13476",
    "GemsFDTD_30385",
    "tonto_23672",
    "lbm_7139",
    "wrf_102864",
    "sphinx3_82338",
]

# 数据目录
DATA_DIR = "/nfs/home/cirunner/perf-report-kmhv3"

# 要排除的日期 (格式: YY-MM-DD)
EXCLUDE_DATES = ["25-12-16", "26-01-07"]

# ============================================================


def parse_date_from_dir(dirname):
    """从目录名提取日期，如 cr251205-xxx -> 25-12-05"""
    match = re.match(r'cr(\d{2})(\d{2})(\d{2})', dirname)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def get_stats_from_file(filepath):
    """从 simulator_out.txt 提取 IPC 和运行时间"""
    ipc, runtime = None, None
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            # 提取 IPC
            match = re.search(r'IPC = ([0-9.]+)', content)
            if match:
                ipc = float(match.group(1))
            # 提取运行时间 (ms)
            match = re.search(r'Host time spent: ([0-9,]+)ms', content)
            if match:
                runtime = int(match.group(1).replace(',', ''))
    except Exception:
        pass
    return ipc, runtime


def find_benchmark_stats(base_dir, benchmark):
    """在目录中查找指定 benchmark 的统计数据"""
    pattern = os.path.join(base_dir, f"{benchmark}_*", "simulator_out.txt")
    files = glob.glob(pattern)
    if files:
        return get_stats_from_file(files[0])
    return None, None


def main():
    # 获取所有 cr* 目录并按时间排序
    dirs = sorted([d for d in os.listdir(DATA_DIR) if d.startswith('cr')])

    # 过滤目录，提取日期
    date_dirs = []
    for d in dirs:
        date = parse_date_from_dir(d)
        if date and date not in EXCLUDE_DATES:
            date_dirs.append((date, d))

    dates = [d[0] for d in date_dirs]

    # 收集数据
    ipc_data = {}
    runtime_data = {}

    for bench in BENCHMARKS:
        ipc_data[bench] = []
        runtime_data[bench] = []
        for date, dirname in date_dirs:
            base_path = os.path.join(DATA_DIR, dirname)
            ipc, runtime = find_benchmark_stats(base_path, bench)
            ipc_data[bench].append(ipc)
            runtime_data[bench].append(runtime)

    # 输出 IPC CSV
    print("=== IPC ===")
    print("Benchmark," + ",".join(dates))
    for bench in BENCHMARKS:
        row = [bench]
        for ipc in ipc_data[bench]:
            row.append(f"{ipc:.6f}" if ipc else "")
        print(",".join(row))

    # 输出运行时间 CSV (小时)
    print()
    print("=== Runtime (hours) ===")
    print("Benchmark," + ",".join(dates))
    for bench in BENCHMARKS:
        row = [bench]
        for rt in runtime_data[bench]:
            if rt:
                hours = rt / 3600000
                row.append(f"{hours:.2f}")
            else:
                row.append("")
        print(",".join(row))


if __name__ == "__main__":
    main()
