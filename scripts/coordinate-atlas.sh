#!/usr/bin/env bash
# One-shot Atlas sandbox coordinator.
# Run from an authorized Atlas development-node allocation.

set -uo pipefail

if (( $# != 0 )); then
    echo "Usage: coordinate-atlas.sh" >&2
    exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"

# Do not accidentally run the coordinator on a login or GPU node.
if [[ $(hostname -s) != atlas-devel-* ]]; then
    echo "Coordinator requires an Atlas development node" >&2
    exit 2
fi

if [[ ! -d "$data_root/site-id" ]]; then
    echo "Flight storage directory is unavailable" >&2
    exit 1
fi

# Only one coordinator may run against this data root at a time.
exec 9>"$data_root/.dpu-atlas-coordinator.lock"

if ! flock -n 9; then
    echo "Another coordinator is running; skipping this invocation"
    exit 0
fi

result=0

echo "=== Register pending flights and submit ODM jobs ==="

if ! bash "$script_dir/atlas.sh" submit; then
    echo "Registration or submission encountered errors" >&2
    result=1
fi

echo "=== Reconcile Slurm results with MongoDB ==="

if ! bash "$script_dir/atlas.sh" reconcile; then
    echo "Reconciliation encountered errors" >&2
    result=1
fi

echo "=== Generate missing flight previews ==="

if ! python3 "$script_dir/generate-missing-atlas-previews.py"; then
    echo "Preview generation encountered errors" >&2
    result=1
fi

echo "=== Coordinator finished (exit status: $result) ==="

exit "$result"
