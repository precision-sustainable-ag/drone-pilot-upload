# Drone Pilot Upload

Drone Pilot Upload is a browser-based application for uploading drone imagery, attaching flight and camera metadata, and generating orthomosaic products through high-performance computing (HPC). The project supports NC State research-station imagery workflows.

The repository contains both the original stand-alone server deployment and work to support USDA SCINet Open OnDemand (OOD) deployments. **Deployment instructions differ by environment.**

## Current deployment status

| Environment | Status | Documentation |
| --- | --- | --- |
| **Atlas sandbox** | Unattended upload-to-results workflow validated November 16, 2026 | [Atlas sandbox runbook](docs/atlas-sandbox-runbook.md) |
| **Ceres sandbox** | Deployment work beginning November 18, 2026; compatibility and end-to-end validation are next ([#24](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/24)) | Planned |
| **Original stand-alone server** | Legacy configuration; verify before redeployment | [Legacy deployment](#legacy-stand-alone-server-deployment) |

The validated Atlas workflow uses the Flask/Vite application on an Open OnDemand `development` allocation, a five-minute Slurm `scrontab` coordinator running on development nodes, and separate A100 GPU jobs for OpenDroneMap (ODM). The coordinator registers new flights in MongoDB, submits GPU work, reconciles Slurm outcomes, and creates orthophoto/VARI/GLI previews. **No scheduled coordinator workload runs on a login node.** Once an upload finishes, the browser/OOD session need not remain active for processing to continue.

## Atlas sandbox: operator quick start

Launch the Atlas OOD `basic` app on the `development` partition, complete a flight upload, then let the scheduled coordinator advance the durable queue. **Do not manually submit ODM or reconcile MongoDB in the normal upload workflow.**

From the repository, the following commands can be used to inspect or diagnose work:

```bash
bash scripts/atlas.sh pending
bash scripts/atlas.sh status details <gpu-job-id>
sacct -j <gpu-job-id> --format=JobID,JobName,State,ExitCode,Elapsed
```

The coordinator is installed with Slurm `scrontab`; its source template is `deploy/atlas-sandbox/dpu-coordinator.scrontab`. It executes `scripts/run-atlas-scheduled-coordinator.sh` in a Slurm development allocation and writes a single rotating log under `<data-root>/logs/atlas-sandbox/coordinator/coordinator.log`.

Consult [the Atlas sandbox runbook](docs/atlas-sandbox-runbook.md) for the authoritative deployment procedure, schedule, logging, durable markers, safety safeguards, manual diagnostics, and ambiguous GPU-submission recovery. `processed` denotes successful Slurm processing with required nonempty orthophoto/VARI/GLI products; it does not constitute scientific validation of the products.

## Technology stack

- **Frontend:** React.js and Material UI.
- **Backend:** Python and Flask, served using Gunicorn in deployed environments.
- **Metadata database:** MongoDB Atlas.
- **HPC integration:** Open OnDemand, Apptainer, Slurm, and OpenDroneMap (ODM).
- **Data processing:** Flight metadata and EXIF extraction, orthophoto generation, and vegetation-index products.

## Repository organization

```text
backend/                 Flask API, configuration, metadata/storage utilities
frontend/                React upload interface
containers/              Apptainer definitions and demonstrations
deploy/                  Environment-specific deployment templates
  atlas-sandbox/         Validated Atlas OOD launcher
ondemand/                Original OOD app materials
ortho_processing/        Orthomosaic and vegetation-index processing, legacy tools
scripts/                 Atlas coordination, registration, GPU submission, reconciliation, and previews
sif_files/               Locally managed Apptainer images (not source code)
docs/                    Deployment and operations documentation (see below)
```

The authoritative Atlas operational document is [docs/atlas-sandbox-runbook.md](docs/atlas-sandbox-runbook.md). Some files in `ortho_processing/` reflect earlier server or workflow layouts and should not be assumed compatible with the Atlas GUID-based data layout. In particular, the legacy `ortho_processing/update_status.py` is **not** the validated Atlas status synchronizer and should not be run against the Atlas sandbox or production MongoDB collections.

## Legacy stand-alone server deployment

> **Historical instructions from the original README.** These apply to independent Ubuntu 20.04+ research-station servers, not the Atlas sandbox. Validate their applicability and obtain current configuration securely from project maintainers before using them.

1. Use `run.sh` for the stand-alone deployment. The original arrangement uses Gunicorn for the API and Nginx for the frontend.
2. Supply the required frontend `.env` and backend `config.py` using an approved secure channel. Never commit secrets.
3. In that deployment model, reload services as appropriate:

   ```bash
   systemctl reload drone_upload_api
   systemctl reload nginx
   ```

Earlier super-user installation documentation is available in the [project's Atlassian guide](https://precision-sustainable-ag.atlassian.net/wiki/spaces/DDP/pages/569573389/App+1+prod+setup+for+super+users); confirm it is current before following it.

## Legacy local development setup

> The following workflow is preserved from the original README. Versions and dependencies may need updating before use; it is **not** the Atlas OOD deployment procedure.

1. Prerequisites listed in the original project: MongoDB, Git, Nginx, ExifTool, Node.js, and npm.
2. Clone the repository:

   ```bash
   git clone https://github.com/precision-sustainable-ag/drone-pilot-upload.git
   ```

3. Frontend:

   ```bash
   cd frontend
   npm install
   # Configure frontend/.env with REACT_APP_API_URL=http://localhost:5000/imgproc
   npm run start
   ```

4. Backend (the original setup specified Python 3.9):

   ```bash
   python3.9 -m venv ./backend/venv
   ./backend/venv/bin/python3 -m pip install -r ./backend/requirements.txt
   ./backend/venv/bin/python3 ./backend/app.py
   ```

## Outstanding work

Atlas unattended operation has been validated in the sandbox. Follow-on work includes completing the operational review under [#22](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/22), validating equivalent functionality on Ceres under [#24](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/24), and adding existing-flight reprocessing and bidirectional Globus transfers under [#23](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/23). Performance optimization and production deployment are separate future efforts.
