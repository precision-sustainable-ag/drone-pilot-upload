# Drone Pilot Upload — Ceres Open OnDemand Sandbox Demo

This directory contains the Open OnDemand Batch Connect definition used to validate the interactive application runtime planned for the `drone-pilot-upload` Ceres refactor.

The purpose of this demo is intentionally narrow. It proves that Ceres Open OnDemand can:

1. present a launch form to the user;
2. submit a Slurm job;
3. allocate a Ceres compute node;
4. start an Apptainer container inside that allocation;
5. run an interactive web application inside the container;
6. detect when the web application is ready;
7. present a browser-accessible **Connect** action through the Open OnDemand reverse proxy;
8. allow the user to interact with server-side application logic; and
9. terminate the application, container, and compute allocation when the user cancels the interactive session.

This is not the production `drone-pilot-upload` application. It is a deliberately small proof of the runtime and lifecycle that the production application will later use.

## Directory Layout

The Open OnDemand application source is maintained in the Git repository under:

```text
ondemand/drone-pilot-upload/
├── form.yml
├── manifest.yml
├── README.md
├── submit.yml.erb
├── view.html.erb
└── template/
    ├── after.sh.erb
    ├── before.sh.erb
    └── script.sh.erb
```

The interactive demonstration application used by this Batch Connect definition is maintained separately under:

```text
containers/ood-web-demo/
└── app.py
```

The current Ceres development deployment is copied to:

```text
~/ondemand/dev/drone-pilot-upload/
```

The Git repository should be treated as the authoritative source. The copy under `~/ondemand/dev` is the active Open OnDemand sandbox deployment used for development and testing.

## Runtime Flow

The demonstrated runtime path is:

```text
Ceres Open OnDemand
        |
        v
Batch Connect launch form
        |
        v
Slurm job submission
        |
        v
Ceres compute-node allocation
        |
        v
template/before.sh.erb
selects an available host/port
        |
        v
template/script.sh.erb
loads Apptainer and starts the application
        |
        v
Apptainer SIF
        |
        v
interactive Python web application
        |
        v
template/after.sh.erb
waits for the service to become reachable
        |
        v
view.html.erb
renders the Connect button
        |
        v
Open OnDemand reverse proxy
        |
        v
user's browser
```

The user does not connect directly to the compute node. Open OnDemand proxies browser traffic to the host and dynamically selected TCP port on which the application is listening.

## What the SIF Contains — and What It Does Not

The current proof-of-concept deliberately separates the Python runtime from the demonstration application source.

The SIF is built from the public `python:3.12-slim` OCI image:

```text
python:3.12-slim OCI image
        |
        | apptainer build
        v
ood-web-demo.sif
contains Python runtime
        |
        | apptainer exec
        |
        +---- bind mount ---- ~dpu/containers/ood-web-demo/
        |                         |
        |                         └── app.py
        v
running container
        |
        └── /opt/ood-web-demo/app.py
```

The SIF therefore contains Python, but it does **not** contain:

```text
~dpu/containers/ood-web-demo/app.py
```

The application is supplied at runtime through a read-only bind mount:

```bash
--bind "${app}:/opt/ood-web-demo:ro"
```

This design was chosen for rapid iteration during the Open OnDemand / Slurm / Apptainer proof-of-concept.

A change to `app.py` does not technically require rebuilding the SIF because `app.py` is not baked into the SIF. The updated source is picked up the next time the application starts.

For regression testing, rebuilding the SIF is still harmless and can be useful when validating the complete development procedure from a clean state.

The production architecture is expected to evolve toward a complete OCI image that contains the real application and its dependencies.

## Current Demonstration Application

The demonstration application is intentionally implemented with only the Python standard library.

It provides:

- a server-side HTTP application;
- a form that accepts a user's name;
- a server-generated response such as `Hello, Steve.`;
- the Ceres compute-node hostname;
- the Slurm job ID; and
- a process-local request counter.

The form is important because it demonstrates active request handling rather than merely serving a static HTML file.

The application is started inside Apptainer from `template/script.sh.erb`.

## Prerequisites

The following assumptions apply to this development procedure:

- the repository is available on Ceres;
- `~dpu` resolves to the top-level `drone-pilot-upload` Git checkout;
- the user has access to the `dash_drone` Slurm account;
- Open OnDemand development apps are available under `~/ondemand/dev`;
- `apptainer/1.4.1` is available through the Ceres module environment.

The relevant repository path used during development was:

```text
/project/dash_drone/user/stephen.amerige/projects/github/precision-sustainable-ag/drone-pilot-upload
```

## Obtain a Ceres Compute Allocation

Apptainer build and manual runtime testing should be performed on a Ceres compute node rather than relying on the login node.

From the Ceres login environment:

```bash
cd ~dpu
```

Request a small interactive Slurm allocation:

```bash
salloc \
    -A dash_drone \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task=2 \
    --mem=4G \
    --time=01:00:00
```

After the allocation is granted, verify the allocated compute node and Slurm job:

```bash
hostname
echo "$SLURM_JOB_ID"
```

Load Apptainer:

```bash
module load apptainer/1.4.1
```

Verify the version:

```bash
apptainer --version
```

The manual `salloc` allocation is independent of any later Open OnDemand allocation. Open OnDemand will submit its own Slurm job when the Batch Connect application is launched.

## Build the Demo SIF

From the top-level Git repository:

```bash
cd ~dpu
```

Build the SIF:

```bash
apptainer build --force \
    sif_files/ood-web-demo.sif \
    docker://python:3.12-slim
```

The command follows the form:

```text
apptainer build [options] OUTPUT SOURCE
```

For this demo:

```text
OUTPUT = sif_files/ood-web-demo.sif
SOURCE = docker://python:3.12-slim
```

Because the output path is relative, running the command from `~dpu` creates:

```text
~dpu/sif_files/ood-web-demo.sif
```

Verify the artifact:

```bash
ls -lh sif_files/ood-web-demo.sif
```

Optionally inspect its file type:

```bash
file sif_files/ood-web-demo.sif
```

## Manually Test the Apptainer Application

Before involving Open OnDemand, test the application directly inside the current Slurm allocation.

From `~dpu`:

```bash
export PORT=8000
```

Run:

```bash
apptainer exec \
    --bind "$PWD/containers/ood-web-demo:/opt/ood-web-demo:ro" \
    --env PORT="$PORT" \
    sif_files/ood-web-demo.sif \
    python /opt/ood-web-demo/app.py
```

Expected output resembles:

```text
Starting application on ceresXX-compute-YY:8000; Slurm job 219xxxxx
```

The process remains in the foreground because it is the running web application.

Stop the manual test with `Ctrl+C`.

The purpose of this test is to isolate the Apptainer/application boundary before introducing Open OnDemand.

## Release the Manual Allocation

After the manual Apptainer test is complete, the allocation used for the build/test can be released.

Exit the allocated shell:

```bash
exit
```

Verify from the login environment:

```bash
squeue -u "$USER"
```

This keeps the subsequent Open OnDemand test clean because the only new Slurm job should be the one created by Open OnDemand.

## Open OnDemand Files

### `manifest.yml`

Defines how the application appears in Open OnDemand and identifies the application as a Batch Connect application.

The important setting is:

```yaml
role: batch_connect
```

This tells Open OnDemand that the application is launched through the scheduler rather than as a conventional Passenger application.

### `form.yml`

Defines the launch form.

The current form uses Open OnDemand's predefined Batch Connect attributes:

```yaml
form:
  - bc_account
  - bc_queue
  - bc_num_hours
  - bc_num_slots
```

Open OnDemand supplies the user-facing controls for these attributes.

The current Ceres cluster is selected with:

```yaml
cluster: "ceres"
```

During normal testing:

```text
Account:          dash_drone
Queue:            left blank
Number of hours:  1
Number of nodes:  1
```

Leaving Queue blank currently allows Ceres to select its default Slurm partition.

### `submit.yml.erb`

Selects the Ceres scheduler configuration and uses the basic Batch Connect template:

```yaml
cluster: "ceres"

batch_connect:
  template: "basic"
```

The explicit `cluster: "ceres"` setting in this file was required during Ceres development even though the cluster is also identified in `form.yml`.

### `template/before.sh.erb`

Runs before the main application payload.

It uses Open OnDemand's `find_port` helper to select an available TCP port on the allocated compute node:

```bash
port=$(find_port "${host}")
```

The selected `host` and `port` values are then available to the remaining Batch Connect lifecycle scripts.

### `template/script.sh.erb`

Runs the actual application payload inside the Slurm allocation.

The current demo:

1. identifies the project checkout;
2. identifies the demo SIF and application source;
3. loads `apptainer/1.4.1`;
4. bind-mounts the application source into the container;
5. passes the dynamically selected port into the container; and
6. uses `exec` so the application remains directly tied to the lifetime of the Slurm job.

Conceptually:

```bash
exec apptainer exec \
    --bind "${app}:/opt/ood-web-demo:ro" \
    --env PORT="${port}" \
    "${sif}" \
    python /opt/ood-web-demo/app.py
```

Using `exec` is intentional. When the Open OnDemand session is cancelled, Slurm terminates the job, which terminates the Apptainer runtime and the application process.

### `template/after.sh.erb`

Waits until the application is actually listening before Open OnDemand marks the session ready.

It uses the Batch Connect helper:

```bash
wait_until_port_used "${host}:${port}" 120
```

If the service does not become available before the timeout, the Batch Connect session is cleaned up instead of presenting a Connect action for an unavailable application.

### `view.html.erb`

Renders the Connect button after the application becomes ready.

The current implementation uses Open OnDemand's reverse-proxy route:

```text
/rnode/<host>/<port>/
```

This allows the browser to reach a service running on an internal compute node without exposing the compute node directly.

## Install or Refresh the Sandbox Copy

The Git repository is the authoritative source. Synchronize it into the active Open OnDemand development location before testing.

From the repository:

```bash
cd ~dpu
```

Create the destination if necessary:

```bash
mkdir -p ~/ondemand/dev/drone-pilot-upload
```

Synchronize:

```bash
rsync -av --delete \
    ondemand/drone-pilot-upload/ \
    ~/ondemand/dev/drone-pilot-upload/
```

Ensure the shell templates are executable in both locations:

```bash
chmod +x \
    ondemand/drone-pilot-upload/template/*.sh.erb \
    ~/ondemand/dev/drone-pilot-upload/template/*.sh.erb
```

Verify:

```bash
ls -l ~/ondemand/dev/drone-pilot-upload/template/*.sh.erb
```

The application should appear under:

```text
Develop
  -> My Sandbox Apps (Development)
  -> Drone Pilot Upload Test
```

If Open OnDemand appears to be using stale metadata, use **Develop -> Restart Web Server** and reload the sandbox application.

## Launch the Demo Through Open OnDemand

In Ceres Open OnDemand:

1. select **Develop -> My Sandbox Apps (Development)**;
2. select **Drone Pilot Upload Test**;
3. enter `dash_drone` for Account;
4. leave Queue blank unless a specific partition is intentionally required;
5. request one hour;
6. request one node; and
7. click **Launch**.

The session should progress through states similar to:

```text
Queued
  -> Starting
  -> Running
```

Open OnDemand submits its own Slurm job for this session.

Monitor from SSH:

```bash
squeue -u "$USER"
```

Once ready, Open OnDemand displays:

```text
Connect to Drone Pilot Upload Test
```

Clicking the button opens the application through the Open OnDemand reverse proxy.

## Verify Interactive Application Behavior

The page should identify:

- the allocated Ceres compute node;
- the Slurm job ID;
- the number of HTTP requests served.

Enter a name in the form and click **Submit**.

A successful server-side response resembles:

```text
Hello, Steve.
```

The request counter should increase.

This confirms that the browser is not merely displaying static content; it is communicating with application code running inside Apptainer on the Slurm-allocated compute node.

## Monitor Open OnDemand and Slurm State

A useful shell-side monitor is:

```bash
squeue -u "$USER"
```

A lightweight helper used during development was:

```bash
#!/bin/bash

squeue -u "$USER"

find ~/ondemand/data/sys/dashboard/batch_connect -maxdepth 3 -type f \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' 2>/dev/null \
    | sort | tail -40
```

This makes it easy to see both scheduler state and Open OnDemand session-state activity.

Generated Batch Connect session files are stored below:

```text
~/ondemand/data/sys/dashboard/batch_connect/
```

These are runtime/debugging artifacts managed by Open OnDemand. They should not be treated as application source.

Useful generated files may include:

```text
before.sh
script.sh
after.sh
job_script_content.sh
job_script_options.json
output.log
user_defined_context.json
```

`output.log` is usually the first place to inspect when a session remains in `Starting` or transitions to `Completed` unexpectedly.

## Stop the Application

The user should stop the application through **My Interactive Sessions** in Open OnDemand.

Click **Cancel** for the running session.

Cancellation terminates the associated Slurm job. Because the application is the foreground process launched through Apptainer, this also terminates:

```text
Slurm allocation
    -> Apptainer runtime
    -> application process
```

The compute resources are then released.

Verify from SSH:

```bash
squeue -u "$USER"
```

The Open OnDemand job should disappear.

After cancellation, refreshing the previously connected application URL should no longer reach the application.

The **Delete** action is separate from **Cancel**:

- **Cancel** terminates the running computational session.
- **Delete** removes the retained Open OnDemand session record/runtime data from the UI.

## Complete Regression-Test Procedure

After any source or configuration change, the complete validation sequence is:

```text
1. cd ~dpu
2. Obtain a manual compute allocation with salloc.
3. Load apptainer/1.4.1.
4. Rebuild the SIF with apptainer build --force.
5. Manually run the application in Apptainer.
6. Stop the manual application.
7. Exit the manual allocation.
8. Synchronize the repository OOD definition with rsync.
9. Ensure template executable permissions.
10. Launch the sandbox app from Ceres Open OnDemand.
11. Confirm a new Slurm job appears.
12. Wait for the session to reach Running.
13. Click Connect.
14. Submit the form and verify the server-generated response.
15. Click Cancel.
16. Verify the OOD Slurm job disappears.
17. Refresh the application tab and verify the service is unavailable.
```

This end-to-end test validates the complete development path rather than only an individual component.

## Development Lessons Established by This Demo

### Open OnDemand is the application launcher

The planned Ceres application does not need to reproduce the existing Hazel Passenger deployment.

Open OnDemand can present the application launch interface, request scheduler resources, start the application on a compute node, and proxy the user's browser to it.

### The application runs inside a Slurm allocation

The user-facing application itself can run as an interactive Slurm workload rather than as a persistent web service on a login or web node.

### Apptainer and Batch Connect integrate cleanly

Batch Connect does not need to know application-specific details beyond how to start the process and determine readiness.

The main application-launch template can invoke Apptainer just as it could invoke any other executable.

### Application lifetime follows the scheduler session

The application can remain in the foreground and rely on Slurm/Open OnDemand to control its lifecycle.

No separate daemon-management system is required for this interaction model.

### The user's browser does not connect directly to compute nodes

Open OnDemand's reverse proxy provides the browser connection to the application.

This avoids requiring externally reachable compute-node ports.

### The current SIF is a runtime image, not the complete application image

For this proof, the SIF supplies Python while `app.py` is bind-mounted from the Git repository.

This is intentionally different from the intended production packaging model.

## Known Development Details

During initial development, several issues were encountered and resolved:

- Open OnDemand required an explicit Ceres cluster definition in `submit.yml.erb`.
- Batch Connect shell templates needed executable permissions.
- The application payload must remain in the foreground for the life of the session.
- `after.sh.erb` should wait for the application port before exposing the Connect action.
- OOD-generated session files under `~/ondemand/data` are useful for debugging but are not source files.
- A manual `salloc` allocation used for building/testing is separate from the allocation created later by Open OnDemand.
- The SIF currently contains the Python runtime but not the demonstration `app.py`.

These details are retained because they are likely to be useful when developing future interactive applications on Ceres.

## Intended Container Distribution Architecture

The current local SIF build is a development convenience.

The intended longer-term distribution path is:

```text
SteveAmerige
    |
    | git commit / git push
    v
precision-sustainable-ag/drone-pilot-upload
    |
    | triggers GitHub Actions
    v
GitHub Actions
    |
    | builds OCI image
    | publishes using temporary GITHUB_TOKEN
    v
private GHCR image
    |
    | authenticated pull from HPC
    v
Ceres / Atlas / Hazel
    |
    | Apptainer converts OCI image locally
    v
local .sif
```

GitHub Actions should normally publish with:

```yaml
permissions:
  contents: read
  packages: write
```

A long-lived `psagriculture` PAT should not be placed into the GitHub Actions workflow unless a future requirement makes that necessary.

The durable `psagriculture` GitHub account is intended for external/headless authentication from systems such as Ceres, Atlas, and Hazel when private GHCR access is required.

Credentials, API keys, passwords, MongoDB secrets, and other runtime secrets must not be baked into the container image.

## Next Refactor Step

The next major step is to replace the demonstration application with the actual `drone-pilot-upload` runtime.

That work will require progressively introducing:

- the real Flask backend;
- the compiled React frontend;
- Python and system dependencies such as ExifTool;
- application configuration;
- MongoDB connectivity;
- persistent Ceres storage;
- flight ingestion behavior; and
- eventually the Slurm-driven scientific-processing pipeline.

Those dependencies should be introduced incrementally while preserving the now-proven lifecycle:

```text
Open OnDemand
    -> Slurm
    -> Apptainer
    -> application
    -> Connect
    -> user interaction
    -> Cancel
```

The current demo should remain available as a minimal known-good diagnostic whenever future application changes make it unclear whether a problem lies in Open OnDemand / Slurm / Apptainer integration or in `drone-pilot-upload` itself.

