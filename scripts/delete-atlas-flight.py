#!/usr/bin/env python3
"""Preview or delete one Atlas sandbox flight from MongoDB and project storage.

Run only through delete-atlas-flight.sh, on an authorized Atlas login host.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from uuid import UUID

from pymongo import MongoClient

DB = "drone-pilot-atlas-sandbox"
COLLECTION = "flight-information"


def canonical_uuid(value):
    value = str(value)
    if str(UUID(value)) != value:
        raise ValueError("flight/organization GUID must be canonical lowercase UUID")
    return value


def locate_flight(root, flight_id):
    # Never traverse site-name: it deliberately contains organization symlinks.
    id_root = root / "site-id"
    if not id_root.is_dir() or id_root.is_symlink():
        raise RuntimeError(f"Missing or symlinked site-id directory: {id_root}")

    matches = []
    for org_dir in id_root.iterdir():
        if org_dir.is_symlink() or not org_dir.is_dir():
            continue
        try:
            organization_id = canonical_uuid(org_dir.name)
        except ValueError:
            continue
        flights = org_dir / "flights"
        if flights.is_symlink() or not flights.is_dir():
            continue
        flight_dir = flights / flight_id
        if flight_dir.is_symlink():
            raise RuntimeError(f"Refusing symlinked flight directory: {flight_dir}")
        if flight_dir.is_dir():
            matches.append((organization_id, flight_dir))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one flight directory; found {len(matches)}")
    org, directory = matches[0]
    if directory.resolve(strict=True) != directory:
        raise RuntimeError("Flight directory resolves outside canonical storage path")
    return org, directory


def check_receipts(folder, org, flight):
    # An in-flight submission is ambiguous: it may have submitted a job but
    # not yet written the Slurm job ID. Deletion must refuse this state.
    if (folder / "odm-submission.submitting.json").exists():
        raise RuntimeError("Ambiguous .submitting state: reconcile Slurm before deleting")
    for name in (
        "mongo-registration.pending.json", "mongo-registration.done.json",
        "odm-submission.pending.json", "odm-submission.submitted.json",
    ):
        path = folder / name
        if not path.exists():
            continue
        try:
            from bson import json_util
            record = json_util.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Cannot validate {name}: {exc}") from exc
        if record.get("flight_id") != flight or record.get("organization_id") != org:
            raise RuntimeError(f"Identity mismatch in {name}")
    receipt = folder / "odm-submission.submitted.json"
    if receipt.is_file():
        data = json.loads(receipt.read_text(encoding="utf-8"))
        job_id = str(data.get("slurm_job_id", ""))
        if not job_id.isdecimal():
            raise RuntimeError("Invalid Slurm job ID in submission receipt")
        return job_id
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--flight-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    flight_id = canonical_uuid(args.flight_id)
    root = args.data_root.expanduser().resolve(strict=True)
    org, folder = locate_flight(root, flight_id)
    job_id = check_receipts(folder, org, flight_id)

    if os.environ.get("DPU_MONGODB_DATABASE") != DB or os.environ.get("DPU_MONGODB_COLLECTION") != COLLECTION:
        parser.error("Refusing to access any database except the Atlas sandbox collection")
    uri = os.environ.get("DPU_MONGODB_CONNECTION_STRING")
    if not uri:
        parser.error("Missing MongoDB connection string")

    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        collection = client[DB][COLLECTION]
        records = list(collection.find({"flight_id": flight_id}).limit(2))
        if len(records) > 1:
            raise RuntimeError("Multiple MongoDB documents have this flight ID; refusing deletion")
        record = records[0] if records else None
        if record is not None and record.get("organization_id") != org:
            raise RuntimeError("MongoDB organization_id disagrees with filesystem")
        db_state = "present" if record else "absent"
        print(f"Flight:   {flight_id}")
        print(f"Org:      {org}")
        print(f"Folder:   {folder}")
        print(f"Job:      {job_id or 'none recorded'}")
        print(f"MongoDB:  {DB}.{COLLECTION}: {db_state}")
        if record:
            print(f"Status:   {record.get('status', 'not set')}")
        if not args.execute:
            if args.preview:
                print("PREVIEW: Resources listed above will be deleted after confirmation.")
            else:
                print("DRY RUN: No MongoDB documents or files deleted.")
            return 0

        # Stage data on the same filesystem before the database operation.
        # On DB failure, restore the original directory. After DB deletion,
        # a removal error leaves a named tombstone for explicit recovery.
        tombstone = folder.with_name(f".deleting-{flight_id}")
        if tombstone.exists() or tombstone.is_symlink():
            raise RuntimeError(f"Existing deletion tombstone requires inspection: {tombstone}")
        folder.rename(tombstone)
        db_deleted = False
        try:
            if record:
                result = collection.delete_one({
                    "_id": record["_id"],
                    "flight_id": flight_id,
                    "organization_id": org,
                })
                if result.deleted_count != 1:
                    raise RuntimeError("MongoDB document was not deleted (record changed?)")
                db_deleted = True
        except Exception:
            tombstone.rename(folder)
            raise
        try:
            shutil.rmtree(tombstone)
        except Exception as exc:
            raise RuntimeError(
                f"MongoDB deletion completed ({int(db_deleted)} document); "
                f"filesystem cleanup incomplete at {tombstone}: {exc}"
            ) from exc
        print(f"DELETED: {flight_id} (MongoDB documents: {int(db_deleted)}; flight directory removed)")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
