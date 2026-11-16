# Drone Pilot Upload — Atlas Sandbox Operations and Architecture

**Status:** Unattended Atlas sandbox upload-to-results workflow validated November 16, 2026.
**Scope:** Atlas sandbox only; Ceres validation is tracked by [#24](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/24), and processing existing or transferred flights by [#23](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/23).
**Audience:** Developers, operators, reviewers, and SCINet support staff.
**Tracking issue:** [#22](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/22).

The Atlas browser application accepts imagery into durable project storage. An independent Slurm `scrontab` job registers the flight in MongoDB, submits ODM to the A100 GPU partition, reconciles Slurm results, and creates previews. **No login-node cron process is used.** The Open OnDemand (OOD) browser session is not required after the upload finishes.

## 1. Validated outcome

On November 16, 2026, a new 48-image flight (`248166a7-8eab-4437-97a5-513a6749f8f3`) was uploaded through OOD. Without manual coordinator commands:

- The scheduled coordinator registered the flight and submitted GPU job `21223609` at approximately 9:30 AM Eastern.
- Subsequent coordinator passes observed the job in `RUNNING` and then `COMPLETED` states and reconciled those states to MongoDB.
- At approximately 10:00–10:02 AM Eastern, the coordinator generated orthophoto, VARI, and GLI PNG previews.
- At 10:55 AM, a later pass reported four flights `CURRENT`, four completed preview sets, and zero errors.
- Scheduled coordination continued after the OOD session ended.

Earlier Atlas validations included completed 48-image A100 jobs `21205406`, `21206182`, and `21223442`. Tests also confirmed that repeated coordinator passes are idempotent, existing previews are skipped, a missing preview can be regenerated, overlapping invocations honor their locks, and ambiguous submissions are **not** automatically retried.

This establishes functional *sandbox* automation, not production readiness, verified scientific validity of every raster, or Ceres compatibility.

## 2. Execution architecture

```text
Browser -> Atlas Open OnDemand (development partition)
             | Flask/Vite app in Apptainer, queue mode
             v
          Atlas shared project storage (images + durable records)
             |
             v
Slurm scrontab (recurs every five minutes)
  -> allocated Atlas development node (for example atlas-devel-1)
       | register pending flights in MongoDB Atlas
       | submit ODM via sbatch
       |                  |
       |                  v
       |             gpu-a100 compute node
       |             ODM orthophoto + VARI/GLI GeoTIFFs
       |                  |
       |                  v
       |             shared project storage
       | collect Slurm accounting (sacct)
       | reconcile MongoDB status and artifact metadata
       | create missing PNG previews
       v
    rotating coordinator log
```

**Resource boundaries:** The Slurm controller schedules recurring jobs; the coordinator actually runs on a node allocated from `development`. GPU ODM runs in its own `gpu-a100` Slurm job (one NVIDIA A100). No recurring coordinator command or image-processing workload runs on the Atlas login node. The GPU job does not need direct MongoDB connectivity.

The `development` node's successful MongoDB access on TCP 27017 was validated independently. Do not assume standard compute/GPU nodes have that connectivity or assume the same arrangement works on Ceres.

## 3. Atlas configuration and paths

| Resource | Validated sandbox value |
| --- | --- |
| Repository | `/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload` |
| Data root | `/project/dash_drone/user/stephen.amerige/dpu-data` |
| OOD source | `deploy/atlas-sandbox/ondemand/drone-pilot-upload/` |
| Active OOD development copy | `~/ondemand/dev/drone-pilot-upload/` |
| Application SIF | `sif_files/drone-pilot-upload-current.sif` |
| ODM SIF | `sif_files/odm-3.6.2-gpu.sif` |
| Apptainer module | `apptainer/1.4.3` |
| MongoDB database/collection | `drone-pilot-atlas-sandbox.flight-information` |
| Secret file | `~/.config/drone-pilot-upload/atlas-sandbox/secrets.env` |
| Slurm account | `dash_drone` |
| OOD/coordinator partition | `development` |
| ODM partition / GPU | `gpu-a100` / `gpu:a100:1` |
| Coordinator schedule source | `deploy/atlas-sandbox/dpu-coordinator.scrontab` |
| Coordinator executable | `scripts/run-atlas-scheduled-coordinator.sh` |
| Operational log | `<data-root>/logs/atlas-sandbox/coordinator/coordinator.log` |
| Slurm scheduler stdout | `<data-root>/logs/atlas-sandbox/coordinator-scron.log` |

Never commit or print MongoDB credentials, flight imagery, processing artifacts, or local SIF binaries without an explicit policy.

### Open OnDemand application

The authoritative launcher lives under `deploy/atlas-sandbox/ondemand/drone-pilot-upload/`; do not use the older top-level `ondemand/` demo as the current deployment source. To update the active development copy, from the repository root:

```bash
rsync -av --delete \
  deploy/atlas-sandbox/ondemand/drone-pilot-upload/ \
  ~/ondemand/dev/drone-pilot-upload/
```

This command replaces the active development app definition; review the source and ensure the target is correct before running it. Start a new OOD `basic` session with account `dash_drone`, partition **`development`**, and an appropriate duration. The application runs Flask/Vite inside Apptainer, using `DPU_MONGODB_MODE=queue`; it writes uploads and durable requests to shared storage rather than directly submitting a GPU job.

An OOD session can end without terminating the independent coordinator or its GPU submissions. When changing the launcher itself, refresh the deployed OOD copy and start a new session. Changes to the repo-resident coordinator/registration/reconciliation scripts generally do not require rebuilding the application SIF; backend or container changes may.

## 4. Unattended scheduling and verification

The deployed schedule, accepted on November 16, 2026, is:

```cron
#SCRON --job-name=dpu-atlas-coordinator
#SCRON --account=dash_drone
#SCRON --partition=development
#SCRON --nodes=1
#SCRON --ntasks=1
#SCRON --cpus-per-task=2
#SCRON --mem=16G
#SCRON --time=00:30:00
#SCRON --output=/project/dash_drone/user/stephen.amerige/dpu-data/logs/atlas-sandbox/coordinator-scron.log
*/5 * * * * /bin/bash -l /project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload/scripts/run-atlas-scheduled-coordinator.sh
```

**Do not blindly replace an existing `scrontab`.** From an Atlas login terminal, inspect it with `scrontab -l`, then use `scrontab -e` to merge or edit the entry. Slurm may mark a rejected line `#BAD:`; inspect the error rather than assuming the job is active. The previously attempted combination including `--dependency=singleton` and `--open-mode=append` was rejected on Atlas; the simpler entry above was accepted. The cause of that rejection was not isolated, so do not claim either directive is universally unsupported.

Commands to inspect scheduling and historical executions:

```bash
scrontab -l
squeue -u "$USER"
sacct --duplicates -j <scrontab-job-id> \
  --format=JobID,JobName%28,State,ExitCode,Elapsed,Start,End
```

Recurring `scrontab` executions may reuse one Slurm job ID. The parent job can appear `REQUEUED` or `PENDING` even when earlier batch steps completed with exit code `0:0`. Check `sacct --duplicates`, the individual batch step, and the operational log rather than treating `REQUEUED` itself as a failure. Start times may drift from exact five-minute boundaries as Slurm schedules allocations.

The wrapper sets `DPU_REPO` to the checkout containing the script, enters the coordinator through Bash, and logs each invocation. To run one manual pass, use an **allocated Atlas development node**:

```bash
bash -l scripts/run-atlas-scheduled-coordinator.sh
```

Do not run the coordinator on a login or GPU compute node; it explicitly checks that the host matches `atlas-devel-*`. An ordinary one-off `sbatch` using the same development allocation is also supported and was validated independently of an OOD session.

## 5. Logs and rotation

The coordinator writes **one active append-only log** instead of one file per five-minute invocation:

```bash
log_dir=/project/dash_drone/user/stephen.amerige/dpu-data/logs/atlas-sandbox/coordinator
tail -n 80 "$log_dir/coordinator.log"
tail -f "$log_dir/coordinator.log"
```

Each invocation begins with a blank line and a local Eastern-time heading, followed by UTC timestamps, the host and Slurm job ID, workflow stages, and the final wrapper exit status.

The wrapper rotates `coordinator.log` between invocations when it is at least **10 MiB**, retaining **five gzip archives** (`coordinator.log.1.gz` through `.5.gz`). It uses `.coordinator-log.lock` to prevent concurrent writers and rotation races. The coordinator independently locks `<data-root>/.dpu-atlas-coordinator.lock`; the ODM submitter also uses its own lock.

The fixed Slurm output path `coordinator-scron.log` is separate from the main operational log and contains the wrapper's log-path announcement. It is not included in the coordinator's gzip rotation. Archived logs can be viewed with `zcat` or `zgrep`.

If another wrapper already holds its lock, the second logs an appropriate skip message and exits successfully without entering the coordinator. Normal schedule invocations perform lightweight no-work passes when there is nothing to advance.

## 6. Durable flight records and result artifacts

Canonical flight layout:

```text
<data-root>/site-id/<organization-guid>/flights/<flight-guid>/
  images/                                  Original uploaded imagery
  other_files/                             Other upload files, if present
  mongo-registration.pending.json          Registration awaiting MongoDB
  mongo-registration.done.json             Registration completed
  odm-submission.pending.json              ODM submission requested
  odm-submission.submitting.json           Uncertain/interrupted sbatch; DO NOT retry automatically
  odm-submission.submitted.json            Submission receipt with Slurm job ID
  odm-slurm-<job-id>.out/.err                Flight-local GPU logs
  odm-slurm-accounting.json                Most recent sacct snapshot
  odm/code/odm_orthophoto/odm_orthophoto.tif
  odm/veg_indices/vari_image.tif
  odm/veg_indices/gli_image.tif
  previews/orthophoto.png
  previews/vari.png
  previews/gli.png
```

The site-name paths are convenience aliases; use canonical `site-id` paths for operator inspection and processing. Not every marker is present simultaneously: successful transitions replace earlier pending state. The submitted job's products and logs remain on shared storage after an OOD session closes.

**Safeguards:** A `flight_id` unique index and idempotent MongoDB registration prevent duplicate records. Submission consumes the pending marker before calling `sbatch`; a crash between these steps leaves `.submitting` for explicit review. Existing `odm/` or `odm-tmp/` directories prevent ordinary resubmission. The coordinator's missing-preview helper only visits flights with a completed Slurm snapshot (`COMPLETED` and `0:0`) and generates missing previews. Existing nonempty preview PNGs are skipped. Preview files are written atomically to avoid publishing incomplete PNGs after interruption.

Result readiness checks validate Slurm success and required nonempty products; they are not a full integrity or scientific-quality assessment. Deliberate reprocessing of successful flights is **out of scope for #22** and tracked in #23.

## 7. Monitoring and routine checks

Use the operator-facing scripts from an appropriate Atlas environment:

```bash
bash scripts/atlas.sh pending
bash scripts/atlas.sh status details <gpu-job-id>
bash scripts/atlas.sh reconcile --dry-run  # inspection only
```

Slurm accounting can be inspected without changing flight state:

```bash
sacct -j <gpu-job-id> --format=JobID,JobName,State,ExitCode,Elapsed,NodeList
```

A completed job should report `COMPLETED`, exit `0:0`, and have nonempty orthophoto, VARI, and GLI GeoTIFFs. The next coordinator pass should reconcile MongoDB to `processed` and generate its three PNG previews. The top-level MongoDB `status` vocabulary includes `registered`, `queued`, `processing`, `ortho generated`, `processed`, and `failed`; the `stages`, `processing`, and `artifacts` fields carry detail. Artifact paths stored in MongoDB are relative to the flight directory.

**Routine activity does not require invoking `atlas.sh submit` or `atlas.sh reconcile` manually.** The scheduled coordinator performs both; the operator commands remain useful for diagnostics and controlled remediation. Do not invoke state-changing commands on a login node as a substitute for a failing scheduled development-node job.

## 8. Failure diagnosis and safe recovery

| Symptom | Inspect | Safe interpretation or action |
| --- | --- | --- |
| No new upload registered | OOD success indication; `atlas.sh pending`; `mongo-registration.pending.json`; coordinator log | Confirm full upload and metadata before touching queue state; next pass should register it |
| Recurring jobs missing | `scrontab -l`, `squeue`, `sacct --duplicates`, `coordinator-scron.log` | Check for `#BAD:` rejection, allocation failures, time limits, or scheduling delays |
| Wrapper skips a pass | `Another coordinator wrapper is active` | A concurrent pass already holds the log lock; inspect that run and allow the next scheduled pass |
| Coordinator skips a pass | `Another coordinator is running` | Processing lock was held; retry at the next scheduled occurrence rather than forcing a duplicate |
| Flight stuck in `PENDING` | `squeue`, `sacct`, `scontrol show job <id>` | GPU queue wait may be legitimate; avoid duplicate `sbatch` |
| GPU job ended but MongoDB not yet `processed` | `sacct`, coordinator log, `odm-slurm-accounting.json`, required rasters | Allow next scheduled reconciliation; review reported errors if mismatch persists |
| Missing previews after successful GPU run | Snapshot, required GeoTIFFs, coordinator log | Later passes retry missing previews; do not rerun ODM merely to rebuild PNGs |
| `RECONCILE MANUALLY (no automatic retry)` | `odm-submission.submitting.json`; Slurm records and flight logs | Treat submission outcome as ambiguous until a human proves what `sbatch` did |
| MongoDB connection fails | Coordinator log, network access from development allocation, secrets file permissions | Diagnose authorized execution environment and credentials; never print secret values |
| Coordinator exceeds walltime | `sacct`, coordinator log, previews | Adjust scheduling allocation if justified; check partial outputs and do not erase markers blindly |

### 8.1 Ambiguous / interrupted ODM submission (critical)

The submitter intentionally renames `odm-submission.pending.json` to `odm-submission.submitting.json` **before** it invokes `sbatch`. If interrupted after Slurm accepts the job but before a submission receipt is saved, automatic retry would risk submitting the same flight twice.

1. **Do not** delete or rename `.submitting.json` merely to make the queue retry, and do not run a second manual `sbatch` as a guess.
2. Record the flight GUID, organization GUID, timestamp, and any error output in `coordinator.log` and the flight directory.
3. Examine `squeue` and `sacct` for jobs named `dpu-<flight-guid>`; inspect the job's details and any `odm-slurm-<job-id>.out/.err` files. Check the flight's existing `odm/`, `odm-tmp/`, and submission markers.
4. Determine whether Slurm accepted a job, whether it ran, and whether its artifacts are complete. **Do not infer that no job was submitted simply because `squeue` is empty**; completed jobs disappear from `squeue`.
5. Once the outcome is independently verified, an authorized operator can reconcile the specific submission record and MongoDB state using a reviewed, case-specific recovery procedure. Preserve the original evidence and avoid automatic state resets or overwriting output directories. Escalate uncertain cases rather than forcing a retry.

This was tested on November 16 using an isolated synthetic `.submitting.json` marker. The submitter reported `RECONCILE MANUALLY (no automatic retry)` and returned an error instead of issuing a new GPU job.

### 8.2 Concurrency safeguards

Two independent locks were exercised on an Atlas development node:

- `<data-root>/.dpu-atlas-coordinator.lock`: a second coordinator returned `Another coordinator is running; skipping this invocation`.
- `<data-root>/logs/atlas-sandbox/coordinator/.coordinator-log.lock`: a second wrapper returned `Another coordinator wrapper is active; skipping this invocation`.

These are defensive no-op exits, not errors, and do not submit duplicate jobs. The submitter also prevents simultaneous `sbatch` consumption with `<data-root>/.dpu-odm-submit.lock` and refuses automatic retry of ambiguous `.submitting.json` files.

## 9. Changes, deployment boundaries, and scope

- The repository is the source for the OOD templates and coordinator scripts. Editing a source template does **not** automatically update `~/ondemand/dev/drone-pilot-upload/` or existing OOD sessions.
- The `scrontab` entry is installed through `scrontab -e` and is **not** auto-installed by checking out the repository. If the coordinator wrapper path changes, update the active `scrontab` accordingly.
- Repository-resident coordinator, registration, reconciliation, and preview scripts are executed from shared storage. Updates take effect on subsequent scheduled passes; verify changes before pushing or deploying them.
- Backend application or dependency changes may require rebuilding the application SIF and restarting OOD sessions. ODM container changes require deliberate validation of the GPU job path.
- Do not modify `site-id` flight state, MongoDB records, or existing derived outputs casually; recovery and reprocessing have different safety requirements.

### Reference for Ceres adaptation (#24)

Atlas demonstrates a *shared processing architecture*, not identical cluster behavior. Ceres must separately validate its OOD app, Apptainer image/module, storage layout and permissions, MongoDB access from its intended coordinator environment, Slurm partitions/CPU or GPU allocations, and an approved recurring scheduling arrangement. Keep shared logic common and cluster-specific values in `deploy/`; do not assume Ceres has an Atlas-like `development` host or accessible MongoDB.

Processing flights already stored on either cluster and bidirectional Globus transfers are tracked under #23. GPU/resource optimization and production deployment are separate future work.
