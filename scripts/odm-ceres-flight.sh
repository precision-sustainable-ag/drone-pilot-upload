#!/usr/bin/env bash
#
# One-shot, CPU-only ODM processing on Ceres. No MongoDB writes or Slurm
# submission are performed by this script; an operator must submit it with sbatch.
#
#SBATCH --job-name=odm-ceres-flight
#SBATCH --account=dash_drone
#SBATCH --partition=ceres
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=odm-ceres-flight-%j.out
#SBATCH --error=odm-ceres-flight-%j.err

set -euo pipefail

if (( $# != 2 && $# != 4 )); then
    echo "Usage: sbatch $0 ORGANIZATION_GUID FLIGHT_GUID [--retry-from-job FAILED_JOB_ID]" >&2
    exit 2
fi
retry_from_job=""
if (( $# == 4 )); then
    if [[ "$3" != "--retry-from-job" || ! "$4" =~ ^[0-9]+$ ]]; then
        echo "ERROR: Retry requires --retry-from-job followed by a numeric failed job ID" >&2
        exit 2
    fi
    retry_from_job="$4"
fi

organization_id="$1"
flight_id="$2"
uuid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
if [[ ! "$organization_id" =~ $uuid_re || ! "$flight_id" =~ $uuid_re ]]; then
    echo "ERROR: Both identifiers must be lowercase UUIDs" >&2
    exit 2
fi

dpu="${DPU_REPO:-/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload}"
data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
sif="${DPU_ODM_SIF:-${dpu}/sif_files/odm-3.6.2-cpu.sif}"
flight_root="${data_root}/site-id/${organization_id}/flights/${flight_id}"
images_dir="${flight_root}/images"
output_dir="${flight_root}/odm"
tmp_dir="${flight_root}/odm-tmp"
if [[ -n "$retry_from_job" ]]; then
    retry_parent="${flight_root}/odm-retries"
    if [[ -L "$retry_parent" ]]; then
        echo "ERROR: Retry parent must not be a symbolic link: $retry_parent" >&2
        exit 3
    fi
    attempt_root="${retry_parent}/retry-${retry_from_job}"
    output_dir="${attempt_root}/odm"
    tmp_dir="${attempt_root}/odm-tmp"
fi

[[ -f "${flight_root}/mongo-registration.done.json" ]] || {
    echo "ERROR: Registration receipt not found: ${flight_id}" >&2
    exit 3
}
[[ -d "$images_dir" ]] || {
    echo "ERROR: Flight images missing: $images_dir" >&2
    exit 3
}
[[ -r "$sif" ]] || {
    echo "ERROR: CPU ODM image not readable: $sif" >&2
    exit 3
}

image_count=$(find "$images_dir" -maxdepth 1 -type f \( \
    -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tif' -o -iname '*.tiff' \
    \) | wc -l)
(( image_count > 0 )) || {
    echo "ERROR: No supported images in $images_dir" >&2
    exit 3
}

# A failed or completed run is never overwritten automatically.
if [[ -e "$output_dir" || -L "$output_dir" || -e "$tmp_dir" || -L "$tmp_dir" ]]; then
    echo "ERROR: ODM output or temporary directory already exists; refusing overwrite" >&2
    exit 3
fi

module load apptainer/1.4.1
apptainer inspect "$sif" >/dev/null

echo "Ceres ODM (CPU-only)"
echo "Job: ${SLURM_JOB_ID:-unknown} on $(hostname)"
echo "Organization: $organization_id"
echo "Flight: $flight_id"
echo "Images: $image_count"
echo "ODM output: $output_dir"

# Claim a fresh retry workspace atomically. Existing attempts are never reused.
if [[ -n "$retry_from_job" ]]; then
    mkdir -p "$retry_parent"
    if ! mkdir "$attempt_root"; then
        echo "ERROR: Retry workspace already exists; reconcile before resubmitting: $attempt_root" >&2
        exit 3
    fi
fi
mkdir -p "$output_dir/code/images" "$tmp_dir"

apptainer run \
    --cleanenv \
    --bind "${images_dir}:${output_dir}/code/images:ro","${tmp_dir}" \
    --writable-tmpfs \
    "$sif" \
    --project-path "$output_dir" \
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

orthophoto="${output_dir}/code/odm_orthophoto/odm_orthophoto.tif"
[[ -s "$orthophoto" ]] || {
    echo "ERROR: ODM orthophoto missing or empty: $orthophoto" >&2
    exit 4
}

echo "Ceres ODM orthophoto generated successfully: $orthophoto"
echo "Vegetation indices and MongoDB reconciliation are separate, subsequent steps."
