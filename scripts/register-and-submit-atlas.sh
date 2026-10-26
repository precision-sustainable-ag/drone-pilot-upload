#!/usr/bin/env bash
# One-shot Atlas sandbox workflow: register MongoDB metadata, then submit ODM.
# Run on the authorized Atlas login host (not in an OOD compute allocation).
(
    set -euo pipefail

    dpu="${DPU_REPO:-/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload}"
    data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
    sif="${DPU_UPLOAD_SIF:-${dpu}/sif_files/drone-pilot-upload-20261026.sif}"
    secrets="${DPU_SECRETS_FILE:-${HOME}/.config/drone-pilot-upload/atlas-sandbox/secrets.env}"

    cd "$dpu"
    unset APPTAINER_NO_MOUNT  # May be set during local SIF builds.
    module load apptainer/1.4.3
    [[ -r "$secrets" ]] || { echo "Secrets file is unreadable: $secrets" >&2; exit 1; }
    source "$secrets"
    : "${DPU_MONGODB_CONNECTION_STRING:?MongoDB connection string not configured}"

    export APPTAINERENV_DPU_MONGODB_CONNECTION_STRING="$DPU_MONGODB_CONNECTION_STRING"
    export APPTAINERENV_DPU_MONGODB_DATABASE=drone-pilot-atlas-sandbox
    export APPTAINERENV_DPU_MONGODB_COLLECTION=flight-information
    unset DPU_MONGODB_CONNECTION_STRING

    apptainer exec "$sif" /opt/venv/bin/python \
        "$dpu/scripts/register-pending-flights.py" \
        --data-root "$data_root" --queue-odm

    unset APPTAINERENV_DPU_MONGODB_CONNECTION_STRING
    unset APPTAINERENV_DPU_MONGODB_DATABASE
    unset APPTAINERENV_DPU_MONGODB_COLLECTION

    python3 "$dpu/scripts/submit-pending-odm.py" \
        --data-root "$data_root" --repo "$dpu" \
        --partition=gpu-a100 --gres=gpu:a100:1
)
