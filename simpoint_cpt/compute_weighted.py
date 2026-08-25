import utils as u
import utils.common as c
import utils.target_stats as t
import json
import pandas as pd
import numpy as np
import sys
import os.path as osp
from scipy.stats import gmean
from statistics import geometric_mean
import argparse
import re
import os
import warnings

args = []
clock_rate = 3 * 10**9
reftime_js = {}
out_dir = 'results'

def proc_input(wl_df: pd.DataFrame, js: dict, workload: str):
    # we implement the weighted metrics computation with the following formula:
    # weight = vec_weight matmul matrix_perf
    # (N, 1) = (1, W) matmul (W, N)
    # To make sure the matrix_perf is in the same order as the vec_weight,
    # we sort the matrix_perf by point
    assert type(wl_df['point'].values[0]) == np.int64
    wl_df = wl_df.sort_values(by=['point']).copy()
    # We also sort the vec_weight by point
    # print('Processing bmk input', workload)
    # workload delete the last underscore and the last part
    if args.nix:    # nix path is <num>_<benchmark>_checkpoint
        workload = '_'.join(workload.split('_')[:-1])
    wl_js = dict(js[workload])
    if 'cpi' not in wl_df.columns and 'ipc' in wl_df.columns:
        wl_df['cpi'] = 1.0 / wl_df['ipc'].replace(0, np.nan)
    if args.score:
        if 'cpi' not in wl_df.columns:
            raise SystemExit(
                f"score requires cpi (or ipc) in input csv; missing for workload: {workload}"
            )
        wl_df['cpi'] = pd.to_numeric(wl_df['cpi'], errors='coerce')
        if wl_df['cpi'].isna().all():
            raise SystemExit(
                f"score requires valid cpi values; got all-NaN for workload: {workload}"
            )
        wl_df['time'] = int(wl_js['insts']) * wl_df['cpi'] / clock_rate
    # print(wl_js['points'])
    vec_weight = pd.DataFrame.from_dict(wl_js['points'], orient='index')

    # convert string index into int64
    vec_weight.index = vec_weight.index.astype(np.int64)
    # select only existing points
    try:
        vec_weight = vec_weight.loc[wl_df['point']]
    except KeyError:
        # Find out which points are present in vec_weight
        valid_points = set(wl_df['point']).intersection(set(vec_weight.index))
        # Only the rows with corresponding weights are kept
        wl_df = wl_df[wl_df['point'].isin(valid_points)]
        vec_weight = vec_weight.loc[wl_df['point']]
        if 0 in wl_df['point'].values:
            # print(f"Ignore checkpoint 0 for {workload}")
            wl_df = wl_df[wl_df['point'] != 0]
            vec_weight = vec_weight[vec_weight.index != 0]

    # print(vec_weight.shape)
    # make their sum equals 1.0
    vec_weight.columns = ['weight']

    vec_weight['weight'] = vec_weight['weight'].astype(np.float64)
    coverage = np.sum(vec_weight.values)
    vec_weight = vec_weight / coverage
    
    # Drop these auxiliary fields

    wl_df['weight'] = vec_weight.values
    wl_df.to_csv(osp.join(out_dir, f'{workload}_raw.csv'))
    to_drop = {'bmk', 'point', 'workload', 'ipc', 'weight'}
    to_drop = to_drop.intersection(set(wl_df.columns.to_list()))
    # print(set(wl_df.columns.to_list()))
    # print(to_drop)
    wl_df = wl_df.drop(to_drop, axis=1)

    weight_metrics = np.matmul(vec_weight.values.reshape(1, -1), wl_df.values)
    decomposed = pd.DataFrame(wl_df.values * vec_weight.values, columns=wl_df.columns, index=wl_df.index)
    # print(decomposed)  # decomposed
    decomposed['weight'] = vec_weight.values
    decomposed.to_csv(osp.join(out_dir, f'{workload}_decomposed.csv'))
    weight_metrics_df = pd.DataFrame(weight_metrics, columns=wl_df.columns)
    # We have to process coverage here to avoid apply weight on top of weight
    weight_metrics_df['coverage'] = coverage
    return weight_metrics_df.values, weight_metrics_df.columns


def proc_bmk(bmk_df: pd.DataFrame, js: dict, bmk: str):
    # Similar to per-input proc, we view the instruction count as the weight
    # and compute weighted metrics with matrix multiplication
    workloads = bmk_df['workload'].unique()
    metric_list = []
    time = 0
    # print('Processing bmk', bmk)
    for wl in workloads:
        metrics, cols = proc_input(bmk_df[bmk_df['workload'] == wl], js, wl)
        if args.score:
            time += metrics[0][np.where(cols.values == 'time')[0][0]]
        metric_list.append(metrics)
        # print(f'{bmk} {wl} {metrics} {cols}')
    metrics = np.concatenate(metric_list, axis=0)
    metrics = pd.DataFrame(metrics, columns=cols)

    input_dict = {}
    for workload in workloads:
        if workload.startswith(workload):
            input_dict[workload] = int(js[workload]['insts'])
    input_insts = pd.DataFrame.from_dict(input_dict, orient='index', columns=['insts'])
    # make their sum equals 1.0
    vec_weight = input_insts / np.sum(input_insts.values)
    weight_metric = np.matmul(vec_weight.values.reshape(1, -1), metrics.values)
    if args.score:
        weight_metric[0][np.where(cols.values == 'time')[0][0]] = time
    return weight_metric, metrics.columns


def compute_weighted_metrics(csv_path: str, js_path: str, out_csv: str, args):
    spec_v = args.spec_version
    df = pd.read_csv(csv_path, index_col=0)

    # Preserve input CSV column order (batch.py already emits YAML-ordered columns).
    with open(js_path, 'r') as f:
        js = json.load(f)
    valid_workloads = set(js.keys())
    invalid_rows = df[~df['workload'].isin(valid_workloads)]
    if not invalid_rows.empty:
        dropped = sorted(invalid_rows['workload'].unique().tolist())
        # print(f"Skip workloads missing in weight json: {dropped}")
        df = df[df['workload'].isin(valid_workloads)]
    if df.empty:
        print("All workloads were filtered out; nothing to process.")
        return
    bmks = df['bmk'].unique()
    weighted = {}
    dirty_bmk_pattern = re.compile(r'(?P<name>\w+)-(?P<dirty>\d)')
    for bmk in bmks:
        m = dirty_bmk_pattern.match(bmk)
        pure_name = bmk
        if m:
            pure_name = m.group('name')
        if pure_name not in u.spec_bmks[spec_v]['int'] and args.int_only:
            print(f'{bmk} not in int list')
            continue
        if pure_name not in u.spec_bmks[spec_v]['float'] and args.fp_only:
            print(f'{bmk} not in fp list')
            continue
        df_bmk = df[df['bmk'] == bmk]
        if df_bmk.empty:
            print(f'{bmk} has no valid workloads after filtering; skip.')
            continue
        workloads = df_bmk['workload'].unique()
        n_wl = len(workloads)
        # print(workloads)
        if n_wl == 0:
            print(f'{bmk} has zero workloads; skip.')
            continue
        elif n_wl == 1:
            metrics, cols = proc_input(df_bmk, js, workloads[0])
        else:
            metrics, cols = proc_bmk(df_bmk, js, bmk)
        weighted[bmk] = metrics[0]
    if len(weighted) == 0:
        print("No benchmarks left to weight; nothing to output.")
        return
    weighted_df = pd.DataFrame.from_dict(weighted, orient='index', columns=cols)

    bmks_cleaned = []
    for bmk in weighted_df.index:
        m = dirty_bmk_pattern.match(bmk)
        if m:
            bmks_cleaned.append(m.group('name'))
        else:
            bmks_cleaned.append(bmk)
    weighted_df.index = bmks_cleaned
    pd.set_option("display.precision", 3)
    # print(bmks_cleaned)

    # sort by int and fp benchmarks, not by cpi
    int_benchmarks = u.spec_bmks[spec_v]['int']
    fp_benchmarks = u.spec_bmks[spec_v]['float']
    weighted_df = weighted_df.reindex(int_benchmarks + fp_benchmarks)

    if 'cpi' in weighted_df.columns:
        # weighted_df = weighted_df.sort_values(by='cpi', ascending=False) 
        pass
    else:
        weighted_df = weighted_df.sort_index()
    # print(weighted_df)
    if out_csv is not None:
        weighted_df.to_csv(out_csv)
    if args.score:
        score = {}
        for bmk in weighted_df.index:
            if not score.get(bmk):
                score[bmk] = {}
            # print(weighted_df.loc[bmk])
            score[bmk]['time'] = float(weighted_df.loc[bmk, 'time'])
            score[bmk]['ref_time'] = float(reftime_js[bmk])
            score[bmk]['score'] = score[bmk]['ref_time'] / score[bmk]['time']
            score[bmk]['coverage'] = weighted_df.loc[bmk, 'coverage']
        score_col = ['time','ref_time','score','coverage']
        score = pd.DataFrame.from_dict(score, orient='index', columns=score_col)
        score['score'] = score['score']/(clock_rate/(10**9))

        # Get int/fp benchmark lists
        int_bmks = [b for b in u.spec_bmks[spec_v]['int'] if b in score.index]
        fp_bmks = [b for b in u.spec_bmks[spec_v]['float'] if b in score.index]

        # Calculate averages
        int_scores = score.loc[int_bmks, 'score'].dropna() if int_bmks else pd.Series()
        fp_scores = score.loc[fp_bmks, 'score'].dropna() if fp_bmks else pd.Series()
        int_avg = geometric_mean(int_scores) if len(int_scores) > 0 else np.nan
        fp_avg = geometric_mean(fp_scores) if len(fp_scores) > 0 else np.nan
        all_scores = score['score'].dropna()
        overall_avg = geometric_mean(all_scores) if len(all_scores) > 0 else np.nan

        # Build final DataFrame with summary rows in correct positions
        rows = []
        for bmk in int_bmks:
            rows.append((bmk, score.loc[bmk]))
        if not args.fp_only and not np.isnan(int_avg):
            rows.append(('int_avg', pd.Series([np.nan, np.nan, int_avg, np.nan], index=score_col)))
        for bmk in fp_bmks:
            rows.append((bmk, score.loc[bmk]))
        if not args.int_only and not np.isnan(fp_avg):
            rows.append(('fp_avg', pd.Series([np.nan, np.nan, fp_avg, np.nan], index=score_col)))
        if not args.int_only and not args.fp_only and not np.isnan(overall_avg):
            rows.append(('overall_avg', pd.Series([np.nan, np.nan, overall_avg, np.nan], index=score_col)))

        score = pd.DataFrame.from_dict(dict(rows), orient='index', columns=score_col)

        # Print results
        print(args.score)
        print(f'================ SPEC{spec_v} =================')
        if not args.fp_only:
            intdf = score.loc[[b for b in int_bmks if b in score.index]]
            print(f'================ Int =================')
            print(intdf)
            if not np.isnan(int_avg):
                print('Estimated Int score per GHz:', int_avg)
                print(f'Estimated Int {clock_rate/(10**9)}GHz:', int_avg*(clock_rate/(10**9)))
        if not args.int_only:
            fpdf = score.loc[[b for b in fp_bmks if b in score.index]]
            print(f'================ FP =================')
            print(fpdf)
            if not np.isnan(fp_avg):
                print('Estimated FP score per GHz:', fp_avg)
                print(f'Estimated FP {clock_rate/(10**9)}GHz:', fp_avg*(clock_rate/(10**9)))
        if not args.int_only and not args.fp_only:
            print(f'================ Overall =================')
            print('Estimated overall score per GHz:', overall_avg)
            print(f'Estimated overall {clock_rate/(10**9)}GHz:', overall_avg*(clock_rate/(10**9)))

        if args.score is not None:
            score.to_csv(args.score)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(usage='specify results top directory and json')
    parser.add_argument('-r', '--results', action='store', required=True, help='results generated from batch.py')
    parser.add_argument('-j', '--json', action='store', required=True, help='json file containing weight info')
    parser.add_argument('-o', '--output', action='store', required=False, help='csv file to stall results')
    parser.add_argument('--out-dir', action='store', required=False, default='results',
                        help='directory for intermediate raw/decomposed csv (default: results)')
    parser.add_argument('-I', '--int-only', action='store_true', required=False, help='only process int')
    parser.add_argument('-F', '--fp-only', action='store_true', required=False, help='only process fp')
    parser.add_argument('-s', '--score', action='store', required=False, help='csv file to stall weighted score results')
    parser.add_argument('-c', '--clock', action='store', required=False, default=3, help='simulation clock rate(GHz)')
    parser.add_argument('-v', '--spec-version', action='store', required=False, default='06',
                        help='spec version, default is 06')
    parser.add_argument('-n', '--nix', action='store_true', required=False, help='handle nix stats')
    args = parser.parse_args()
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    clock_rate = float(args.clock) * 10**9
    if args.score:
        spec_v = args.spec_version
        path = os.path.abspath(os.path.dirname(sys.argv[0]))
        with open(path + f'/resources/spec{spec_v}_reftime.json', 'r') as f:
            reftime_js = json.load(f)
    
    compute_weighted_metrics(args.results, args.json, args.output, args)
