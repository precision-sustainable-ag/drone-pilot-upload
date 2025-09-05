#!/usr/bin/env python3
"""
Reconcile flight records with on-disk artifacts.

- Verifies ODM (stage 1) completion from outputs/logs
- Verifies ortho_intel (stage 2) completion from outputs/logs
- Moves outputs out of ./code (finalize) if needed
- Updates Mongo per-stage fields and overall status

Usage:
  python reconcile_flights.py [--station central] [--limit 0] [--dry-run]

Requires:
  - services.db.connect_db() -> (client, collection)
  - config['mount_dir']  e.g. '/rs1/shares/cals-research-station'

"""

import argparse
import logging
import os
from datetime import datetime, timezone

from config import config
from services.artifacts import (
    finalize_outputs,
    odm_done,
    ortho_intel_done,
)
from services.db import connect_db
from services.fs import count_files, flight_dir_for

# services imports
from services.logs import setup_logging
from services.lsf_parse import lsf_terminal_status
from services.persistence import set_overall_status, set_stage
from services.status import recompute_overall, reconcile_state

# ---------- Filesystem helpers ----------


def utcnow():
    return datetime.now(timezone.utc)


# ---------- Reconcile one flight ----------


def reconcile_one(db, meta, dry_run=False, finalize=True):
    fid = meta["flight_id"]
    rs = meta["research_station"]
    fdir = flight_dir_for(meta)

    if not os.path.isdir(fdir):
        logging.warning("%s: flight directory not found: %s", fid, fdir)
        return

    images_dir = os.path.join(fdir, "images")
    actual = count_files(images_dir)
    expected = meta.get("num_files")
    if expected and actual != expected and meta.get("status") != "processed":
        msg = f"file count mismatch (expected {expected}, found {actual})"
        logging.error("%s: %s", fid, msg)
        set_stage(db, fid, "odm", {"state": "blocked", "message": msg}, dry_run)
        set_overall_status(fdir, fid, "file count mismatch", rs, dry_run)
        return  # skip further checks

    # Stage inspectors
    ok_odm, why_odm = odm_done(fdir)
    ok_oi, why_oi = ortho_intel_done(fdir)

    # Tail inspectors (terminal status only at the end of LSF logs)

    odm_out = os.path.join(fdir, "odm_processing-out.txt")
    odm_err = os.path.join(fdir, "odm_processing-err.txt")
    odm_tail_state, odm_tail_reason = lsf_terminal_status(odm_out, odm_err)

    oi_out = os.path.join(fdir, "ortho_intel-out.txt")
    oi_err = os.path.join(fdir, "ortho_intel-err.txt")
    oi_tail_state, oi_tail_reason = lsf_terminal_status(oi_out, oi_err)

    # Read current stage states (if any)
    stages = meta.get("stages", {})
    odm_state_prev = stages.get("odm", {}).get("state")
    oi_state_prev = stages.get("ortho_intel", {}).get("state")

    # Compute desired states using tail + artifacts (+ stickiness)
    odm_state, odm_reason = reconcile_state(
        prev=odm_state_prev,
        ok_by_artifacts=ok_odm,
        tail_state=odm_tail_state,
        tail_reason=odm_tail_reason,
    )
    oi_state, oi_reason = reconcile_state(
        prev=oi_state_prev,
        ok_by_artifacts=ok_oi,
        tail_state=oi_tail_state,
        tail_reason=oi_tail_reason,
    )

    # Finalize outputs only if ODM ended up succeeded
    if finalize and odm_state == "succeeded":
        finalize_outputs(fdir, dry_run=dry_run)

    now = utcnow()

    # Update per-stage (only if changed or missing)
    if odm_state != odm_state_prev:
        updates = (
            {"state": odm_state, "ended_at": now}
            if odm_state == "succeeded"
            else {"state": odm_state}
        )
        updates.setdefault("message", odm_reason or why_odm)
        set_stage(db, fid, "odm", updates, dry_run=dry_run)

    if oi_state != oi_state_prev:
        updates = (
            {"state": oi_state, "ended_at": now} if oi_state == "succeeded" else {"state": oi_state}
        )
        updates.setdefault("message", oi_reason or why_oi)
        set_stage(db, fid, "ortho_intel", updates, dry_run=dry_run)

    # Overall status
    overall_prev = meta.get("status")
    failed_now = (odm_tail_state == "failed") or (oi_tail_state == "failed")
    overall = recompute_overall(
        odm_state=odm_state,
        oi_state=oi_state,
        overall_prev=overall_prev,
        failed_now=failed_now,
    )

    if overall != overall_prev:
        set_overall_status(fdir, fid, overall, rs, dry_run)
        logging.info("%s: status %s -> %s", fid, overall_prev, overall)


# ---------- Main ----------


def main():
    ap = argparse.ArgumentParser(description="Reconcile flight records with real outputs")
    ap.add_argument("--station", help="Research station filter (e.g., central)", default=None)
    ap.add_argument("--limit", type=int, default=0, help="Max flights to process (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write to DB or move files")
    args = ap.parse_args()

    setup_logging(config["reconcile_log_file"])

    client, col = connect_db()

    q = {}
    if args.station:
        q["research_station"] = args.station

    # Prefer flights that are not yet fully processed or have missing stage info,
    # but default to scanning all matching flights.
    cursor = col.find(
        q, {"flight_id": 1, "research_station": 1, "status": 1, "stages": 1, "num_files": 1}
    )

    count = 0
    for meta in cursor:
        try:
            reconcile_one(col, meta, dry_run=args.dry_run, finalize=True)
            count += 1
            if args.limit and count >= args.limit:
                break
        except Exception as e:
            logging.exception("Error reconciling %s: %s", meta.get("flight_id"), e)

    logging.info(
        "Reconciled %d flights%s", count, f" (station={args.station})" if args.station else ""
    )


if __name__ == "__main__":
    main()
