#!/usr/bin/env bash
# Delete exactly one Atlas sandbox flight. Read-only unless --execute.
set -euo pipefail

usage() {
    echo "Usage: scripts/atlas.sh delete FLIGHT_GUID [--execute]" >&2
    exit 2
}

(( $# == 1 || $# == 2 )) || usage
flight_id=$1
mode=${2:---dry-run}
[[ $mode == --dry-run || $mode == --execute ]] || usage
uuid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
[[ $flight_id =~ $uuid_re ]] || { echo "ERROR: Expected canonical flight GUID" >&2; exit 2; }

# Do not change the caller's environment. All persistent changes are explicit.
(
    set -euo pipefail
    dpu=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
    data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
    sif="${DPU_UPLOAD_SIF:-${dpu}/sif_files/drone-pilot-upload-20261026.sif}"
    secrets="${DPU_SECRETS_FILE:-${HOME}/.config/drone-pilot-upload/atlas-sandbox/secrets.env}"

    [[ -d "$data_root/site-id" ]] || { echo "ERROR: Missing Atlas flight storage" >&2; exit 1; }
    [[ -r "$sif" ]] || { echo "ERROR: Missing application SIF: $sif" >&2; exit 1; }

    # Block concurrent ODM submission. submit-pending-odm.py uses this lock.
    if [[ $mode == --execute ]]; then
        command -v flock >/dev/null || { echo "ERROR: flock unavailable" >&2; exit 1; }
        exec 9>"$data_root/.dpu-odm-submit.lock"
        flock -n 9 || { echo "ERROR: ODM submission is in progress" >&2; exit 1; }
    fi

    # Check Slurm before any deletion. The job name is deliberately a full GUID.
    check_jobs() {
        local lines
        lines=$(squeue -u "$USER" -h -o '%.200j|%.20i') || {
            echo "ERROR: Cannot query active Slurm jobs; refusing deletion" >&2
            return 1
        }
        if printf '%s\n' "$lines" | awk -F'|' -v target="dpu-${flight_id}" '
            { name=$1; gsub(/^[[:space:]]+|[[:space:]]+$/, "", name); if (name == target) found=1 }
            END { exit !found }
        '; then
            echo "ERROR: A Slurm job is still active for flight $flight_id" >&2
            return 1
        fi
    }
    command -v squeue >/dev/null || { echo "ERROR: squeue unavailable" >&2; exit 1; }
    check_jobs

    module load apptainer/1.4.3
    unset APPTAINER_NO_MOUNT
    [[ -r "$secrets" ]] || { echo "ERROR: MongoDB secrets file is not readable" >&2; exit 1; }
    source "$secrets"
    : "${DPU_MONGODB_CONNECTION_STRING:?MongoDB connection string missing}"
    export APPTAINERENV_DPU_MONGODB_CONNECTION_STRING="$DPU_MONGODB_CONNECTION_STRING"
    export APPTAINERENV_DPU_MONGODB_DATABASE=drone-pilot-atlas-sandbox
    export APPTAINERENV_DPU_MONGODB_COLLECTION=flight-information
    unset DPU_MONGODB_CONNECTION_STRING

    run_delete() {
        apptainer exec "$sif" /opt/venv/bin/python "$dpu/scripts/delete-atlas-flight.py" \
            --data-root "$data_root" --flight-id "$flight_id" "$@"
    }

    # A normal invocation is read-only.
    if [[ $mode != --execute ]]; then
        run_delete
        exit 0
    fi

    # Execution requested: preview first.
    run_delete --preview

    # Require interactive confirmation before deleting anything.
    [[ -t 0 ]] || {
        echo "ERROR: Interactive confirmation required" >&2
        exit 1
    }

    printf '\nTo delete both MongoDB and project files, type the full flight GUID: '
    IFS= read -r confirmation

    [[ $confirmation == "$flight_id" ]] || {
        echo "Cancelled: confirmation did not match." >&2
        exit 1
    }

    # Recheck for active jobs immediately before deletion.
    check_jobs

    # Perform the actual deletion.
    run_delete --execute
)
