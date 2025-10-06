"""
Aimed as the orchestrator to send jobs using the DTN - trigger point
Jobs are sent using generate_ortho.sh
"""

from __future__ import annotations

import argparse
import concurrent.futures
import itertools
import logging
import multiprocessing
import os
import uuid
from datetime import datetime, timedelta

from config import config
from reconcile_flights import reconcile_one
from services.db import connect_db
from services.fs import count_files
from services.logs import get_logger, setup_logging
from services.persistence import update_record
from services.pipeline import write_and_run_odm, write_and_run_ortho_intel

# setup logging
log = get_logger(__name__, component="cron")

# ---------- main per-flight logic ----------


def process_flight(flight_id, db_collection=None, run_id: str | None = None):
    # allow single-flight testing without main(): connect if not provided
    if db_collection is None:
        _, db_collection = connect_db()

    meta = db_collection.find_one({"flight_id": flight_id})
    if not meta:
        log.error({"event": "missing_db_record", "flight_id": flight_id, "run_id": run_id})
        return None

    # targeted reconcile first (freshen stage/overall; moves outputs if ODM done)
    try:
        reconcile_one(db_collection, meta, dry_run=False, finalize=True)
        # refresh after reconcile
        meta = db_collection.find_one({"flight_id": flight_id}) or meta
    except Exception as e:
        log.exception(
            "reconcile_before_processing_failed",
            extra={
                "event": "reconcile_exception",
                "flight_id": flight_id,
                "run_id": run_id,
                "error": repr(e),
            },
        )

    research_station = meta["research_station"]
    status = meta.get("status")
    flight_dir = os.path.join(config["mount_dir"], research_station, "flights", flight_id)
    stages = meta.get("stages") or {}
    odm_state = (stages.get("odm") or {}).get("state")

    # image count must match
    images_dir = os.path.join(flight_dir, "images")
    if meta["num_files"] != count_files(images_dir):
        log.info(
            {
                "event": "skip_file_count_mismatch",
                "flight_id": flight_id,
                "run_id": run_id,
                "expected": meta["num_files"],
                "found": count_files(images_dir),
            }
        )
        return None

    # if already "ortho generated", odm succeeded but ortho intel failed,
    # skip ODM and run ONLY ortho_intel
    if status == "ortho generated" or (status == "failed" and odm_state == "succeeded"):
        reason = (
            "status=ortho generated, skipping ODM"
            if status == "ortho generated"
            else "retry: overall=failed but odm=succeeded; running ortho_intel only"
        )
        log.info(
            {
                "event": "skip_odm_run_ortho_intel",
                "flight_id": flight_id,
                "run_id": run_id,
                "extra": reason,
            }
        )
        update_record(flight_dir, flight_id, "processing")
        if write_and_run_ortho_intel(flight_dir, flight_id):
            update_record(flight_dir, flight_id, "processed", research_station)
            return flight_id
        else:
            update_record(flight_dir, flight_id, "failed")
            log.error({"event": "ortho_intel_failed", "flight_id": flight_id, "run_id": run_id})
            return None

    # default path: run ODM then ortho_intel
    update_record(flight_dir, flight_id, "processing")
    log.info({"event": "odm_start", "flight_id": flight_id, "run_id": run_id})

    if not write_and_run_odm(flight_dir, flight_id):
        update_record(flight_dir, flight_id, "failed")
        log.error({"event": "odm_failed", "flight_id": flight_id, "run_id": run_id})
        return None

    update_record(flight_dir, flight_id, "ortho generated")
    log.info({"event": "odm_done", "flight_id": flight_id, "run_id": run_id})

    log.info({"event": "ortho_intel_start", "flight_id": flight_id, "run_id": run_id})
    if write_and_run_ortho_intel(flight_dir, flight_id):
        update_record(flight_dir, flight_id, "processed", research_station)
        log.info({"event": "processed", "flight_id": flight_id, "run_id": run_id})
        return flight_id
    else:
        update_record(flight_dir, flight_id, "failed")
        log.error({"event": "ortho_intel_failed", "flight_id": flight_id, "run_id": run_id})
        return None


def main():
    # argument for running one station at a time
    ap = argparse.ArgumentParser(description="Run ODM/Ortho-Intel jobs for eligible flights")
    ap.add_argument("--station", default="central", help="Research station filter (e.g., central)")
    ap.add_argument("--limit", default=None, help="How many flights to process")
    ap.add_argument(
        "--max-workers", type=int, default=multiprocessing.cpu_count(), help="Thread pool size"
    )
    args = ap.parse_args()

    # setup loigging from config file
    setup_logging()
    run_id = str(uuid.uuid4())

    # use global db collection
    client, db_collection = connect_db()

    # gets all flights uploaded yesterday (and earlier) for central
    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday = datetime.combine(yesterday, datetime.min.time())

    query = {"upload_time": {"$lt": yesterday}, "research_station": args.station}
    results = db_collection.find(query)

    index = 0
    records_to_process = []
    for row in results:
        # always allow 'ortho generated' so we can finish them
        if "status" not in row:
            records_to_process.append(row["flight_id"])
            index += 1
        elif row["status"] in ["processed", "processing", "file count mismatch"]:
            # skip already processed and currently-running
            continue
        else:
            # includes: ortho generated, failed, unknown, etc.
            records_to_process.append(row["flight_id"])
            index += 1

        # break once limit number of flights have been processed
        if args.limit and index >= int(args.limit):
            break

    if records_to_process:
        log.info(
            {
                "event": "dispatch_batch",
                "station": args.station,
                "run_id": run_id,
                "count": len(records_to_process),
                "flight_ids": records_to_process,
            }
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            executor.map(
                process_flight,
                records_to_process,
                itertools.repeat(db_collection),
                itertools.repeat(run_id),
            )
    else:
        logging.info({"service": "database query", "message": "no records"})


if __name__ == "__main__":
    main()
