# Ceres sandbox — one-shot coordination (Issue 24)

This workflow operates on Ceres storage and `drone-pilot-ceres-sandbox.flight-information`. It does not alter Atlas automation. The Ceres coordinator is **not scheduled** by this PR; SCINet approval and a suitable long-lived allocation are prerequisites for unattended operation.

## Verified reference flight

- Organization: `b31408b9-b0d9-4437-962e-10a1bdd30688`
- Flight: `a9c8bd9e-e977-4cfd-9431-05637388f43f`
- 48 JPEG images; manual CPU ODM job `22864996` completed in 52m 19s.
- MongoDB state reconciled to `processed` with both processing stages `succeeded`.
- Orthophoto, VARI, GLI, and three previews verified.

## Execution prerequisites

Run the coordinator in an approved **Ceres compute allocation**, never on a login node. The allocation must have MongoDB connectivity, access to the `dash_drone` Slurm account, and enough CPU/memory/time for postprocessing. Submission via `sbatch` from that allocation must be permitted by local policy. Do not enable any recurring schedule until permission has been confirmed.

On the compute node, a Python environment containing `numpy` and `rasterio` must be available for postprocessing. Use `DPU_VEG_PYTHON` to select that environment; do not assume system Python has those packages. The application SIF provides PyMongo for registration/reconciliation, not NumPy/Rasterio. Credentials remain in `~/.config/drone-pilot-upload/secrets.env`; do not print or commit them.

## Read-only checks on an allocated compute node

```bash
cd /project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload
git pull --ff-only

bash -n scripts/coordinate-ceres.sh
bash -n scripts/odm-ceres-flight.sh

python3 scripts/submit-pending-odm.py \
  --sandbox ceres --data-root /project/dash_drone/user/stephen.amerige/dpu-data \
  --repo "$PWD" --dry-run

DPU_VEG_PYTHON="$(command -v python)"
"$DPU_VEG_PYTHON" -c 'import numpy, rasterio; print("Ceres postprocessing dependencies: OK")'
```

The successful historical flight is already registered, processed, and reconciled. The submission dry run should find no new pending work unless another flight has been uploaded.

## Manual one-shot coordinator invocation

After confirming its permitted execution context and inspecting the pending queue:

```bash
cd /project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload
export DPU_VEG_PYTHON="$(command -v python)"
bash scripts/coordinate-ceres.sh
```

The coordinator uses a nonblocking `$DPU_DATA_ROOT/.dpu-ceres-coordinator.lock` to prevent concurrent runs. It registers pending uploads with `--sandbox ceres --queue-odm`, submits CPU-only ODM jobs with durable `.pending` / `.submitting` / `.submitted` states, collects `sacct` snapshots, generates missing indices/previews for successful ODM jobs, and reconciles verified artifacts into the Ceres sandbox MongoDB collection.

**Slurm jobs are asynchronous.** A newly submitted ODM job will normally still be running when the coordinator reaches collection. Invoke the one-shot coordinator again after the job completes to finish postprocessing and reconciliation. A scheduler is not included in this PR.

## Important safeguards and recovery

- Slurm submission uses `scripts/odm-ceres-flight.sh` (4 CPUs, 64 GB, 8-hour limit, `ceres` partition, no GPU). The submitter passes absolute `--output` / `--error` paths inside each flight directory, correcting the manual first run's log placement.
- Submission transitions to `.submitting.json` **before** `sbatch`. If interrupted, do not blindly resubmit; reconcile the ambiguous state manually to avoid duplicate jobs.
- The ODM job refuses existing `odm` or `odm-tmp` directories, even after a failure. Never delete them automatically.
- Postprocessing does not overwrite nonempty VARI/GLI outputs. A missing or partial index artifact requires inspection instead of an automatic retry.
- Database operations require an explicitly matched Ceres sandbox/database selection and cannot target Atlas by accident.
- Before automation, avoid manually launching a second ODM job against a flight already present in the queue.

## Deferred work

1. Validate one fresh upload through the queued submission and postprocessing path.
2. Verify the resulting MongoDB state and logs under the flight directory.
3. Confirm with SCINet administrators which long-lived Ceres compute allocation and scheduling mechanism are approved.
4. Only then enable recurrent one-shot coordinator execution.
5. Resolve the independent frontend development-dependency audit before merging the PR.
