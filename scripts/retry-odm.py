#!/usr/bin/env python3
"""Operator-only, one-attempt ODM recovery after a confirmed Slurm timeout/OOM.

Dry runs only inspect files and Slurm accounting. Live submission requires both
--submit and --confirm-job-id; the coordinator never calls this script.
A durable .submitting record is created before sbatch, and ambiguous attempts
must be reconciled by an operator rather than blindly resubmitted.
"""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from importlib.util import module_from_spec, spec_from_file_location

SUBMITTED = "odm-submission.submitted.json"
RESOURCE_FAILURES = {"TIMEOUT", "OUT_OF_MEMORY"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff"}
JOB_ID_PATTERN = re.compile(r"^(\d+)(?:;[A-Za-z0-9_.-]+)?$")


def load_profiles(script):
    """Use the same cluster profiles as the regular submitter."""
    spec = spec_from_file_location("dpu_submit_pending", script)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load profile definitions from {script}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RESOURCE_PROFILES, module.preview_resource_profile


def guid(value):
    value = str(value)
    if str(UUID(value)) != value:
        raise ValueError(f"Noncanonical flight identifier: {value}")
    return value


def inventory_for(images):
    if not images.is_dir() or images.is_symlink():
        raise ValueError("Original images directory is missing or a symbolic link")
    count = total = 0
    with os.scandir(images) as entries:
        for entry in entries:
            if entry.name.lower().endswith(tuple(IMAGE_EXTENSIONS)) and entry.is_file(follow_symlinks=False):
                count += 1
                total += entry.stat(follow_symlinks=False).st_size
    if not count:
        raise ValueError("No supported original images remain")
    return {"image_count": count, "total_image_bytes": total}


def slurm_state(job_id):
    cmd = ["sacct", "-n", "-P", "-X", "-j", job_id, "-o", "JobIDRaw,State,ExitCode"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(f"Slurm accounting unavailable: {result.stderr.strip()}")
    matches = [
        row.split("|") for row in result.stdout.splitlines()
        if row and row.split("|")[0] == job_id
    ]
    if len(matches) != 1 or len(matches[0]) != 3:
        raise ValueError(f"Expected exactly one authoritative Slurm job row for {job_id}")
    state = matches[0][1].split()[0].split("+")[0].upper()
    if state not in RESOURCE_FAILURES:
        raise ValueError(f"Job {job_id} state={state}; only TIMEOUT or OUT_OF_MEMORY can be retried")
    return state


def plan_retry(args, repo, root):
    receipt_paths = list((root / "site-id").glob(f"*/flights/{guid(args.flight_id)}/{SUBMITTED}"))
    if len(receipt_paths) != 1:
        raise ValueError(f"Expected exactly one submission receipt for {args.flight_id}")
    receipt_path = receipt_paths[0]
    folder = receipt_path.parent
    organization = guid(folder.parent.parent.name)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("flight_id") != args.flight_id or receipt.get("organization_id") != organization:
        raise ValueError("Submission receipt does not match flight identity")
    if str(receipt.get("slurm_job_id")) != args.failed_job_id:
        raise ValueError("Failed job ID does not match the original submission receipt")
    if not (folder / "mongo-registration.done.json").is_file():
        raise ValueError("MongoDB registration receipt missing")
    for name in ("odm-submission.pending.json", "odm-submission.submitting.json"):
        if (folder / name).exists() or (folder / name).is_symlink():
            raise ValueError(f"Ambiguous or conflicting submission state: {name}")

    observed = inventory_for(folder / "images")
    expected = receipt.get("image_inventory")
    if expected is None:
        if not args.acknowledge_unverified_images:
            raise ValueError(
                "Legacy receipt lacks image inventory; independently verify originals "
                "and explicitly pass --acknowledge-unverified-images"
            )
        integrity = "operator acknowledged legacy receipt without image inventory"
    elif (not isinstance(expected, dict) or
          type(expected.get("image_count")) is not int or
          type(expected.get("total_image_bytes")) is not int or
          expected != observed):
        raise ValueError("Original image count or bytes differ from submission inventory")
    else:
        integrity = "count and bytes match receipt (not a checksum)"

    state = slurm_state(args.failed_job_id)
    profiles, choose = load_profiles(repo / "scripts" / "submit-pending-odm.py")
    selected, reason = choose(args.sandbox, observed)
    cluster_profiles = profiles[args.sandbox]
    prior_name = (receipt.get("resource_profile") or {}).get("name")
    minimum_index = next(i for i, p in enumerate(cluster_profiles) if p["name"] == selected["name"])
    if prior_name is not None:
        matches = [i for i, p in enumerate(cluster_profiles) if p["name"] == prior_name]
        if len(matches) != 1:
            raise ValueError("Unknown profile in original submission receipt")
        minimum_index = max(minimum_index, matches[0])
    candidates = [
        p for i, p in enumerate(cluster_profiles)
        if i > minimum_index and p["name"] == args.profile
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Profile {args.profile!r} is not larger than the prior/workload profile; "
            "choose a larger approved profile or escalate for manual sizing"
        )
    profile = candidates[0]
    retry_stem = f"odm-retry-from-{args.failed_job_id}"
    submitting = folder / f"{retry_stem}.submitting.json"
    submitted = folder / f"{retry_stem}.submitted.json"
    retry_parent = folder / "odm-retries"
    attempt = retry_parent / f"retry-{args.failed_job_id}"
    if retry_parent.is_symlink() or attempt.exists() or attempt.is_symlink():
        raise ValueError("Retry workspace already exists or is unsafe; reconcile manually")
    for marker in (submitting, submitted):
        if marker.exists() or marker.is_symlink():
            raise ValueError(f"Existing retry marker; reconcile manually: {marker}")

    job_script = repo / "scripts" / f"odm-{args.sandbox}-flight.sh"
    if not job_script.is_file() or "--retry-from-job" not in job_script.read_text(encoding="utf-8"):
        raise ValueError("The local batch script does not support isolated retry workspaces")

    command = [
        "sbatch", "--parsable", f"--partition={profile['partition']}",
        f"--cpus-per-task={profile['cpus']}", f"--mem={profile['mem']}",
        f"--time={profile['time']}",
        f"--job-name=dpu-retry-{args.flight_id}",
        f"--chdir={folder}",
        f"--output={folder}/{retry_stem}-slurm-%j.out",
        f"--error={folder}/{retry_stem}-slurm-%j.err",
    ]
    if profile["gres"]:
        command.append(f"--gres={profile['gres']}")
    command.extend([str(job_script), organization, args.flight_id,
                    "--retry-from-job", args.failed_job_id])
    record = {
        "organization_id": organization, "flight_id": args.flight_id,
        "previous_slurm_job_id": args.failed_job_id, "previous_slurm_state": state,
        "requested_resources": {
            "profile": profile["name"], "partition": profile["partition"],
            "gres": profile["gres"], "cpus_per_task": profile["cpus"],
            "memory": profile["mem"], "walltime": profile["time"],
        },
        "image_inventory": observed, "inventory_assurance": integrity,
        "selection_reason": reason,
        "retry_workspace": str(attempt),
        "authorized_at": datetime.now(timezone.utc).isoformat(),
    }
    return folder, submitting, submitted, command, record


def atomic_json(path, payload):
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".dpu-retry-", delete=False
        ) as stream:
            tmp = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


def reserve_marker(path, record):
    # O_EXCL is the durable at-most-once guard against concurrent operators.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--sandbox", required=True, choices=("atlas", "ceres"))
    parser.add_argument("--flight-id", required=True)
    parser.add_argument("--failed-job-id", required=True)
    parser.add_argument("--profile", required=True, choices=("medium", "large"))
    parser.add_argument("--acknowledge-unverified-images", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--submit", action="store_true")
    parser.add_argument("--confirm-job-id",
                        help="Required for submission; must equal --failed-job-id")
    args = parser.parse_args()
    if not args.failed_job_id.isdigit():
        parser.error("--failed-job-id must be numeric")
    if args.submit and args.confirm_job_id != args.failed_job_id:
        parser.error("--submit requires --confirm-job-id matching --failed-job-id")
    if args.dry_run and args.confirm_job_id:
        parser.error("--confirm-job-id is only accepted with --submit")

    repo = args.repo.expanduser().resolve(strict=True)
    root = args.data_root.expanduser().resolve(strict=True)
    lock = None
    try:
        if args.submit:
            lock = open(root / ".dpu-odm-submit.lock", "a+", encoding="utf-8")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        folder, submitting, submitted, cmd, record = plan_retry(args, repo, root)
        print(f"CONFIRMED: {record['previous_slurm_state']} job={args.failed_job_id}", flush=True)
        print(f"  {record['image_inventory']} / {record['inventory_assurance']}", flush=True)
        print(f"  Selected {record['requested_resources']}", flush=True)
        print(f"  Retry workspace: {record['retry_workspace']}", flush=True)
        if args.dry_run:
            print("WOULD SUBMIT: " + " ".join(cmd), flush=True)
            print("DRY RUN: no job, marker, or workspace created", flush=True)
            return 0

        # Do not make the retry appear safe-to-resubmit after an ambiguous sbatch.
        reserve_marker(submitting, record)
        environment = {
            k: v for k, v in os.environ.items()
            if "MONGODB" not in k.upper() and k != "DPU_SECRETS_FILE"
        }
        environment.update(DPU_DATA_ROOT=str(root), DPU_REPO=str(repo))
        result = subprocess.run(cmd, cwd=repo, env=environment,
                                capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"sbatch failed ({result.returncode}): {result.stderr.strip()}")
        match = JOB_ID_PATTERN.fullmatch(result.stdout.strip())
        if match is None:
            raise RuntimeError(f"Ambiguous sbatch output: {result.stdout.strip()!r}")
        record["retry_slurm_job_id"] = match.group(1)
        record["submitted_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(submitted, record)
        submitting.unlink()
        print(f"SUBMITTED: retry job={record['retry_slurm_job_id']}; "
              "original submission and outputs preserved", flush=True)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        if args.submit:
            print("No automatic retry. Reconcile submission/marker state manually.",
                  file=sys.stderr, flush=True)
        return 1
    finally:
        if lock is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
