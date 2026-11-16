# Drone Pilot Upload — Atlas Open OnDemand Sandbox

This directory contains the **current Open OnDemand (OOD) Batch Connect application** for Drone Pilot Upload on USDA SCINet Atlas. It launches the real Flask/Vite upload interface inside an Apptainer container on a Slurm-allocated **development** node. This is an Atlas **sandbox** deployment, not a production deployment or the earlier demonstration web server.

The application accepts drone imagery and records a durable request for subsequent processing. A separate, scheduled Atlas coordinator registers flights in sandbox MongoDB, submits OpenDroneMap (ODM) work to A100 GPU nodes, reconciles Slurm results, and generates PNG previews. **The OOD session and background processing have independent lifetimes.**

For the complete workflow, operational checks, and recovery procedures, use the [Atlas sandbox operations runbook](../../../../docs/atlas-sandbox-runbook.md). Atlas-specific unattended coordination is tracked in [issue #22](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/22); Ceres validation is separate ([issue #24](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/24)).

## For people uploading imagery

1. Sign in to the **Atlas Open OnDemand** portal and open **Drone Pilot Upload** under the sandbox/development interactive applications.
2. Request an allocation using the `dash_drone` account and **`development` partition**, with a session duration long enough to complete the upload. The current form offers account, partition, hours, and node count.
3. When the session reaches **Running**, choose **Connect to Drone Pilot Upload**. OOD opens the application through its reverse proxy; no direct connection to the internal compute node is needed.
4. Choose **Add or update folder(s)** and select the imagery folder or folders. Supported image filenames use `.jpg`, `.jpeg`, `.tif`, or `.tiff`; hidden files are ignored. Review the selected folder and file counts.
5. Select a **Research Station**, enter **Pilot Name**, select **Cloudiness**, and add **Additional comments** if needed. Research Station, Pilot Name, and Cloudiness are required by the form.
6. Choose **Upload Folder(s)** and keep the session/browser connection open until the success message appears. The upload button is disabled while the transfer is in progress.

**Understand what “uploaded successfully” means:** The backend has accepted the upload and written the flight data and durable registration request to shared storage. It does **not** mean that the Slurm GPU job or downstream previews have finished. Background work proceeds independently after a successful upload, even if the OOD session subsequently ends.

The current browser interface is an **upload interface**, not a flight-processing dashboard or product-download portal. To inspect processing status or locate artifacts, consult the runbook or an Atlas operator. Avoid uploading the same imagery again merely because results are not immediate; a second upload is not the same as safely retrying an existing flight.

## What this deployment runs

```text
Browser
  -> Atlas OOD Batch Connect / reverse proxy
      -> Slurm development-node allocation
          -> Apptainer: Drone Pilot Upload (Flask + built Vite/React frontend)
              -> Shared storage: images + durable registration request

Independent Slurm scrontab job (every 5 minutes)
  -> Atlas development node: one-shot coordinator
      -> MongoDB Atlas sandbox registration
      -> Separate gpu-a100 Slurm ODM job: orthophoto, VARI, GLI
      -> Slurm accounting / MongoDB reconciliation
      -> Missing orthophoto, VARI, GLI PNG previews
```

The OOD launcher sets `DPU_MONGODB_MODE=queue`; it does not need direct MongoDB connectivity to accept uploads. The coordinator runs independently on an authorized development-node allocation, where sandbox MongoDB connectivity has been validated. GPU processing occurs in separate Slurm jobs and does not require a live OOD session.

Successful unattended upload-to-previews processing was demonstrated on Atlas on **November 16, 2026**, using a new 48-image flight. The coordinator also continued operating after the corresponding interactive OOD session had completed.

## Files in this directory

| File | Responsibility |
| --- | --- |
| `manifest.yml` | Publishes **Drone Pilot Upload** as a `batch_connect` interactive app under Servers. |
| `form.yml` | Selects the `atlas` cluster and exposes the account, partition, hours, and node-count controls. |
| `submit.yml.erb` | Submits through the Atlas scheduler using the `basic` Batch Connect template. |
| `template/before.sh.erb` | Selects a free port on the allocated host with `find_port`. |
| `template/script.sh.erb` | Loads Apptainer and launches the application as the session's foreground process. |
| `template/after.sh.erb` | Waits up to 120 seconds for the web port to become available; cleans up an unsuccessful launch. |
| `view.html.erb` | Presents the **Connect** link through OOD's `/rnode/<host>/<port>/` proxy. |

### Validated Atlas sandbox settings

The launcher currently uses these values (defined in `template/script.sh.erb`):

| Setting | Value |
| --- | --- |
| Repository checkout | `/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload` |
| Application image | `sif_files/drone-pilot-upload-current.sif` |
| Apptainer module | `apptainer/1.4.3` |
| Shared data root | `/project/dash_drone/user/stephen.amerige/dpu-data` |
| Flight path organization | `site-id` (stable GUIDs), `site-name` (station aliases) |
| MongoDB mode | `queue` |
| MongoDB target used by the background coordinator | `drone-pilot-atlas-sandbox.flight-information` |
| Application log | `<data-root>/logs/atlas-sandbox/app.log` |
| Background coordinator | Slurm `scrontab`, development partition, every five minutes |
| ODM GPU partition | `gpu-a100` (one A100 GPU per submitted ODM job) |

The launcher provides the application port and data/database configuration through Apptainer environment variables. MongoDB credentials are loaded only by the separate authorized coordination scripts from the operator's protected secrets file; **never add secrets to this README, the OOD templates, or Git**.

These paths and resources describe this **specific Atlas sandbox**. Do not assume they are appropriate for Ceres, production, or another account.

## Install or update the OOD development application

The **Git repository is the source of truth** for this application definition. The active OOD development copy is located at `~/ondemand/dev/drone-pilot-upload/` on Atlas.

From the Atlas checkout, inspect the proposed synchronization first:

```bash
cd /project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload
mkdir -p ~/ondemand/dev/drone-pilot-upload
rsync -av --delete --dry-run \
  deploy/atlas-sandbox/ondemand/drone-pilot-upload/ \
  ~/ondemand/dev/drone-pilot-upload/
```

If the preview is correct, synchronize the app definition:

```bash
rsync -av --delete \
  deploy/atlas-sandbox/ondemand/drone-pilot-upload/ \
  ~/ondemand/dev/drone-pilot-upload/
```

**Caution:** `--delete` removes files in the destination not present in the source. Review the dry run before applying it, particularly if anyone has placed local-only files in the active OOD directory.

For OOD launcher/template changes, start a **new** interactive session to use the updated definition. If OOD continues to show old metadata, refresh the browser or use the OOD development web-server restart option where appropriate. Changes to the built frontend, backend, runtime dependencies, or container image require the corresponding image/build/deployment steps; copying these OOD templates alone does not rebuild the SIF.

Changing this OOD application definition does **not** install or modify the independent coordinator's Slurm schedule. The scheduler's repository reference is [`deploy/atlas-sandbox/dpu-coordinator.scrontab`](../../dpu-coordinator.scrontab); operators should compare it with the **active** `scrontab` before making any scheduler changes. Do not replace other scheduled jobs.

## Session lifecycle and troubleshooting

- **Start:** OOD allocates a development node and runs `template/script.sh.erb`, which executes `apptainer run` as the foreground process. The SIF starts the Gunicorn-served Flask application and built frontend.
- **Connect:** `template/after.sh.erb` confirms the port is listening before OOD presents the Connect link. The `/rnode/` path is the browser connection; do not substitute a compute-node hostname/port URL.
- **Stop:** Cancel the session through **My Interactive Sessions** or allow its Slurm allocation to end. This stops the interactive web application **but not** the coordinator or already-submitted GPU work. Deleting the retained OOD session card is separate from cancelling an active session.

For an OOD session that does not start, inspect its Batch Connect `output.log` under `~/ondemand/data/sys/dashboard/batch_connect/`. For upload/application errors, check `<data-root>/logs/atlas-sandbox/app.log` and confirm that the storage root and current SIF are accessible. An upload that has not reported success should not be assumed complete.

For background-processing issues, check the separate logs and Slurm state:

```bash
# From an Atlas host with project storage and Slurm access:
tail -n 100 /project/dash_drone/user/stephen.amerige/dpu-data/logs/atlas-sandbox/coordinator/coordinator.log
squeue -u "$USER"
```

The coordinator log records each invocation with a local EST/EDT header, UTC timestamps, Slurm job identity, registration/submission counts, reconciliation, preview results, and exit status. Its wrapper rotates the log at approximately 10 MiB, retaining up to five gzip archives. A completed ODM job may no longer appear in `squeue`; use `sacct` with its **ODM job ID** and follow the [runbook](../../../../docs/atlas-sandbox-runbook.md) for status reconciliation, queue markers, failure diagnosis, and recovery.

**Do not delete, rename, or recreate `odm-submission.submitting.json` to force processing.** This state is intentionally ambiguous: an interrupted submission may already have created a GPU job. Automatic resubmission is blocked pending explicit operator reconciliation. Coordinator and wrapper locks also prevent overlapping executions; the November 16 validation exercised both protections.

## Scope and related documentation

This README describes the **current Atlas OOD application and what its users and maintainers need to know**. The [Atlas sandbox operations runbook](../../../../docs/atlas-sandbox-runbook.md) owns full processing operations, MongoDB status semantics, artifacts, and recovery procedures. Processing/reprocessing previously uploaded flights and cross-cluster transfers are tracked separately in [issue #23](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/23); Ceres deployment validation is tracked in [issue #24](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/24).
