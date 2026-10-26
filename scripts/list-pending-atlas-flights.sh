#!/usr/bin/env bash
set -euo pipefail

root="${DPU_DATA_ROOT:-/project/dash_drone/user/${USER}/dpu-data}/site-id"

if [[ ! -d "$root" ]]; then
    printf 'Data directory not found: %s\n' "$root" >&2
    exit 1
fi

mapfile -t flights < <(
    find "$root" -type f \
        -name 'mongo-registration.pending.json' \
        -printf '%h\n' | sort
)

if (( ${#flights[@]} == 0 )); then
    echo "No pending flight registrations."
else
    for flight in "${flights[@]}"; do
        printf '%s  %s\n' "${flight##*/}" "$flight"
    done
fi
