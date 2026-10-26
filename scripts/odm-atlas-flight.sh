#!/usr/bin/env bash

#SBATCH --job-name=odm-atlas-flight
#SBATCH --account=dash_drone
#SBATCH --partition=gpu-l40s
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=01:00:00
#SBATCH --output=odm-atlas-flight-%j.out
#SBATCH --error=odm-atlas-flight-%j.err

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: sbatch $0 ORGANIZATION_GUID FLIGHT_GUID" >&2
    exit 2
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
sif="${DPU_ODM_SIF:-${dpu}/sif_files/odm-3.6.2-gpu.sif}"
python="${DPU_PYTHON:-/project/dash_drone/user/stephen.amerige/conda/drone-pilot-upload/bin/python}"

flight_root="${data_root}/site-id/${organization_id}/flights/${flight_id}"
images_dir="${flight_root}/images"
output_dir="${flight_root}/odm"
tmp_dir="${flight_root}/odm-tmp"

[[ -f "${flight_root}/mongo-registration.done.json" ]] || {
    echo "ERROR: Flight has not been registered in MongoDB: ${flight_id}" >&2
    exit 3
}
[[ -d "$images_dir" ]] || {
    echo "ERROR: Flight images directory not found: $images_dir" >&2
    exit 3
}
[[ -r "$sif" ]] || {
    echo "ERROR: ODM SIF not readable: $sif" >&2
    exit 3
}
[[ -x "$python" ]] || {
    echo "ERROR: Vegetation-index Python not executable: $python" >&2
    exit 3
}

image_count=$(find "$images_dir" -maxdepth 1 -type f \( \
    -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tif' -o -iname '*.tiff' \
    \) | wc -l)
if (( image_count == 0 )); then
    echo "ERROR: No supported image files in $images_dir" >&2
    exit 3
fi

# Never delete or overwrite an earlier processing run automatically.
if [[ -e "$output_dir" || -L "$output_dir" || -e "$tmp_dir" || -L "$tmp_dir" ]]; then
    echo "ERROR: Processing directories already exist; refusing to overwrite:" >&2
    echo "  $output_dir" >&2
    echo "  $tmp_dir" >&2
    exit 3
fi

module load apptainer/1.4.3
apptainer inspect "$sif" >/dev/null

echo "Starting Atlas ODM processing"
echo "Job: ${SLURM_JOB_ID:-unknown} on $(hostname)"
echo "Organization: $organization_id"
echo "Flight: $flight_id"
echo "Images ($image_count): $images_dir"
echo "ODM output: $output_dir"
echo "Temporary directory: $tmp_dir"

mkdir -p "$output_dir/code/images" "$tmp_dir"

apptainer run \
    --cleanenv \
    --nv \
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

echo "Starting vegetation-index processing"
"$python" "${dpu}/ortho_processing/ortho_intelligence.py" \
    "$orthophoto" "$output_dir"

for index in vari gli; do
    artifact="${output_dir}/veg_indices/${index}_image.tif"
    [[ -s "$artifact" ]] || {
        echo "ERROR: Vegetation-index artifact missing or empty: $artifact" >&2
        exit 5
    }
    echo "Validated: $artifact"
done

echo "ODM and vegetation-index processing completed successfully"
echo "Orthophoto: $orthophoto"

