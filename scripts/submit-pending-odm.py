#!/usr/bin/env python3
"""Submit queued ODM jobs from a Slurm-capable host (not inside Apptainer).

At-most-once *automatic* submission: a flight is moved to `.submitting`
before sbatch. If the process crashes, that file remains and requires human
reconciliation, rather than risking duplicate processing.
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

PENDING = "odm-submission.pending.json"
SUBMITTING = "odm-submission.submitting.json"
SUBMITTED = "odm-submission.submitted.json"
REGISTERED = "mongo-registration.done.json"
JOB_ID_PATTERN = re.compile(r"^(\d+)(?:;[A-Za-z0-9_.-]+)?$")
IMAGE_EXTENSIONS = frozenset((".jpg", ".jpeg", ".tif", ".tiff"))

# Initial sizing *proposals*, deliberately NOT used for sbatch yet.
# Thresholds are provisional workload buckets, not validated runtime estimates.
# Keep CPUs at four until ODM --max-concurrency is adjusted and tested.
GIB = 1024 ** 3
RESOURCE_PROFILES = {
    "atlas": (
        {"name": "small", "max_images": 100, "max_bytes": 10 * GIB,
         "partition": "gpu-a100", "gres": "gpu:a100:1",
         "cpus": 4, "mem": "64G", "time": "01:00:00"},
        {"name": "medium", "max_images": 500, "max_bytes": 50 * GIB,
         "partition": "gpu-a100", "gres": "gpu:a100:1",
         "cpus": 4, "mem": "128G", "time": "04:00:00"},
        {"name": "large", "max_images": None, "max_bytes": None,
         "partition": "gpu-a100", "gres": "gpu:a100:1",
         "cpus": 4, "mem": "256G", "time": "12:00:00"},
    ),
    "ceres": (
        {"name": "small", "max_images": 100, "max_bytes": 10 * GIB,
         "partition": "ceres", "gres": None,
         "cpus": 4, "mem": "64G", "time": "08:00:00"},
        {"name": "medium", "max_images": 500, "max_bytes": 50 * GIB,
         "partition": "ceres", "gres": None,
         "cpus": 4, "mem": "128G", "time": "16:00:00"},
        {"name": "large", "max_images": None, "max_bytes": None,
         "partition": "ceres", "gres": None,
         "cpus": 4, "mem": "256G", "time": "48:00:00"},
    ),
}


def preview_resource_profile(sandbox, inventory):
    """Suggest a conservative bucket; never change submission resources."""
    count = inventory["image_count"]
    total_bytes = inventory["total_image_bytes"]
    for profile in RESOURCE_PROFILES[sandbox]:
        if profile["max_images"] is None or (
            count <= profile["max_images"] and
            total_bytes <= profile["max_bytes"]
        ):
            reason = (
                f"{count} images, {total_bytes} bytes; "
                "provisional count/size thresholds (not a runtime guarantee)"
            )
            return profile, reason
    raise AssertionError("Last resource profile must be unbounded")



def guid(value):
    value = str(value)
    if str(UUID(value)) != value:
        raise ValueError(f"Noncanonical GUID: {value}")
    return value


def atomic_json(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".odm-submission-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def image_inventory(images_dir):
    """Inspect the same regular-file image types accepted by the ODM job scripts."""
    count = 0
    total_bytes = 0
    with os.scandir(images_dir) as entries:
        for entry in entries:
            if entry.name.lower().endswith(tuple(IMAGE_EXTENSIONS)) and entry.is_file(follow_symlinks=False):
                count += 1
                total_bytes += entry.stat(follow_symlinks=False).st_size
    if count == 0:
        raise ValueError("No supported regular-file images in flight images directory")
    return {"image_count": count, "total_image_bytes": total_bytes}


def inspect(path):
    flight_dir = path.parent
    if flight_dir.parent.name != "flights":
        raise ValueError("Unexpected flight directory layout")
    org = guid(flight_dir.parent.parent.name)
    flight = guid(flight_dir.name)
    request = json.loads(path.read_text(encoding="utf-8"))
    if request.get("flight_id") != flight or request.get("organization_id") != org:
        raise ValueError("Submission request does not match flight directory")
    if not (flight_dir / REGISTERED).is_file():
        raise ValueError("MongoDB registration has not completed")
    images_dir = flight_dir / "images"
    if not images_dir.is_dir():
        raise ValueError("Missing flight images")
    inventory = image_inventory(images_dir)
    if (flight_dir / "odm").exists() or (flight_dir / "odm-tmp").exists():
        raise ValueError("ODM directories already exist; refusing duplicate processing")
    for name in (SUBMITTING, SUBMITTED):
        if (flight_dir / name).exists():
            raise ValueError(f"ODM submission already has state {name}")
    return org, flight, request, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--sandbox", choices=("atlas", "ceres"), default="atlas")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--gres", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve(strict=True)
    repo = args.repo.expanduser().resolve(strict=True)
    job_script = repo / "scripts" / f"odm-{args.sandbox}-flight.sh"
    partition = args.partition or ("ceres" if args.sandbox == "ceres" else "gpu-a100")
    gres = args.gres if args.gres is not None else (None if args.sandbox == "ceres" else "gpu:a100:1")
    if args.sandbox == "ceres" and gres:
        parser.error("Ceres submission is CPU-only; --gres is not allowed")
    if not job_script.is_file():
        parser.error(f"ODM job script not found: {job_script}")
    id_root = root / "site-id"
    if not id_root.is_dir():
        parser.error(f"GUID storage directory not found: {id_root}")

    # A shared lock serializes concurrent submitter invocations.
    # The dry run intentionally does not create or modify anything.
    lock = None
    if not args.dry_run:
        lock = open(root / ".dpu-odm-submit.lock", "a+", encoding="utf-8")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another ODM submission process is already running")

    errors = 0
    try:
        pending = sorted(id_root.glob(f"*/flights/*/{PENDING}"))
        ambiguous = sorted(id_root.glob(f"*/flights/*/{SUBMITTING}"))
        print(f"Pending ODM submissions: {len(pending)}", flush=True)
        for stuck in ambiguous:
            errors += 1
            print(f"RECONCILE MANUALLY (no automatic retry): {stuck}",
                  file=sys.stderr, flush=True)

        for path in pending:
            try:
                org, flight, request, inventory = inspect(path)
                if args.dry_run:
                    print(
                        f"WOULD SUBMIT WITH CURRENT SETTINGS: {flight} "
                        f"({partition}, {gres or 'CPU only'}); "
                        f"images={inventory['image_count']}; "
                        f"image_bytes={inventory['total_image_bytes']}",
                        flush=True,
                    )
                    profile, reason = preview_resource_profile(args.sandbox, inventory)
                    print(
                        f"PROFILE PREVIEW ONLY (not applied): {flight}: "
                        f"{profile['name']} partition={profile['partition']} "
                        f"gres={profile['gres'] or 'none'} cpus={profile['cpus']} "
                        f"mem={profile['mem']} time={profile['time']}; "
                        f"reason={reason}",
                        flush=True,
                    )
                    continue
                submitting = path.with_name(SUBMITTING)
                submitted = path.with_name(SUBMITTED)
                # Before sbatch, consume the pending request. An interruption
                # here leaves .submitting for explicit human reconciliation.
                path.rename(submitting)
                command = [
                    "sbatch", "--parsable",
                    f"--partition={partition}",
                    f"--job-name=dpu-{flight}",
                    f"--chdir={path.parent}",
                    f"--output={path.parent}/odm-slurm-%j.out",
                    f"--error={path.parent}/odm-slurm-%j.err",
                    str(job_script), org, flight,
                ]
                if gres:
                    command.insert(3, f"--gres={gres}")
                # Keep MongoDB credentials out of the Slurm job environment.
                environment = {
                    key: value for key, value in os.environ.items()
                    if "MONGODB" not in key.upper() and key != "DPU_SECRETS_FILE"
                }
                result = subprocess.run(
                    command, cwd=repo, env=environment,
                    capture_output=True, text=True, check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"sbatch exited {result.returncode}: {result.stderr.strip()}"
                    )
                match = JOB_ID_PATTERN.fullmatch(result.stdout.strip())
                if match is None:
                    raise RuntimeError(f"Unexpected sbatch response: {result.stdout.strip()!r}")
                job_id = match.group(1)
                receipt = dict(request)
                receipt.update({
                    "image_inventory": inventory,
                    "slurm_job_id": job_id,
                    "partition": partition,
                    "gres": gres,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                })
                atomic_json(submitted, receipt)
                submitting.unlink()
                print(f"SUBMITTED: {flight} Slurm job {job_id}", flush=True)
            except Exception as exc:
                errors += 1
                print(f"FAILED: {path}: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)

        print(f"ODM submission errors: {errors}", flush=True)
        return 1 if errors else 0
    finally:
        if lock is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
