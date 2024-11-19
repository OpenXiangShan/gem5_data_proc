set -x

ulimit -n 4096

export PYTHONPATH=`pwd`

example_stats_dir=/nfs/home/fengkehan/gem5_data_proc/ckpt_all_logs

mkdir -p results

tag="xs"

python3 pldm_log_get.py --logfile $example_stats_dir --outfile results/output_pldm.csv
python3 simpoint_cpt/compute_weighted.py --int-only \
    -r results/output_pldm.csv \
    -j /nfs/home/fengkehan/gem5_data_proc/cluster-0-0.json \
    --score results/$tag-score.csv
