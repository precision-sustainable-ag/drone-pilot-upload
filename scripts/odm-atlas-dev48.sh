#!/usr/bin/env bash

#SBATCH --job-name=odm-atlas-dev48
#SBATCH --account=dash_drone
#SBATCH --partition=gpu-l40s
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=01:00:00
#SBATCH --output=odm-atlas-dev48-%j.out
#SBATCH --error=odm-atlas-dev48-%j.err

set -euo pipefail

flight_id="e48d496c-e7d1-4345-8fc2-42fbc78b3b28"

dpu="/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload"
data_root="/project/dash_drone/user/stephen.amerige/dpu-data/odm/${flight_id}"

images_dir="${data_root}/images-renamed-subset48"
output_dir="${data_root}/output-dev48-atlas"
tmp_dir="${data_root}/tmp-dev48-atlas"
sif="${dpu}/sif_files/odm-3.6.2-gpu.sif"

module load apptainer/1.4.3

echo "Starting ODM Atlas Dev48 Run"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Host: $(hostname)"
echo "Images: ${images_dir}"
echo "Output: ${output_dir}"
echo "Temporary storage: ${tmp_dir}"
echo "SIF: ${sif}"
echo "Image count: $(find "${images_dir}" -maxdepth 1 -type f | wc -l)"

#
# Start with clean processing directories so this run cannot reuse
# artifacts from a previous dev48 execution.
#
rm -rf "${output_dir}"
rm -rf "${tmp_dir}"

mkdir -p "${output_dir}/code/images"
mkdir -p "${tmp_dir}"

apptainer run \
    --nv \
    --bind "${images_dir}:${output_dir}/code/images:ro","${tmp_dir}" \
    --writable-tmpfs \
    "${sif}" \
    --project-path "${output_dir}" \
    --dtm \
    --orthophoto-resolution 0.01 \
    --smrf-threshold 0.4 \
    --smrf-window 24 \
    --dsm \
    --min-num-features 10000 \
    --orthophoto-compression LZW \
    --feature-type sift \
    --pc-quality medium \
    --max-concurrency 4

echo
echo "ODM Atlas Dev48 Run completed successfully"
echo "Orthophoto:"
echo "  ${output_dir}/code/odm_orthophoto/odm_orthophoto.tif"
