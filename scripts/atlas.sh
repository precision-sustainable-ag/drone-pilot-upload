#!/usr/bin/env bash
# Operator-facing interface for Drone Pilot Upload on SCINet Atlas.
# Run MongoDB-related operations only from an authorized Atlas login node.

atlas_help() {
    cat <<'HELP'
Drone Pilot Upload - Atlas Operations

Usage:
  atlas.sh <directive> [arguments]

Directives:
  pending                List uploaded flights awaiting MongoDB registration (read-only)
  submit                 Register pending flights and submit ODM jobs (changes state)
  status [job-id]        Show active Slurm jobs, or accounting for one job (read-only)
  reconcile [--dry-run]  Synchronize Slurm results with MongoDB (changes state)
  help                   Display this help (read-only)

Typical workflow:
  1. Upload images through the Open OnDemand application.
  2. atlas.sh pending
  3. atlas.sh submit
  4. atlas.sh status
  5. atlas.sh status <job-id>
  6. atlas.sh reconcile --dry-run
  7. atlas.sh reconcile

Examples:
  bash scripts/atlas.sh pending
  bash scripts/atlas.sh submit
  bash scripts/atlas.sh status 21033567
  bash scripts/atlas.sh reconcile --dry-run
  bash scripts/atlas.sh reconcile

Notes:
  - Submit and reconcile require an authorized Atlas login node with
    MongoDB connectivity, access to project storage, and Slurm tools.
  - Uploading images alone does not submit an ODM job.
  - A job that has finished is not shown by squeue; use 'status <job-id>'.
  - No directive automatically runs the next workflow step.
HELP
}

atlas_pending() {
    local script_dir=$1
    shift
    if (( $# != 0 )); then
        printf 'Usage: atlas.sh pending\n' >&2
        return 2
    fi
    bash "$script_dir/list-pending-atlas-flights.sh"
}

atlas_submit() {
    local script_dir=$1
    shift
    if (( $# != 0 )); then
        printf 'Usage: atlas.sh submit\n' >&2
        return 2
    fi
    bash "$script_dir/register-and-submit-atlas.sh"
}

atlas_status() {
    local script_dir=$1
    shift
    if (( $# == 0 )); then
        squeue -u "$USER"
    elif (( $# == 1 )) && [[ $1 =~ ^[0-9]+$ ]]; then
        sacct -j "$1" --format=JobID,JobName,State,ExitCode,Elapsed
    else
        printf 'Usage: atlas.sh status [job-id]\n' >&2
        return 2
    fi
}

atlas_reconcile() {
    local script_dir=$1
    shift
    if (( $# > 1 )) || (( $# == 1 )) && [[ $1 != --dry-run ]]; then
        printf 'Usage: atlas.sh reconcile [--dry-run]\n' >&2
        return 2
    fi
    bash "$script_dir/reconcile-atlas-flights.sh" "$@"
}

main() {
    set -euo pipefail
    local script_dir directive handler
    script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    directive=${1:-help}
    if (( $# > 0 )); then
        shift
    fi
    case "$directive" in
        -h|--help) directive=help ;;
    esac
    if [[ ! $directive =~ ^[a-z][a-z0-9_-]*$ ]]; then
        printf 'Unknown directive: %s\n\n' "$directive" >&2
        atlas_help >&2
        return 2
    fi
    handler="atlas_${directive//-/_}"
    if ! declare -F "$handler" >/dev/null; then
        printf 'Unknown directive: %s\n\n' "$directive" >&2
        atlas_help >&2
        return 2
    fi
    # Help receives no script directory; operational directives receive it.
    if [[ $directive == help ]]; then
        atlas_help
    else
        "$handler" "$script_dir" "$@"
    fi
}

main "$@"
