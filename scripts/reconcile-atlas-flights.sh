#!/usr/bin/env bash
# One-shot status reconciliation: host Slurm accounting, container MongoDB sync.
(
    set -euo pipefail
    dpu="${DPU_REPO:-/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload}"
    data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
    sif="${DPU_UPLOAD_SIF:-${dpu}/sif_files/drone-pilot-upload-20261026.sif}"
    secrets="${DPU_SECRETS_FILE:-${HOME}/.config/drone-pilot-upload/atlas-sandbox/secrets.env}"
    mode=()
    if [[ "${1:-}" == "--dry-run" ]]; then
        mode+=(--dry-run)
        shift
    fi
    if (( $# > 0 )); then
        echo "Usage: $0 [--dry-run]" >&2
        exit 2
    fi
    cd "$dpu"
    # Always refresh the local Slurm snapshot. --dry-run prevents MongoDB writes,
    # but the harmless accounting snapshot is needed for a useful preview.
    python3 scripts/collect-atlas-status.py --data-root "$data_root"
    module load apptainer/1.4.3
    unset APPTAINER_NO_MOUNT
    if [[ ${#mode[@]} -eq 0 ]]; then
        [[ -r "$secrets" ]] || { echo "Cannot read secrets file: $secrets" >&2; exit 1; }
        source "$secrets"
        : "${DPU_MONGODB_CONNECTION_STRING:?MongoDB connection string not set}"
        export APPTAINERENV_DPU_MONGODB_CONNECTION_STRING="$DPU_MONGODB_CONNECTION_STRING"
        export APPTAINERENV_DPU_MONGODB_DATABASE=drone-pilot-atlas-sandbox
        export APPTAINERENV_DPU_MONGODB_COLLECTION=flight-information
        unset DPU_MONGODB_CONNECTION_STRING
    fi
    apptainer exec "$sif" /opt/venv/bin/python \
        "$dpu/scripts/sync-atlas-mongodb.py" \
        --data-root "$data_root" "${mode[@]}"
)
