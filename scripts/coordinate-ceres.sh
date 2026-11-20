#!/usr/bin/env bash
# One-shot Ceres sandbox coordinator. Run only from an authorized Ceres compute
# allocation with Slurm access, MongoDB network access, and a Python environment
# containing NumPy and Rasterio. No timer/scheduler is installed by this script.
set -euo pipefail

if (( $# != 0 )); then
    echo "Usage: coordinate-ceres.sh" >&2
    exit 2
fi

host=$(hostname -s)
if [[ $host != ceres*-compute-* && $host != ceres*-mem-* ]]; then
    echo "ERROR: Ceres coordinator requires a compute allocation, not a login node: $host" >&2
    exit 2
fi

dpu="${DPU_REPO:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}"
data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
sif="${DPU_UPLOAD_SIF:-$dpu/sif_files/drone-pilot-upload.next.sif}"
secrets="${DPU_SECRETS_FILE:-$HOME/.config/drone-pilot-upload/secrets.env}"
veg_python="${DPU_VEG_PYTHON:-python3}"

[[ -d "$data_root/site-id" ]] || { echo "Flight data root unavailable" >&2; exit 1; }
[[ -r "$sif" ]] || { echo "Application SIF unavailable" >&2; exit 1; }
[[ -r "$secrets" ]] || { echo "Protected MongoDB credentials unavailable" >&2; exit 1; }

# One coordinator at a time across processes and OOD sessions.
exec 9>"$data_root/.dpu-ceres-coordinator.lock"
if ! flock -n 9; then
    echo "Another Ceres coordinator is active; skipping"
    exit 0
fi

module load apptainer/1.4.1
"$veg_python" -c 'import numpy, rasterio' || {
    echo "ERROR: DPU_VEG_PYTHON must provide NumPy and Rasterio" >&2
    exit 1
}

# Secrets never enter the Slurm ODM job environment.
set -a
# shellcheck disable=SC1090
source "$secrets"
set +a
: "${DPU_MONGODB_CONNECTION_STRING:?MongoDB credentials missing}"
export APPTAINERENV_DPU_MONGODB_CONNECTION_STRING="$DPU_MONGODB_CONNECTION_STRING"
export APPTAINERENV_DPU_MONGODB_DATABASE=drone-pilot-ceres-sandbox
export APPTAINERENV_DPU_MONGODB_COLLECTION=flight-information
unset DPU_MONGODB_CONNECTION_STRING

echo "=== Ceres: register pending flights and queue ODM ==="
apptainer exec --bind "$dpu/scripts:/opt/dpu-scripts:ro" "$sif" \
    python /opt/dpu-scripts/register-pending-flights.py \
    --sandbox ceres --data-root "$data_root" --queue-odm

echo "=== Ceres: submit pending CPU ODM jobs ==="
python3 "$dpu/scripts/submit-pending-odm.py" \
    --sandbox ceres --data-root "$data_root" --repo "$dpu" \
    --apply-resource-profile

echo "=== Ceres: collect Slurm accounting ==="
python3 "$dpu/scripts/collect-atlas-status.py" --data-root "$data_root"

echo "=== Ceres: generate missing vegetation indices and PNG previews ==="
"$veg_python" "$dpu/scripts/postprocess-ceres-flights.py" \
    --data-root "$data_root" --repo "$dpu"

echo "=== Ceres: reconcile verified results with MongoDB ==="
apptainer exec --bind "$dpu/scripts:/opt/dpu-scripts:ro" "$sif" \
    python /opt/dpu-scripts/sync-atlas-mongodb.py \
    --sandbox ceres --data-root "$data_root"

echo "=== Ceres coordinator finished successfully ==="
