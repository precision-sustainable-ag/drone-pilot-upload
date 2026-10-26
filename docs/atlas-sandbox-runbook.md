# Drone Pilot Upload — Atlas Sandbox Operations and Architecture

**Status:** Functional Atlas proof of concept validated October 26, 2026.  
**Scope:** USDA SCINet Atlas sandbox only. Ceres and production deployment are out of scope.  
**Audience:** Developers, operators, reviewers, and SCINet support staff.

> This runbook documents the *currently demonstrated* deployment. Flight registration/Slurm submission and MongoDB status reconciliation are **manual, independent operator actions**. Do not describe them as an unattended service. No login-node cron service, privileged firewall change, or network tunnel is assumed or authorized by this document.

## 1. Purpose and demonstrated result

Drone Pilot Upload accepts aerial imagery through a browser-based Open OnDemand (OOD) application, extracts camera and flight metadata, stores images under stable organization/flight GUIDs, registers flight metadata in a sandbox MongoDB Atlas collection, submits GPU processing to Slurm, and generates an ODM orthophoto plus vegetation indices. A separate reconciliation operation records execution outcomes and product readiness in MongoDB.

The October 26, 2026 integration test used **24 JPEG images**, with flight GUID `b01f52c5-e985-4bd1-b121-75505e7dabec`. It automatically submitted Slurm job **21019534**, which completed on Atlas A100 hardware in **5 minutes 50 seconds** with exit code **0:0**. ODM generated an orthophoto and VARI/GLI raster products. Manual reconciliation subsequently wrote `status: "processed"` and the execution/artifact metadata into MongoDB.

This demonstrates the functional *Atlas* pipeline. It does **not** establish unattended orchestration, production security approval, Ceres compatibility, or GPU/CPU parity.

## 2. Architecture and network constraint

```text
User browser
   | upload
   v
Atlas OOD session on compute node
   | Flask/React application in Apptainer
   | writes images + BSON Extended JSON queue record
   v
Atlas shared project storage (durable GUID-based flight directory)
   |                                 ^
   | host-side registration           | host-side reconciliation
   v                                 |
Atlas login-host one-shot scripts  <--- Slurm accounting (sacct)
   |                                ^
   | MongoDB Atlas TCP 27017         | GPU batch job outcome
   | sbatch                          |
   v                                |
MongoDB Atlas (sandbox database)     Slurm A100 GPU job
                                     | ODM + VARI + GLI
                                     v
                              Flight artifact files
```

Atlas **compute nodes** have not been able to connect directly to the MongoDB Atlas service on TCP 27017. Diagnostics found proxy CONNECT requests to that destination rejected with HTTP 403. Short, one-shot MongoDB operations from an Atlas **login host** succeeded, as did Slurm submission. The workaround is a durable shared-filesystem handoff, not a tunnel or a change to the cluster network policy.

The login-node workflow is currently performed manually. **SCINet/Atlas support approval is required before setting up any unattended user service or scheduler on a login node.** SCINet's documented `scrontab` facility submits recurring Slurm batch jobs, but those run on compute nodes and therefore do not, by themselves, solve the current database connectivity restriction.

## 3. Repository layout

```text
backend/                       Flask backend; queue-mode metadata registration
frontend/                      React upload interface
containers/drone-pilot-upload/  Application Apptainer definition
sif_files/                     Local SIF images (managed separately from Git)
deploy/atlas-sandbox/ondemand/drone-pilot-upload/template/
  script.sh.erb                 Atlas OOD session launcher
scripts/
  register-pending-flights.py   Validate and register queued metadata; request ODM
  submit-pending-odm.py         Atomically/defensively submit pending Slurm jobs
  register-and-submit-atlas.sh  Run registration then submission on login host
  odm-atlas-flight.sh           GUID-based Slurm GPU ODM and vegetation pipeline
  collect-atlas-status.py      Read Slurm accounting into per-flight snapshot
  sync-atlas-mongodb.py        Reconcile status, stages, and artifacts into MongoDB
  reconcile-atlas-flights.sh   Run accounting collection then DB reconciliation
ortho_processing/              Vegetation-index processing and legacy utilities
docs/atlas-sandbox-runbook.md   This operational runbook
```

**Legacy caution:** `ortho_processing/update_status.py` is not the validated Atlas reconciler. The supplied legacy version contains an unconditional bulk update marking matching Sandhills `processing` flights as `failed`. Do not run it against either production or the Atlas sandbox database. Current reconciliation uses `scripts/reconcile-atlas-flights.sh` instead.

## 4. Environment and boundaries

The commands in this document are run on **Atlas**, from the Git repository on shared project storage. Examples use the existing shell shortcut `~dpu`; if that shortcut is unavailable, change to the repository's full project path instead.

| Resource | Current Atlas sandbox value |
|---|---|
| Repository | `/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload` |
| Data root | `/project/dash_drone/user/stephen.amerige/dpu-data` |
| Application SIF | `sif_files/drone-pilot-upload-20261026.sif` |
| GPU ODM SIF | `sif_files/odm-3.6.2-gpu.sif` |
| MongoDB database | `drone-pilot-atlas-sandbox` |
| MongoDB collection | `flight-information` |
| Slurm account | `dash_drone` |
| Validated GPU partition | `gpu-a100` (one A100 GPU) |
| Secret env file | `~/.config/drone-pilot-upload/atlas-sandbox/secrets.env` — **never commit or print its contents** |

The Atlas OOD launcher specifies `DPU_MONGODB_MODE=queue` and uses the application SIF. The login-host scripts load `apptainer/1.4.3` and run the **current repository Python files through Apptainer** for their required Python dependencies. This means edits restricted to these repository-side scripts require **no SIF rebuild or OOD session restart**, so long as the wrapper continues to reference the shared-storage copies.

If `backend/` or container dependencies change, reassess whether the SIF must be rebuilt and the OOD session restarted; the above no-rebuild rule does not apply universally.

## 5. Data layout and durable workflow markers

Example flight path:

```text
<data-root>/site-id/<organization-guid>/flights/<flight-guid>/
  images/                                  Uploaded images
  other_files/                             Miscellaneous uploaded files (if any)
  mongo-registration.pending.json          Waiting for login-host registration
  mongo-registration.done.json             Registration recorded successfully
  odm-submission.pending.json              Waiting for Slurm submission
  odm-submission.submitting.json           Ambiguous/interrupted submission; inspect manually
  odm-submission.submitted.json            Slurm receipt; includes job ID
  odm-slurm-<job-id>.out                    Slurm stdout
  odm-slurm-<job-id>.err                    Slurm stderr
  odm-slurm-accounting.json                Collected `sacct` snapshot
  odm/code/odm_orthophoto/odm_orthophoto.tif
  odm/veg_indices/vari_image.tif
  odm/veg_indices/gli_image.tif
```

`mongo-registration.pending.json` becomes `mongo-registration.done.json` after a successful registration (and, when enabled, durable ODM request generation). The submission script consumes its `pending` state **before** calling `sbatch`; ambiguous interruptions intentionally leave `submitting` in place and block automatic resubmission. Do **not** rename or remove this file merely to force a retry; investigate Slurm/accounting first to avoid duplicate GPU jobs writing to the same flight directory.

Output paths used in MongoDB's `artifacts` object are **relative to the flight directory**, not hardcoded absolute filesystem paths.

## 6. Manual operating procedure (current state)

### 6.1 Start and use the Atlas OOD upload app

1. Launch a fresh OOD Drone Pilot Upload session through the Atlas portal. Allocate sufficient session time for interactive upload and testing; session lifetime is independent of GPU job lifetime.
2. Connect through the active session's **Connect** control, rather than an expired browser tab.
3. Upload the imagery and confirm the application's success dialog.
4. Confirm the metadata queue file exists on shared storage:

   ```bash
   find /project/dash_drone/user/stephen.amerige/dpu-data/site-id \
     -name 'mongo-registration.pending.json' -print
   ```

**The upload success dialog indicates data reached the application and its queue; it does not mean MongoDB registration or ODM processing is complete.**

### 6.2 Operator action A: register flight and submit GPU job

On the **Atlas login host**:

```bash
cd ~dpu
bash scripts/register-and-submit-atlas.sh
```

A successful new flight generally reports:

```text
Pending registrations: 1
READY: <flight-guid> (24 images)
ODM QUEUED: <flight-guid>
REGISTERED: <flight-guid>
Completed: 1; failed: 0
Pending ODM submissions: 1
SUBMITTED: <flight-guid> Slurm job <job-id>
ODM submission errors: 0
```

The MongoDB registrar uses a unique `flight_id` index and an insert-only initialization of new status fields (`$setOnInsert`):

```json
{
  "status": "registered",
  "stages": {
    "odm": { "state": "pending" },
    "ortho_intel": { "state": "pending" }
  }
}
```

A retry must not reset an existing flight's status or trigger a duplicate GPU submission. New initial-status behavior applies to **newly inserted** MongoDB records, not records already present before that code change.

### 6.3 Monitor the submitted Slurm job

```bash
squeue -u "$USER"
sacct -j <job-id> --format=JobID,JobName,State,ExitCode,Elapsed
```

When the job is running, find the log **inside the flight directory**, not at the repository root:

```bash
FLIGHT_ROOT=/project/dash_drone/user/stephen.amerige/dpu-data/site-id/<organization-guid>/flights/<flight-guid>
tail -n 40 "$FLIGHT_ROOT/odm-slurm-<job-id>.out"
```

A proven successful job reports `COMPLETED`, exit code `0:0`, and the message `ODM and vegetation-index processing completed successfully`. The script additionally checks that orthophoto, VARI, and GLI files exist and are nonempty. Artifact existence/nonzero size is a **basic readiness test**, not a comprehensive GeoTIFF integrity or scientific-validity audit.

### 6.4 Operator action B: reconcile status and outputs into MongoDB

**This is a separate manual step, after submission and later as the job advances or completes.** The reconciler first gathers Slurm accounting on the login host, then runs database synchronization through Apptainer.

Preview proposed changes without modifying MongoDB:

```bash
cd ~dpu
bash scripts/reconcile-atlas-flights.sh --dry-run
```

Apply the update:

```bash
bash scripts/reconcile-atlas-flights.sh
```

For successful output, expect messages resembling:

```text
RECORDED: <flight-guid> job=<job-id> state=COMPLETED
Slurm collection errors: 0
READY: <flight-guid>: processed
SYNCED: <flight-guid>: processed
MongoDB reconciliation errors: 0
```

Finally, verify the document in MongoDB Atlas, database `drone-pilot-atlas-sandbox`, collection `flight-information`, filtering by `flight_id`.

**Important:** A flight can remain `registered` in MongoDB despite a submitted/running/completed Slurm job **until reconciliation runs**. This is a known operational limitation, not an indication that the processing pipeline failed.

## 7. MongoDB schema and status semantics

The existing camera, EXIF, flight geometry, and organization metadata remain intact. The Atlas status integration adds:

```json
{
  "status": "processed",
  "stages": {
    "odm": { "state": "succeeded" },
    "ortho_intel": { "state": "succeeded" }
  },
  "processing": {
    "engine": "odm",
    "slurm_job_id": "21019534",
    "partition": "gpu-a100",
    "slurm_state": "COMPLETED",
    "exit_code": "0:0",
    "submitted_at": "<BSON UTC Date>",
    "started_at": "<BSON UTC Date>",
    "completed_at": "<BSON UTC Date>",
    "observed_at": "<BSON UTC Date>",
    "error": null
  },
  "artifacts": {
    "orthophoto": "odm/code/odm_orthophoto/odm_orthophoto.tif",
    "vegetation_indices": {
      "vari": "odm/veg_indices/vari_image.tif",
      "gli": "odm/veg_indices/gli_image.tif"
    }
  }
}
```

The literal `<BSON UTC Date>` values above are explanatory placeholders, **not** strings to write to MongoDB. In the implementation, date fields are timezone-aware Python datetimes serialized by PyMongo into BSON Date values.

| Top-level status | Meaning |
|---|---|
| `registered` | New flight record created in MongoDB; images stored, processing not yet confirmed |
| `queued` | Slurm accounting reports a waiting state, after reconciliation |
| `processing` | Slurm accounting reports an active GPU job, after reconciliation |
| `ortho generated` | Orthophoto exists while downstream work is not yet complete |
| `processed` | Slurm reports successful completion and orthophoto, VARI, GLI files are present/nonempty |
| `failed` | Slurm reported failure or completion lacked required outputs; see `processing.error` |

Top-level `status` retains the established `processed` vocabulary rather than introducing a competing `ready` status. Stage-level `state` fields provide separate ODM and orthophoto-intelligence outcomes.

**State limitations:** The synchronizer currently preserves an already-`processed` flight against subsequent demotion and refuses to silently change Slurm job identity. Reprocessing and detecting the later disappearance of previously successful artifacts require explicitly designed handling. The legacy code's broader status heuristic is not automatically authoritative for Atlas.

## 8. Useful validation and troubleshooting

| Symptom | Check | Interpretation / safe action |
|---|---|---|
| New upload not visible | `squeue -u "$USER"`, OOD session, app log | OOD session may have expired; reconnect to a new active session before retrying |
| No pending registration | `find <data-root>/site-id -name 'mongo-registration.pending.json'` | Check whether the upload reached shared storage; do not assume MongoDB failure |
| Registration command reports 0 | Check queue files and whether registration was previously completed | A zero count is normal when no work remains |
| Slurm job is `PENDING (Resources)` | `squeue`, `sinfo`, `scontrol show job` | GPU availability may be exhausted; CPU/memory availability alone does not imply GPUs are free |
| No ODM log in repository root | Check `<flight-dir>/odm-slurm-<job-id>.out` | Automated submission intentionally uses flight-local logs |
| `.submitting.json` left behind | Inspect `sacct`, `squeue`, Slurm job name and flight logs | **Do not blindly resubmit**; ambiguous result may already have started a job |
| Slurm `COMPLETED` but MongoDB still `registered` | Run the separate reconciliation command | Status is only advanced when reconciliation runs |
| MongoDB `processed` without fully validated GeoTIFFs | Verify actual rasters independently | Current readiness check is based on required nonempty files and Slurm success |
| Outdated timestamp string | Verify UTC timestamp patch and reconcile again | Confirm BSON Date types, not naive timestamp text |

Operational caveat: the console message `NDVI and GLI files written in chunks` in the vegetation processor appears inconsistent with the validated filename `vari_image.tif`. Confirm the actual index calculation before changing labels or promising NDVI output.

## 9. Redeployment, changes, and Git

**No application restart/SIF rebuild is needed** for changes limited to the repository-resident login-host scripts listed in Section 3. Both one-shot wrappers invoke Python scripts by path from the checked-out shared repository, using the already available application SIF's Python environment.

Rebuild/restart decisions differ when changing the application backend, its Python dependencies, the definition file, frontend build, or the OOD launcher. The OOD launch template is deployed separately under `~/ondemand/dev/drone-pilot-upload` and sessions must be restarted to pick up launcher changes.

Before a commit, inspect staged versus unstaged changes. For example, `git status` showing one script both staged and modified means the staged snapshot is not its final contents. Stage the final intended files before invoking the project's standard `Go commit 20` convention.

Do not commit credentials, secrets files, SIF binaries without explicit policy, flight imagery, processing output, or temporary queues.

## 10. Security and operations work still open

The next planned development phase is a targeted security review on Atlas, covering authorization/authentication, upload-type/content and size validation, path traversal and symlink handling, secrets/logging, subprocess invocation, container/runtime isolation, dependency vulnerabilities, filesystem permissions, and data provenance. Address issues on the shared application code before porting to Ceres.

**Unattended coordination is not yet deployed.** Two manual operator actions are currently necessary for a newly uploaded flight: registration/submission and reconciliation after processing. A user-facing design should permit users to close the browser once uploads are received, with independent background processing and accurate MongoDB status. A short, scheduled, idempotent coordinator could invoke the proven one-shot operations, but its host and scheduling mechanism must be approved by SCINet/Atlas operations.

## 11. SCINet / Atlas support question (pending)

Contact the **Atlas-specific helpdesk** at `help-usda@hpc.msstate.edu` for the Atlas networking and scheduled-workflow request. SCINet's Ceres VRSC address is `scinet_vrsc@usda.gov`; the Atlas helpdesk is more directly relevant to this request.

Ask for guidance on:

1. Whether narrowly scoped outbound TLS/TCP connectivity to MongoDB Atlas on port 27017 may be enabled for Atlas compute nodes, or whether this restriction is intentional and should remain.
2. Which approved execution environment can access **MongoDB Atlas**, **the shared Atlas project filesystem**, and **Slurm submission/accounting** for short recurring registration/reconciliation operations without an interactive login session.
3. Whether a supported scheduler/service can execute those operations automatically, with secure credential handling, audit logs, and resource limits.
4. If no host satisfies all three requirements, what supported alternative architecture VRSC recommends.

Do **not** configure a permanent login-node cron task or connection tunnel without administrator authorization. A compute-node `scrontab` job alone does not address the observed TCP 27017 restriction.

Official references: https://scinet.usda.gov/support/contact and https://scinet.usda.gov/guides/use/slurm

## 12. Planned next milestones

1. Confirm that **new** MongoDB inserts initialize `status: registered` and both stages as `pending` (the `$setOnInsert` patch).
2. Complete and commit Atlas status reconciliation and this runbook.
3. Conduct and remediate the focused Atlas security review.
4. Obtain SCINet guidance and implement an approved unattended coordinator; test progress/failure/status handling.
5. Only then create `deploy/ceres-sandbox` and evaluate Ceres's CPU-only ODM deployment and runtime characteristics.
