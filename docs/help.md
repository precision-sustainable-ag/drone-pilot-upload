```text
Drone Pilot Upload - Atlas Operations

Usage:
  atlas.sh <directive> [arguments]

Directives:
  pending                 List uploaded flights awaiting MongoDB registration (read-only)
  submit                  Register pending flights and submit ODM jobs (changes state)
  status [job-id]         Show active Slurm jobs, or accounting for one job (read-only)
  status details [job-id] Show the latest/specified ODM job and its logs (read-only)
  reconcile [--dry-run]   Synchronize Slurm results with MongoDB (changes state)
  help                    Display this help (read-only)

Typical workflow:
  1. Upload images through the Open OnDemand application.
  2. atlas.sh pending
  3. atlas.sh submit
  4. atlas.sh status
  5. atlas.sh status details [job-id]
  6. atlas.sh reconcile --dry-run
  7. atlas.sh reconcile

Examples:
  bash scripts/atlas.sh pending
  bash scripts/atlas.sh submit
  bash scripts/atlas.sh status 21033567
  bash scripts/atlas.sh status details
  bash scripts/atlas.sh status details 21033567
  bash scripts/atlas.sh reconcile --dry-run
  bash scripts/atlas.sh reconcile

Notes:
  - Submit and reconcile require an authorized Atlas login node with
    MongoDB connectivity, access to project storage, and Slurm tools.
  - Uploading images alone does not submit an ODM job.
  - A job that has finished is not shown by squeue; use 'status <job-id>'.
  - 'status details' selects the latest submitted ODM job by receipt timestamp.
  - No directive automatically runs the next workflow step.
```

