from datetime import datetime, timezone
import os
from config import config
import utils

def utcnow():
    return datetime.now(timezone.utc)

def flight_dir_for(meta) -> str:
    rs = meta["research_station"]
    fid = meta["flight_id"]
    return os.path.join(config["mount_dir"], rs, "flights", fid)

def set_stage(db, fid: str, stage: str, updates: dict, dry_run: bool=False) -> None:
    path = f"stages.{stage}"
    payload = {f"{path}.{k}": v for k, v in updates.items()}
    if dry_run:
        return
    db.update_one({"flight_id": fid}, {"$set": payload})

def set_overall_status(fdir: str, fid: str, status: str, rs: str, dry_run: bool=False) -> None:
    if dry_run:
        return
    # utils.updateRecord handles audit/logging for you
    utils.updateRecord(fdir, fid, status, rs)

def recompute_overall(odm_state: str, oi_state: str, overall_prev: str|None) -> str:
    if oi_state == "succeeded":
        return "processed"
    if odm_state == "succeeded" and oi_state != "failed":
        return "ortho generated"
    if overall_prev == "failed" and oi_state != "succeeded" and odm_state != "succeeded":
        return "failed"
    return overall_prev or "processing"
