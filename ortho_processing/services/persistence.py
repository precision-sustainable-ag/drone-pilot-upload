from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from services.db import connect_db
from services.geo import read_crs
from services.logs import get_logger

log = get_logger(__name__, component="persistence")


def utcnow():
    return datetime.now(timezone.utc)


def set_stage(db, fid: str, stage: str, updates: dict, dry_run: bool = False) -> None:
    path = f"stages.{stage}"
    payload = {f"{path}.{k}": v for k, v in updates.items()}
    if dry_run:
        return
    db.update_one({"flight_id": fid}, {"$set": payload})
    log.debug(
        {"event": "set_stage", "flight_id": fid, "stage": stage, "keys": sorted(updates.keys())}
    )


def stamp_stage(
    coll,
    fid: str,
    stage: str,
    *,
    job_id: int | None,
    run_id: str | None,
    ts: datetime | None = None,
    dry_run: bool = False,
) -> None:
    """
    Persist a submission for a stage and update the flight-level 'last_job'.
    Idempotent-friendly; does not create the flight record (no upsert).
    """
    stamp_ts = (ts or datetime.now(timezone.utc)).isoformat()

    # Per-stage metadata
    payload: dict[str, Any] = {
        "state": "queued" if job_id else "submit_failed",
        "job_id": job_id,
        "submitted_at": stamp_ts,
        "run_id": run_id,
    }
    set_stage(coll, fid, stage, payload, dry_run=dry_run)

    if dry_run:
        return

    # Flight-level "most recent job" pointer
    coll.update_one(
        {"flight_id": fid},
        {
            "$set": {
                "last_job": {
                    "stage": stage,
                    "job_id": job_id,
                    "submitted_at": stamp_ts,
                    "run_id": run_id,
                }
            }
        },
        upsert=False,
    )


def update_record(
    flight_dir: str, flight_id: str, status: str, research_station: str | None = None
):
    client, col = connect_db()
    q = {"flight_id": flight_id}
    update = {"$set": {"status": status}}

    if status in ("processed", "ortho generated") and research_station:
        crs = read_crs(flight_dir)
        ortho = os.path.join(
            research_station, "flights", flight_id, "odm_orthophoto", "odm_orthophoto.tif"
        )
        update["$set"].update({"orthophoto_path": ortho})
        if crs is not None:
            update["$set"]["orthophoto_source_crs"] = crs
        if status == "processed":
            update["$set"].update(
                {
                    "cog_path": os.path.join(
                        research_station,
                        "flights",
                        flight_id,
                        "odm_orthophoto",
                        "odm_orthophoto_cog.tif",
                    ),
                    "veg_index_folder": os.path.join(
                        research_station, "flights", flight_id, "veg_indices"
                    ),
                }
            )

    col.update_one(q, update, upsert=True)
    log.debug(
        {"event": "update_record", "flight_id": flight_id, "status": status, "rs": research_station}
    )


def set_overall_status(fdir: str, fid: str, status: str, rs: str, dry_run: bool = False) -> None:
    if dry_run:
        return
    # utils.updateRecord handles audit/logging for you
    update_record(fdir, fid, status, rs)
    log.info({"event": "overall_status_set", "flight_id": fid, "status": status, "station": rs})
