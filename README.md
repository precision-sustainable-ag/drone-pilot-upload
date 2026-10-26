# Drone Pilot Upload

Drone Pilot Upload is a browser-based application for uploading drone imagery, attaching flight and camera metadata, and generating orthomosaic products through high-performance computing (HPC). The project supports NC State research-station imagery workflows.

The repository contains both the original stand-alone server deployment and work to support USDA SCINet Open OnDemand (OOD) deployments. **Deployment instructions differ by environment.**

## Current deployment status

| Environment | Status | Documentation |
| --- | --- | --- |
| **Atlas sandbox** | End-to-end functional workflow validated October 26, 2026; manual operator coordination still required | [Atlas sandbox runbook](docs/atlas-sandbox-runbook.md) |
| **Ceres sandbox** | Planned; not yet validated | To be documented |
| **Original stand-alone server deployment** | Legacy configuration; check with project maintainers before redeploying | [Legacy deployment](#legacy-stand-alone-server-deployment) |

The Atlas sandbox validation covered an upload of 24 JPEG images, EXIF/flight metadata extraction, MongoDB registration, automatic Slurm submission *when the operator invokes the registration command*, processing with OpenDroneMap (ODM) on an A100 GPU, production of an orthophoto and VARI/GLI imagery, and subsequent MongoDB status reconciliation. The validated Slurm job completed successfully, but the workflow is **not yet unattended**.

## Atlas sandbox: operator quick start

The Atlas OOD upload application writes imagery and a registration request to shared project storage. The compute node currently cannot connect directly to MongoDB Atlas on TCP port 27017; a login-host workflow registers the metadata and submits a Slurm job. Once processing completes, a separate reconciliation step updates MongoDB with the job status and artifact paths.

**Run these commands on an authorized Atlas login host, from the repository:**

```bash
# After an upload: register pending flights and submit ODM jobs.
bash scripts/register-and-submit-atlas.sh

# Later, while jobs progress or after they finish: inspect changes, then sync.
bash scripts/reconcile-atlas-flights.sh --dry-run
bash scripts/reconcile-atlas-flights.sh
```

These are **two distinct manual operator actions**; neither is performed automatically by the user's browser session. Do not configure an unattended login-node scheduler or network tunnel without SCINet approval. For prerequisites, environment setup, secrets, Slurm monitoring, duplicate-job safeguards, MongoDB schema, and troubleshooting, read the **[Atlas sandbox operations and architecture runbook](docs/atlas-sandbox-runbook.md)** before operating the system.

MongoDB's top-level `status` describes flight readiness. The current status vocabulary includes `registered`, `queued`, `processing`, `ortho generated`, `processed`, and `failed`. `processed` indicates that Slurm completed successfully and the required orthophoto, VARI, and GLI files passed the current existence/nonempty-file checks. Newly registered flights are intended to initialize at `registered`; that specific insertion change requires confirmation with a fresh flight. Detailed stage and job information is held in the `stages`, `processing`, and `artifacts` fields.

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
scripts/                 Atlas registration, Slurm submission, and reconciliation
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

The next steps are to confirm initial `registered` status on a fresh flight, commit the Atlas status integration, perform a targeted security review, obtain SCINet guidance for an approved unattended coordinator, and only then begin Ceres-specific deployment and CPU-processing validation. See the runbook for the current operational caveats and support questions.
