#!/usr/bin/env bash
# Execute one Atlas coordinator pass and append to a rotating shared log.
# Rotation is managed here because user-level scrontab jobs cannot depend on
# a system logrotate configuration. One writer holds the lock at a time.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"
data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
log_dir="$data_root/logs/atlas-sandbox/coordinator"
log_file="$log_dir/coordinator.log"
max_log_bytes=$((10 * 1024 * 1024))
max_archives=5

if [[ ! -d "$data_root/site-id" ]]; then
    echo "Flight storage is unavailable: $data_root/site-id" >&2
    exit 1
fi

umask 027
mkdir -p -- "$log_dir"

# Serialize both rotation and append, including manually triggered invocations.
# The coordinator also has its own separate processing lock.
exec 8>"$log_dir/.coordinator-log.lock"
if ! flock -n 8; then
    echo "Another coordinator wrapper is active; skipping this invocation"
    exit 0
fi

# Rotate only between invocations; no live log can be renamed or truncated.
if [[ -f "$log_file" ]] && (( $(stat -c '%s' -- "$log_file") >= max_log_bytes )); then
    rm -f -- "$log_file.$max_archives.gz"
    for ((i=max_archives-1; i>=1; i--)); do
        if [[ -f "$log_file.$i.gz" ]]; then
            mv -f -- "$log_file.$i.gz" "$log_file.$((i+1)).gz"
        fi
    done
    gzip -c -- "$log_file" > "$log_file.1.gz"
    : > "$log_file"
fi

export DPU_REPO="$repo_root"
echo "Coordinator log: $log_file"

{
    printf '\n### %s\n' "$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'Coordinator started (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'Host: %s\n' "$(hostname -s)"
    printf 'Slurm job: %s\n' "${SLURM_JOB_ID:-manual}"
    printf 'Repository: %s\n' "$DPU_REPO"
    printf 'Data root: %s\n' "$data_root"

    status=0
    bash "$script_dir/coordinate-atlas.sh" || status=$?

    printf 'Coordinator finished (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'Wrapper exit status: %s\n' "$status"
    exit "$status"
} >> "$log_file" 2>&1
