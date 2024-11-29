set -x

ulimit -n 4096

# usage:
# bash example-scripts/gem5-score-ci.sh  \
# /nfs/home/yanyue/workspace/GEM5/util/xs_scripts/test/spec_gcc15_gcb_zicond_new \
# /nfs/home/yanyue/workspace/checkpoint_scripts/checkpoint_scripts/archive/spec06_gcc15_rv64gcb_zicond_O3_lto_base_nemu_single_core_NEMU_archgroup_2024-11-01-18-30/checkpoint-0-0-0/cluster-0-0.json

example_stats_dir=$1
json_path=$2

mkdir -p results

tag="gem5-score-example"
python3 batch.py -s $example_stats_dir -o results/$tag.csv

python3 simpoint_cpt/compute_weighted.py \
    -r results/$tag.csv \
    -j $json_path \
    --score results/$tag-score.csv
