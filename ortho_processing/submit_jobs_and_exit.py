"""
Orchestrator: submit ODM / Ortho-Intel jobs and exit.
- Reconciles each flight first to refresh stage/overall and move any finished outputs.
- Submits only the necessary stage(s); does NOT poll or wait.
- Records job_id and 'queued' state in stage metadata.
- Also records the most recent job in top-level 'last_job'.
- Never downgrades from 'ortho generated' here; reconciliation logic handles
  promotions/demotions after jobs complete.
"""

from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timedelta

from config import config
from reconcile_flights import reconcile_one
from services.db import connect_db
from services.fs import count_files, purge_code_dir
from services.logs import get_logger, setup_logging
from services.lsf import submit
from services.persistence import stamp_stage, update_record
from services.scripts import write_odm_script, write_ortho_intel_script

# Structured logger
log = get_logger(__name__, component="cron")


def process_flight(
    flight_id: str,
    db_collection=None,
    run_id: str | None = None,
) -> str | None:
    """Submit the needed job(s) for a flight and return the flight_id (or None on skip)."""
    # Allow single-flight testing without main(): connect if not provided
    if db_collection is None:
        _, db_collection = connect_db()

    meta = db_collection.find_one({"flight_id": flight_id})
    if not meta:
        log.error({"event": "missing_db_record", "flight_id": flight_id, "run_id": run_id})
        return None

    # Reconcile first (refresh stage/overall; move outputs if needed)
    try:
        reconcile_one(db_collection, meta, dry_run=False, finalize=True)
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
    stages = meta.get("stages") or {}
    odm_state = (stages.get("odm") or {}).get("state")

    flight_dir = os.path.join(config["mount_dir"], research_station, "flights", flight_id)
    images_dir = os.path.join(flight_dir, "images")
    panels_dir = os.path.join(flight_dir, "panels")

    # Sanity: image count must match expected
    images_count = count_files(images_dir)
    panels_count = count_files(panels_dir)
    if meta["num_files"] != (panels_count + images_count):
        log.info(
            {
                "event": "skip_file_count_mismatch",
                "flight_id": flight_id,
                "run_id": run_id,
                "expected": meta["num_files"],
                "images count": images_count,
                "panels count": panels_count,
            }
        )
        # Optional: mark overall so cron skips it next time until fixed
        update_record(flight_dir, flight_id, "file count mismatch", research_station)
        return None

    # If overall status is 'failed', clear stale intermediates to ensure a clean re-run

    if status == "failed":
        purge_code_dir(flight_dir, flight_id=flight_id, run_id=run_id)

    # If ODM already succeeded, submit ONLY Ortho-Intel.
    if status == "ortho generated" or (status == "failed" and odm_state == "succeeded"):
        reason = (
            "status=ortho generated, skipping ODM"
            if status == "ortho generated"
            else "retry: overall=failed but odm=succeeded; submitting ortho_intel only"
        )
        log.info(
            {
                "event": "skip_odm_submit_ortho_intel",
                "flight_id": flight_id,
                "run_id": run_id,
                "reason": reason,
            }
        )

        # If overall was 'failed' but ODM is done, normalize overall to 'ortho generated'
        # so future logic won't demote it again.
        if status == "failed":
            update_record(flight_dir, flight_id, "ortho generated", research_station)

        # mark record as processing
        update_record(flight_dir, flight_id, "processing", research_station)

        # Prepare and submit Ortho-Intel (no polling)
        oi_script = os.path.join(flight_dir, "ortho_intel_lsf.sh")
        ortho_file = os.path.join(flight_dir, "odm_orthophoto", "odm_orthophoto.tif")
        write_ortho_intel_script(
            flight_dir=flight_dir,
            ortho_file=ortho_file,
            script_path=oi_script,
        )
        job_id = submit(oi_script, flight_dir)
        stamp_stage(db_collection, flight_id, "ortho_intel", job_id=job_id, run_id=run_id)
        log.info(
            {
                "event": "ortho_intel_submitted",
                "flight_id": flight_id,
                "run_id": run_id,
                "job_id": job_id,
            }
        )
        return flight_id

    # Default path: submit ODM only; reconciler will submit OI upon ODM success.
    update_record(flight_dir, flight_id, "processing", research_station)
    odm_script = os.path.join(flight_dir, "odm_lsf.sh")
    write_odm_script(
        flight_dir=flight_dir,
        images_dir=images_dir,
        script_path=odm_script,
    )
    job_id = submit(odm_script, flight_dir)
    stamp_stage(db_collection, flight_id, "odm", job_id=job_id, run_id=run_id)
    log.info(
        {
            "event": "odm_submitted",
            "flight_id": flight_id,
            "run_id": run_id,
            "job_id": job_id,
        }
    )
    return flight_id


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Submit ODM/Ortho-Intel jobs for eligible flights and exit"
    )
    ap.add_argument(
        "--station",
        default="central",
        help="Research station filter (e.g., central)",
    )
    ap.add_argument(
        "--limit",
        default=None,
        help="Max number of flights to submit this run",
    )
    args = ap.parse_args()

    # Configure logging
    setup_logging()
    run_id = str(uuid.uuid4())

    # Use global DB collection
    _, db_collection = connect_db()

    # Get all flights uploaded yesterday (and earlier) for the station
    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday = datetime.combine(yesterday, datetime.min.time())

    query = (
        {"upload_time": {"$lt": yesterday}, "research_station": args.station}
        if args.station
        else {"upload_time": {"$lt": yesterday}}
    )
    results = db_collection.find(query)

    records_to_process: list[str] = []
    for row in results:
        # Always allow 'ortho generated' so we can finish them
        if "status" not in row:
            records_to_process.append(row["flight_id"])
        elif row["status"] in ["processed", "processing"]:
            # Skip already processed, currently-running, or known-bad counts
            continue
        else:
            # Includes: ortho generated, failed, unknown, etc.
            records_to_process.append(row["flight_id"])

        if args.limit and len(records_to_process) >= int(args.limit):
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
        # Submit serially; the scheduler handles parallelism.
        for fid in records_to_process:
            try:
                process_flight(fid, db_collection=db_collection, run_id=run_id)
            except Exception as e:
                log.exception(
                    "submit_exception",
                    extra={"flight_id": fid, "run_id": run_id, "error": repr(e)},
                )
    else:
        log.info({"event": "dispatch_batch", "station": args.station, "run_id": run_id, "count": 0})


if __name__ == "__main__":
    main()
