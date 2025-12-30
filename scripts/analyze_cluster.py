#!/usr/bin/env python3
import json
import csv
import sys

TOP_N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

ORDER = [
    'perlbench', 'bzip2', 'gcc', 'mcf', 'gobmk', 'hmmer', 'sjeng',
    'libquantum', 'h264ref', 'omnetpp', 'astar', 'xalancbmk',
    'bwaves', 'gamess', 'milc', 'zeusmp', 'gromacs', 'cactusADM',
    'leslie3d', 'namd', 'dealII', 'soplex', 'povray', 'calculix',
    'GemsFDTD', 'tonto', 'lbm', 'wrf', 'sphinx3'
]

with open('cluster-0-0.json') as f:
    data = json.load(f)

merged = {}
for name, info in data.items():
    base = name.split('_')[0]
    if base not in merged:
        merged[base] = []
    for point, weight in info['points'].items():
        merged[base].append((name, point, float(weight)))

with open(f'cluster_top{TOP_N}.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    header = ['benchmark'] + [f'top{i+1}_{x}' for i in range(TOP_N) for x in ['name', 'weight']]
    writer.writerow(header)
    for base in ORDER:
        if base not in merged:
            continue
        points = sorted(merged[base], key=lambda x: x[2], reverse=True)[:TOP_N]
        row = [base]
        for p in points:
            row.extend([f"{p[0]}_{p[1]}", f"{p[2]*100:.1f}%"])
        writer.writerow(row)

print(f"已写入 cluster_top{TOP_N}.csv")
