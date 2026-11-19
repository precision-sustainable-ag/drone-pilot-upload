#!/usr/bin/env bash
# Scheduled one-shot Ceres coordinator wrapper. Install scrontab separately,
# only after SCINet permits recurring jobs on the Ceres compute partition.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"
data_root="${DPU_DATA_ROOT:-/project/dash_drone/user/stephen.amerige/dpu-data}"
settings="${DPU_CERES_SCHEDULE_ENV:-$HOME/.config/drone-pilot-upload/ceres-sandbox/coordinator.env}"
log_dir="$data_root/logs/ceres-sandbox/coordinator"
log_file="$log_dir/coordinator.log"
max_log_bytes=$((10 * 1024 * 1024))
max_archives=5

[[ -d "$data_root/site-id" ]] || { echo "Missing Ceres flight storage" >&2; exit 1; }
[[ -r "$settings" ]] || { echo "Missing Ceres schedule settings: $settings" >&2; exit 1; }
# Configuration contains a path to the persistent Python environment, not credentials.
# shellcheck disable=SC1090
source "$settings"
: "${DPU_VEG_PYTHON:?Set DPU_VEG_PYTHON to the absolute Python executable path}"
[[ "$DPU_VEG_PYTHON" = /* && -x "$DPU_VEG_PYTHON" ]] || {
    echo "DPU_VEG_PYTHON must point to an executable absolute path" >&2
    exit 1
}
export DPU_VEG_PYTHON
export DPU_REPO="$repo_root"

umask 027
mkdir -p -- "$log_dir"
exec 8>"$log_dir/.coordinator-log.lock"
if ! flock -n 8; then
    echo "Another coordinator wrapper is active; skipping"
    exit 0
fi
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

{
    printf '\n### %s\n' "$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'UTC: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'Host: %s | Slurm job: %s\n' "$(hostname -s)" "${SLURM_JOB_ID:-manual}"
    status=0
    bash "$script_dir/coordinate-ceres.sh" || status=$?
    printf 'Coordinator exit status: %s\n' "$status"
    exit "$status"
} >> "$log_file" 2>&1
