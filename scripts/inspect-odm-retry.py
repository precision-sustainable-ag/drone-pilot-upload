#!/usr/bin/env python3
"""Read-only status and artifact inspection for an operator-submitted ODM retry.

This does not update the original receipt, original accounting snapshot,
MongoDB, or flight products. Successful retry outputs are not promoted.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

RETRY_PREFIX = "odm-retry-from-"
PRODUCTS = {
    "orthophoto": "odm/code/odm_orthophoto/odm_orthophoto.tif",
    "vari": "odm/veg_indices/vari_image.tif",
    "gli": "odm/veg_indices/gli_image.tif",
}
TERMINAL_FAILURES = {
    "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL",
    "BOOT_FAIL", "PREEMPTED", "DEADLINE", "REVOKED",
}


def canonical_guid(value):
    if str(UUID(value)) != value:
        raise ValueError(f"Noncanonical flight ID: {value}")
    return value


def review_publication(flight_dir, attempt, sandbox, state, exit_code):
    """Read-only preflight. This never replaces the original ODM workspace."""
    blockers = []
    if state != "COMPLETED" or exit_code != "0:0":
        blockers.append(f"Retry Slurm job is not successful: {state} exit={exit_code}")
    for name, relative in PRODUCTS.items():
        product = attempt / relative
        if product.is_symlink() or not product.is_file() or product.stat().st_size == 0:
            blockers.append(f"Missing, empty, or symlinked retry {name}: {relative}")
    if sandbox == "ceres" and any(
        not (attempt / PRODUCTS[name]).is_file() for name in ("vari", "gli")
    ):
        blockers.append("Ceres indices require isolated postprocessing before publication")
    for name in ("odm", "odm-tmp"):
        old = flight_dir / name
        if old.exists() or old.is_symlink():
            blockers.append(f"Existing {name} must be archived, not overwritten")
    previews = flight_dir / "previews"
    if previews.exists() or previews.is_symlink():
        blockers.append("Existing previews must be preserved before regeneration")

    print("PUBLICATION REVIEW (read-only):", flush=True)
    for blocker in blockers:
        print(f"  BLOCKED: {blocker}", flush=True)
    if not blockers:
        print("  Preliminary file and state checks passed; "
              "GeoTIFF validity and publication still require operator review",
              flush=True)
    print("  No original files, receipts, previews, or MongoDB records changed.", flush=True)
    return not blockers


def inspect_retry(root, flight_id, previous_job_id, sandbox, publication_review=False):
    canonical_guid(flight_id)
    if not previous_job_id.isdigit():
        raise ValueError("Previous job ID must be numeric")

    pattern = f"*/flights/{flight_id}/{RETRY_PREFIX}{previous_job_id}.submitted.json"
    matches = list((root / "site-id").glob(pattern))
    if len(matches) != 1:
        raise ValueError("Expected exactly one submitted retry receipt; do not infer submission from .submitting")

    receipt_path = matches[0]
    flight_dir = receipt_path.parent
    org = str(UUID(flight_dir.parent.parent.name))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("flight_id") != flight_id or receipt.get("organization_id") != org or
            str(receipt.get("previous_slurm_job_id")) != previous_job_id):
        raise ValueError("Retry receipt does not match flight and original job")

    original = flight_dir / "odm-submission.submitted.json"
    original_receipt = json.loads(original.read_text(encoding="utf-8"))
    if (original_receipt.get("flight_id") != flight_id or
            original_receipt.get("organization_id") != org or
            str(original_receipt.get("slurm_job_id")) != previous_job_id):
        raise ValueError("Original submission receipt disagrees with retry history")

    retry_id = str(receipt.get("retry_slurm_job_id", ""))
    if not retry_id.isdigit():
        raise ValueError("Invalid retry Slurm job ID")
    attempt = flight_dir / "odm-retries" / f"retry-{previous_job_id}"
    if (Path(receipt.get("retry_workspace", "")) != attempt or
            attempt.is_symlink() or attempt.parent.is_symlink()):
        raise ValueError("Unsafe or mismatched retry workspace")

    cmd = [
        "sacct", "-n", "-P", "-j", retry_id,
        "-o", "JobIDRaw,State,ExitCode,Start,End,Partition,Elapsed,ReqMem,MaxRSS",
    ]
    result = subprocess.run(
        cmd, text=True, capture_output=True, check=False,
        env=dict(os.environ, TZ="UTC", SLURM_TIME_FORMAT="standard"),
    )
    if result.returncode:
        raise ValueError(f"Slurm accounting failed: {result.stderr.strip()}")
    rows = [line.split("|") for line in result.stdout.splitlines() if line.strip()]
    jobs = [r for r in rows if len(r) == 9 and r[0] == retry_id]
    if len(jobs) != 1:
        raise ValueError(f"Expected one Slurm accounting row for retry job {retry_id}")

    _, raw_state, exit_code, start, end, partition, elapsed, reqmem, _ = jobs[0]
    state = raw_state.split()[0].split("+")[0].upper()
    step_rss = {
        r[0]: r[8] for r in rows if len(r) == 9 and r[0].startswith(retry_id + ".")
        and r[8] and r[8] not in {"Unknown", "None"}
    }
    paths = PRODUCTS if sandbox == "atlas" else {"orthophoto": PRODUCTS["orthophoto"]}
    present = {
        name: (attempt / relative).is_file() and (attempt / relative).stat().st_size > 0
        for name, relative in paths.items()
    }

    print(f"RETRY: flight={flight_id} previous_job={previous_job_id} retry_job={retry_id}")
    print(f"  Slurm: state={state} exit={exit_code} partition={partition}")
    print(f"  Timing: started={start} ended={end} elapsed={elapsed}")
    print(f"  Memory: requested={reqmem or 'unavailable'} "
          f"MaxRSS_by_step={step_rss or 'unavailable'}")
    print(f"  Isolated products: {present}")
    if state == "COMPLETED" and exit_code == "0:0":
        if all(present.values()):
            if sandbox == "ceres":
                print("ODM ORTHOPHOTO READY: Ceres indices/previews need separate "
                      "processing in the isolated workspace")
            else:
                print("RETRY PRODUCTS READY: Atlas orthophoto and indices present")
        else:
            print("REVIEW REQUIRED: Slurm succeeded but expected retry products are missing")
    elif state in TERMINAL_FAILURES or state == "COMPLETED":
        print("RETRY FAILED: preserve attempt and records; no automatic resubmission")
    else:
        print("RETRY IN PROGRESS OR UNRESOLVED: no promotion or resubmission")
    print("Original receipt, original products and MongoDB remain unchanged.")
    if publication_review:
        return int(not review_publication(
            flight_dir, attempt, sandbox, state, exit_code
        ))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--flight-id", required=True)
    parser.add_argument("--previous-job-id", required=True)
    parser.add_argument("--sandbox", choices=("atlas", "ceres"), required=True)
    parser.add_argument("--review-publication", action="store_true",
                        help="Report blockers without altering original or retry outputs")
    args = parser.parse_args()
    try:
        root = args.data_root.expanduser().resolve(strict=True)
        return inspect_retry(root, args.flight_id, args.previous_job_id, args.sandbox,
                             args.review_publication)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
