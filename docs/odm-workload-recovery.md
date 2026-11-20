# Workload-aware ODM sizing and resource-failure recovery (Issue #28)

**Status:** Feature-branch procedure; operator review and validation required before deployment.
**Scope:** Atlas A100 GPU and Ceres CPU sandbox ODM submissions. No production deployment, automatic resubmission, or automated promotion/reprocessing of earlier flight products.
**Related:** [#28](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/28) (resource sizing and safe recovery), [#23](https://github.com/precision-sustainable-ag/drone-pilot-upload/issues/23) (broader processing/reprocessing and result publication).

## Before changing a running coordinator

Both submitters read scripts/submit-pending-odm.py from the repository checkout. The Atlas scripts/register-and-submit-atlas.sh and Ceres scripts/coordinate-ceres.sh entrypoints pass **--apply-resource-profile**. **Updating a checkout used by a scheduled coordinator can affect its very next submission.** Do not use a feature-branch checkout as the active scheduled checkout before testing and authorizing deployment.

This issue implements a **single operator-controlled retry of an original job that Slurm unequivocally classifies as TIMEOUT or OUT_OF_MEMORY**. It does not retry generic FAILED/CANCELLED jobs or previously retried jobs. The original submission receipt, accounting snapshot, ODM output directories, source images, and MongoDB processing record are not replaced by retry submission or inspection.

## Profile selection

Flight inventory is a count and sum of bytes of regular JPG/JPEG/TIF/TIFF files (case insensitive), excluding symlinks. **A matching count and byte sum is not a cryptographic integrity check.** Thresholds are provisional workload categories; they are **not** measured guarantees of ODM runtime or memory consumption.

| Profile | Image count AND total bytes | Atlas allocation | Ceres allocation |
| --- | --- | --- | --- |
| Small | Up to 100 AND up to 10 GiB | 1 A100, 4 CPUs, 64G, 1 h | 4 CPUs, 64G, 8 h |
| Medium | Up to 500 AND up to 50 GiB | 1 A100, 4 CPUs, 128G, 4 h | 4 CPUs, 128G, 16 h |
| Large | Everything larger | 1 A100, 4 CPUs, 256G, 12 h | 4 CPUs, 256G, 48 h |

Slurm partition and GRES are gpu-a100/gpu:a100:1 on Atlas and ceres/none on Ceres. The Atlas batch-script GPU defaults also use A100. Actual cluster limits and resource access must be verified independently before processing unusually large flights.

### Slurm configuration and test-only validation (November 20, 2026)

On the respective login nodes, operators inspected `scontrol show partition`, `sinfo`, and `sacctmgr ... show qos`. The following limits were observed:

- **Atlas `gpu-a100`:** three nodes, eight A100 GPUs per node, 128 CPUs per node, 2,063,965 MiB/node; partition MaxTime unlimited; `a100` QoS MaxWall **7 days**, MaxTRESPerUser **mem=1500G**.
- **Ceres `ceres`:** partition MaxTime **60 days**; node summary minimum **752,000 MiB** and **96 CPUs** per node; `ceres` QoS MaxWall **21 days** and MaxTRESPerUser **cpu=4000,mem=36T,node=32**.

Both clusters accepted the **largest proposed profile** in a read-only `sbatch --test-only` feasibility check:

~~~bash
# Atlas -- test-only, not a job submission
sbatch --test-only --account=dash_drone --partition=gpu-a100 \
  --gres=gpu:a100:1 --cpus-per-task=4 --mem=256G \
  --time=12:00:00 --wrap='/bin/true'

# Ceres -- test-only, not a job submission
sbatch --test-only --account=dash_drone --partition=ceres \
  --cpus-per-task=4 --mem=256G --time=48:00:00 \
  --wrap='/bin/true'
~~~

Atlas returned an estimated placement on `atlas-0243`; Ceres returned `ceres25-compute-42`. These were **Slurm feasibility estimates, not actual jobs**. The partition/QoS observations and test-only acceptance support configuration compatibility, **not guaranteed queue admission, account-level approvals, or validated processing runtime**.

For pending submissions, on a Slurm-capable authorized host, inspect the proposed command **without consuming any queue marker**:

~~~bash
python3 scripts/submit-pending-odm.py \
  --sandbox atlas --data-root "$DPU_DATA_ROOT" --repo "$PWD" \
  --apply-resource-profile --dry-run
~~~

Use --sandbox ceres on Ceres. The optional --apply-resource-profile is required when invoking the submitter directly; without it, profile selection is **preview-only** and older submission behavior remains. The scheduled coordinator entrypoints on the feature branch now opt in explicitly.

Successful submission receipts include image inventory, profile choice, and requested Slurm resources. scripts/collect-atlas-status.py collects Slurm timing/memory evidence (where available); a recorded MaxRSS is step-specific and may not represent whole-job peak memory.

## Recovery: read-only review, then explicit operator submission

1. Confirm the original Slurm job ID and its TIMEOUT or OUT_OF_MEMORY state with sacct, its original submitted receipt, and logs. Do not retry merely because squeue no longer lists the job.
2. Review the original imagery, original odm/ and odm-tmp/, existing orthophoto/indices, and pending/submitting states. Use the review command below. A legacy submission receipt without inventory requires *independent* imagery confirmation by an operator.
3. Select a strictly larger approved profile than both the original recorded profile (if present) **and** the profile suggested by the current image inventory. If there is no larger profile, escalate for manual sizing rather than guessing.
4. Start with the non-mutating retry dry run; inspect partition/GRES, memory, time, retry directory, and reported integrity assurance.
5. Only after separately approving the specific resource request, use --submit together with --confirm-job-id equal to the original failed Slurm job ID. **Do not submit a test retry against a successful historical job.**

Example with operator-supplied identifiers (substitute real values):

~~~bash
python3 scripts/collect-atlas-status.py \
  --data-root "$DPU_DATA_ROOT" --flight-id "$FLIGHT_ID" \
  --dry-run --review-recovery

python3 scripts/retry-odm.py \
  --sandbox atlas --data-root "$DPU_DATA_ROOT" --repo "$PWD" \
  --flight-id "$FLIGHT_ID" --failed-job-id "$FAILED_JOB_ID" \
  --profile medium --dry-run
~~~

For a Ceres flight, use --sandbox ceres. If the old receipt has no inventory, independently verify the original images and then **explicitly** add --acknowledge-unverified-images to the dry run and authorized submission. This flag cannot prove byte integrity.

**Authorized submission only (not an unattended coordinator command):**

~~~bash
python3 scripts/retry-odm.py \
  --sandbox atlas --data-root "$DPU_DATA_ROOT" --repo "$PWD" \
  --flight-id "$FLIGHT_ID" --failed-job-id "$FAILED_JOB_ID" \
  --profile medium --submit --confirm-job-id "$FAILED_JOB_ID"
~~~

The retry acquires the normal shared submit lock, reserves odm-retry-from-<original-job>.submitting.json exclusively **before** calling sbatch, and on unambiguous success writes a separate odm-retry-from-<original-job>.submitted.json. It gives the new Slurm job an isolated workspace, odm-retries/retry-<original-job>/odm and odm-tmp, leaving the original odm/ and odm-tmp/ untouched. The command does not re-upload images or mutate MongoDB.

If sbatch fails, its output is ambiguous, or the process is interrupted, **leave the .submitting marker untouched** and investigate sacct, squeue, Slurm logs, and receipt state before any further action. Even a rejected submission retains the marker to fail closed. Never delete a marker simply to force reprocessing.

## Inspecting an attempted retry

From a Slurm-capable login host (read-only):

~~~bash
python3 scripts/inspect-odm-retry.py \
  --sandbox atlas --data-root "$DPU_DATA_ROOT" \
  --flight-id "$FLIGHT_ID" --previous-job-id "$FAILED_JOB_ID"

python3 scripts/inspect-odm-retry.py \
  --sandbox atlas --data-root "$DPU_DATA_ROOT" \
  --flight-id "$FLIGHT_ID" --previous-job-id "$FAILED_JOB_ID" \
  --review-publication
~~~

The inspector reads the separate retry receipt and Slurm accounting and reports elapsed time, requested memory, per-step MaxRSS, exit code, and nonempty retry products. --review-publication is only a **preliminary filesystem preflight**: it reports missing products, non-successful Slurm jobs, conflicting existing odm/ / odm-tmp/, and existing preview directories; it does **not** verify GeoTIFF structure or scientific validity.

Atlas normally generates orthophoto, VARI and GLI within its ODM batch job. Ceres generates only the orthophoto in that job; VARI, GLI, and PNG previews require a separate compute-node postprocessing step. **The current Ceres postprocessor targets the original odm/, not isolated retry workspaces.** Do not run it on a retry expecting it to publish or process retry indices automatically.

**No automatic promotion exists in Issue #28.** The existing preview generator and MongoDB reconciler use the original flight odm/ paths and original submission/accounting records. They will not independently discover the isolated retry result; running them is not an authorized publication mechanism. Preserve original outputs and history, inspect the retry data separately, and defer intentional publication of reprocessed outputs and related MongoDB changes to #23 or a separately reviewed operator procedure.

## Regression tests, runnable on Atlas/Ceres login nodes

The suite is intentionally isolated from real Slurm, MongoDB, credentials, files, and GPU/CPU processing. It uses temporary directories and mocked Slurm responses.

~~~bash
python3 -m unittest discover -s tests -p 'test_odm_*.py' -v
bash -n scripts/register-and-submit-atlas.sh scripts/coordinate-ceres.sh \
  scripts/odm-atlas-flight.sh scripts/odm-ceres-flight.sh
~~~

Use a clean working tree or detached/temporary feature-branch copy for these tests. Tests run automatically through .github/workflows/odm-regression.yml for relevant pull requests. This is a mocked regression suite, **not** a substitute for a reviewed, minimal real Slurm/Apptainer smoke test at deployment time. Do not perform a real test on a login node.

## Operational boundary

Do not deploy this branch, replace original outputs, remove ambiguous markers, or launch a real retry as part of documentation or mocked testing. Any scheduler activation, larger resource request, or intentional publication requires the operator's review. Production deployment remains out of scope for #28.
