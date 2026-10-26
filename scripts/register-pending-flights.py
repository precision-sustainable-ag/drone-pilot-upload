#!/usr/bin/env python3
"""Register queued Atlas sandbox flights in MongoDB (one-shot, idempotent).

Run from an authorized Atlas host with MongoDB connectivity using the
Drone Pilot Upload container's Python environment.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from bson import json_util
from pymongo import MongoClient

SANDBOX_DATABASE = "drone-pilot-atlas-sandbox"
SANDBOX_COLLECTION = "flight-information"
PENDING_NAME = "mongo-registration.pending.json"
DONE_NAME = "mongo-registration.done.json"
ODM_REQUEST_NAMES = (
    "odm-submission.pending.json",
    "odm-submission.submitting.json",
    "odm-submission.submitted.json",
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff"}


def canonical_guid(value):
    value = str(value)
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError(f"Noncanonical GUID: {value}")
    return normalized


def inspect_pending(path):
    # Expected: <data-root>/site-id/<org-guid>/flights/<flight-guid>/<file>
    flight_dir = path.parent
    if flight_dir.parent.name != "flights":
        raise ValueError("Unexpected flight directory layout")

    organization_id = canonical_guid(flight_dir.parent.parent.name)
    flight_id = canonical_guid(flight_dir.name)

    with path.open("r", encoding="utf-8") as stream:
        record = json_util.loads(stream.read())
    if not isinstance(record, dict):
        raise ValueError("Queued metadata is not a document")
    if record.get("flight_id") != flight_id:
        raise ValueError("Queued flight_id does not match its directory")
    if record.get("organization_id") != organization_id:
        raise ValueError("Queued organization_id does not match its directory")
    if "_id" in record:
        raise ValueError("Queued metadata unexpectedly contains an _id")

    count = record.get("num_files")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("Missing or invalid num_files")
    images_dir = flight_dir / "images"
    if not images_dir.is_dir():
        raise ValueError("Flight images directory is missing")
    actual = sum(
        1 for file in images_dir.iterdir()
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
    )
    if actual != count:
        raise ValueError(f"Image count mismatch: {actual} stored, {count} recorded")

    done = flight_dir / DONE_NAME
    if done.exists():
        raise ValueError("A completed registration file already exists")
    return record, done


def validate_existing(existing, expected):
    for field in ("flight_id", "organization_id", "num_files"):
        if existing.get(field) != expected.get(field):
            raise ValueError(f"Existing MongoDB record disagrees on {field}")


def queue_odm_submission(flight_dir, record):
    """Durably request one ODM job before marking registration complete.

    This function never submits a Slurm job. Submission happens on the
    login host using scripts/submit-pending-odm.py.
    """
    flight_id = record["flight_id"]
    organization_id = record["organization_id"]

    if (flight_dir / "odm").exists() or (flight_dir / "odm-tmp").exists():
        print(f"ODM OUTPUT EXISTS: {flight_id}; not queued", flush=True)
        return

    for name in ODM_REQUEST_NAMES:
        state_file = flight_dir / name
        if state_file.exists():
            existing = json.loads(state_file.read_text(encoding="utf-8"))
            if (existing.get("flight_id") != flight_id or
                    existing.get("organization_id") != organization_id):
                raise ValueError(f"Conflicting ODM submission state: {state_file}")
            print(f"ODM ALREADY QUEUED: {flight_id} ({name})", flush=True)
            return

    request = {
        "flight_id": flight_id,
        "organization_id": organization_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = flight_dir / ODM_REQUEST_NAMES[0]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=flight_dir,
            prefix=".odm-request-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(request, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(f"ODM QUEUED: {flight_id}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root", required=True, type=Path,
        help="Root containing site-id/<organization GUID>/flights/"
    )
    parser.add_argument("--id-dir", default="site-id", help="Organization GUID directory name")
    parser.add_argument("--dry-run", action="store_true", help="Inspect queue; do not connect to MongoDB")
    parser.add_argument("--queue-odm", action="store_true", help="Queue one ODM submission after each successful MongoDB registration")
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve(strict=True)
    if args.id_dir in ("", ".", "..") or "/" in args.id_dir or "\\" in args.id_dir:
        parser.error("--id-dir must be a single directory name")
    id_root = root / args.id_dir
    if not id_root.is_dir():
        parser.error(f"GUID storage directory is missing: {id_root}")

    pending_files = sorted(id_root.glob(f"*/flights/*/{PENDING_NAME}"))
    print(f"Pending registrations: {len(pending_files)}", flush=True)
    if not pending_files:
        return 0

    # Parse and validate the entire queue before connecting to MongoDB.
    valid = []
    errors = 0
    for path in pending_files:
        try:
            record, done = inspect_pending(path)
            valid.append((path, done, record))
            print(f"READY: {record['flight_id']} ({record['num_files']} images)", flush=True)
        except Exception as exc:
            errors += 1
            print(f"INVALID: {path}: {exc}", file=sys.stderr, flush=True)

    if args.dry_run:
        print("DRY RUN: no MongoDB operations or file renames performed", flush=True)
        return 1 if errors else 0
    if not valid:
        return 1

    # Refuse any database except the dedicated Atlas sandbox database.
    database = os.environ.get("DPU_MONGODB_DATABASE")
    collection_name = os.environ.get("DPU_MONGODB_COLLECTION")
    if database != SANDBOX_DATABASE or collection_name != SANDBOX_COLLECTION:
        parser.error("Refusing to write outside drone-pilot-atlas-sandbox.flight-information")
    uri = os.environ.get("DPU_MONGODB_CONNECTION_STRING")
    if not uri:
        parser.error("DPU_MONGODB_CONNECTION_STRING is missing")

    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        collection = client[database][collection_name]
        # Enforce idempotence even if the command is retried or run twice.
        collection.create_index(
            "flight_id", unique=True, sparse=True, name="dpu_flight_id_unique"
        )
        print("Sandbox flight_id unique index: READY", flush=True)

        registered = 0
        for pending, done, record in valid:
            flight_id = record["flight_id"]
            try:
                collection.update_one(
                    {"flight_id": flight_id},
                    {"$setOnInsert": record},
                    upsert=True,
                )
                existing = collection.find_one({"flight_id": flight_id})
                if existing is None:
                    raise RuntimeError("Record not found after upsert")
                validate_existing(existing, record)
                if args.queue_odm:
                    queue_odm_submission(pending.parent, record)
                pending.replace(done)  # Only after DB success and optional queue durability.
                registered += 1
                print(f"REGISTERED: {flight_id}", flush=True)
            except Exception as exc:
                errors += 1
                print(f"FAILED: {flight_id}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        print(f"Completed: {registered}; failed: {errors}", flush=True)
        return 1 if errors else 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())

