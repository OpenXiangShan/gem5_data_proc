#!/usr/bin/env bash
set -euo pipefail

set -x

# 打印当前工作目录
echo "Current working directory: $(pwd)"

json_path=/nfs/share/zyy/spec06_rv64gcb_O3_20m_gcc12.2.0-intFpcOff-jeMalloc/zstd-checkpoint-0-0-0/cluster-0-0.json

# spec 17 json
# json_path=/nfs/home/yanyue/spec17_cpts/checkpoint-0-0-0/cluster-0-0.json

# 根据输入参数tag, 在GEM5_stable/ GEM5_ideal 路径下寻找example_stats_dir
tag=$1
if [ -z "$tag" ]; then
    echo "tag is empty"
    exit 1
fi
echo "tag: $tag"
dirs_stable="/nfs/home/yanyue/workspace/GEM5_stable/util/xs_scripts/test/$tag"
dirs_ideal="/nfs/home/yanyue/workspace/GEM5_ideal/util/xs_scripts/test/$tag"
dirs_4="/nfs/home/yanyue/workspace/GEM5_4/util/xs_scripts/test/$tag"
if [ -d "$dirs_stable" ]; then
    example_stats_dir=$dirs_stable
elif [ -d "$dirs_ideal" ]; then
    example_stats_dir=$dirs_ideal
elif [ -d "$dirs_4" ]; then
    example_stats_dir=$dirs_4
else
    echo "example_stats_dir is not found"
    example_stats_dir=$1
    # tag 为example_stats_dir 最后一部分
    tag=$(basename "$example_stats_dir")
fi
echo "example_stats_dir: $example_stats_dir"

ARGS=""
# ARGS="-t --topdown-raw"
ARGS+=" --branch"       

# for RTL Score, add --xiangshan/-X
# ARGS+=" -X"

python3 batch.py -s $example_stats_dir $ARGS -o results/$tag.csv

# INT_ONLY="--int-only"
INT_ONLY=""

spec17=false
if $spec17; then
    spec17_args="-v 17"
    json_path=/nfs/home/yanyue/spec17_cpts/checkpoint-0-0-0/cluster-0-0.json
else
    spec17_args=""
fi


python3 simpoint_cpt/compute_weighted.py \
    -r results/$tag.csv \
    -j $json_path \
    $INT_ONLY \
    $spec17_args \
    -o results/$tag-weighted.csv

# for spec17, add -v 17
python3 simpoint_cpt/compute_weighted.py \
    -r results/$tag.csv \
    -j $json_path \
    $INT_ONLY \
    $spec17_args \
    --score results/$tag-score.csv
