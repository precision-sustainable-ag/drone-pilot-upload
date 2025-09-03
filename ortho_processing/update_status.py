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
  - utils.connectDb() -> (client, collection)
  - config['mount_dir']  e.g. '/rs1/shares/cals-research-station'

"""
import argparse
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from glob import glob
import utils
from config import config


# ---------- Filesystem helpers ----------

def setup_logging(logfile="reconcile.log"):
    """Configure logging to both file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(logfile, mode="a"),
            logging.StreamHandler()
        ]
    )

def utcnow():
    return datetime.now(timezone.utc)

def count_files(path):
    """Count files under a directory (non-recursive)."""
    try:
        return sum(1 for _ in os.scandir(path) if _.is_file())
    except FileNotFoundError:
        return 0

def exists_nonempty(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def dir_exists_nonempty(path):
    try:
        return os.path.isdir(path) and any(os.scandir(path))
    except OSError:
        return False


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def flight_dir_for(meta):
    """Resolve flight directory from metadata."""
    rs = meta["research_station"]
    fid = meta["flight_id"]
    return os.path.join(config["mount_dir"], rs, "flights", fid)


def safe_move_tree(src, dst):
    """Move src -> dst (rename if same FS; fallback to copy+remove)."""
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)


# ---------- Stage checks ----------

def has_orthophoto(fdir):
    """
    Return path to orthophoto if present, searching both final and in-place locations.
    Priority: ./odm_orthophoto/odm_orthophoto.tif then ./code/odm_orthophoto/odm_orthophoto.tif
    """
    p1 = os.path.join(fdir, "odm_orthophoto", "odm_orthophoto.tif")
    p2 = os.path.join(fdir, "code", "odm_orthophoto", "odm_orthophoto.tif")
    if exists_nonempty(p1):
        return p1
    if exists_nonempty(p2):
        return p2
    return None


def odm_done(fdir):
    """
    Heuristics to confirm ODM success:
      - log.json with {"success": true} in ./code or root
      - OR presence of an orthophoto.tif (final or under ./code)
    Returns (bool, reason_string)
    """
    # Prefer log.json truth if available
    for candidate in (
        os.path.join(fdir, "code", "log.json"),
        os.path.join(fdir, "log.json"),
    ):
        j = load_json(candidate)
        if isinstance(j, dict) and j.get("success") is True:
            return True, f"log.json success=true ({os.path.relpath(candidate, fdir)})"

    # Fall back to artifact existence
    ortho = has_orthophoto(fdir)
    if ortho:
        return True, f"orthophoto present ({os.path.relpath(ortho, fdir)})"
    return False, "no success markers (log.json) and no orthophoto"


def ortho_intel_done(fdir):
    """
    Confirm ortho_intel completion by artifacts:
      - COG: odm_orthophoto_cog.tif
      - veg_indices directory contains at least one file (NDVI/LAI/etc.)
    Returns (bool, reason_string)
    """
    cog = os.path.join(fdir, "odm_orthophoto", "odm_orthophoto_cog.tif")
    veg_dir = os.path.join(fdir, "veg_indices")
    if exists_nonempty(cog) and dir_exists_nonempty(veg_dir):
        return True, "COG + veg_indices"
    if exists_nonempty(cog):
        return True, "COG present"
    if dir_exists_nonempty(veg_dir):
        return True, "veg_indices present"
    return False, "no ortho_intel artifacts"


# ---------- Finalization ----------

def finalize_outputs(fdir, dry_run=False):
    """
    If outputs live under ./code/*, move them to the flight root:
      - move everything from ./code except 'images' into flight root
      - preserve existing targets (skip overwrite) to be safe
    """
    code_dir = os.path.join(fdir, "code")
    if not os.path.isdir(code_dir):
        return

    for item in os.listdir(code_dir):
        if item == "images":
            continue
        src = os.path.join(code_dir, item)
        dst = os.path.join(fdir, item)
        if os.path.exists(dst):
            # If destination already exists, skip to avoid clobbering
            logging.debug("finalize: destination exists, skipping %s", os.path.relpath(dst, fdir))
            continue
        logging.info("finalize: moving %s -> %s", os.path.relpath(src, fdir), os.path.relpath(dst, fdir))
        if not dry_run:
            safe_move_tree(src, dst)

    # Remove ./code if it only contains images (or is empty)
    try:
        residual = [x.name for x in os.scandir(code_dir) if x.name != "images"]
        if not residual:
            logging.info("finalize: removing empty code dir")
            if not dry_run:
                shutil.rmtree(code_dir, ignore_errors=True)
    except FileNotFoundError:
        pass


# ---------- Mongo update helpers ----------

def set_stage(db, fid, stage, updates, dry_run=False):
    path = f"stages.{stage}"
    payload = {f"{path}.{k}": v for k, v in updates.items()}
    if dry_run:
        logging.info("[dry-run] DB set %s: %s", fid, payload)
        return
    db.update_one({"flight_id": fid}, {"$set": payload})


def set_overall_status(db, fid, status, dry_run=False):
    if dry_run:
        logging.info("[dry-run] DB set %s: status=%s", fid, status)
        return
    db.update_one({"flight_id": fid}, {"$set": {"status": status}})


def recompute_overall(odm_state, oi_state):
    """
    Roll-up overall status from per-stage states.
    """
    if oi_state == "succeeded":
        return "processed"
    if odm_state == "succeeded":
        return "ortho generated"
    if odm_state in ("pending", "processing") or oi_state in ("pending", "processing"):
        return "processing"
    if odm_state == "failed" or oi_state == "failed":
        return "failed"
    return "processing"


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
    if expected and actual != expected:
        msg = f"file count mismatch (expected {expected}, found {actual})"
        logging.error("%s: %s", fid, msg)
        set_stage(db, fid, "odm", {"state": "blocked", "message": msg}, dry_run)
        set_overall_status(db, fid, "file count mismatch", dry_run)
        return  # skip further checks

    # Stage inspectors
    ok_odm, why_odm = odm_done(fdir)
    ok_oi,  why_oi  = ortho_intel_done(fdir)

    # Finalize outputs if ODM is done and stuff still under ./code
    if ok_odm and finalize:
        finalize_outputs(fdir, dry_run=dry_run)

    # Read current stage states (if any)
    stages = meta.get("stages", {})
    odm_state_prev = stages.get("odm", {}).get("state")
    oi_state_prev  = stages.get("ortho_intel", {}).get("state")

    # Compute desired states
    odm_state = "succeeded" if ok_odm else ("processing" if odm_state_prev in ("pending", "processing") else "unknown")
    oi_state  = "succeeded" if ok_oi  else ("processing" if oi_state_prev  in ("pending", "processing") else "unknown")

    now = utcnow()

    # Update per-stage (only if changed or missing)
    if odm_state != odm_state_prev:
        updates = {"state": odm_state, "ended_at": now} if odm_state == "succeeded" else {"state": odm_state}
        updates.setdefault("message", why_odm)
        set_stage(db, fid, "odm", updates, dry_run=dry_run)

    if oi_state != oi_state_prev:
        updates = {"state": oi_state, "ended_at": now} if oi_state == "succeeded" else {"state": oi_state}
        updates.setdefault("message", why_oi)
        set_stage(db, fid, "ortho_intel", updates, dry_run=dry_run)

    # Overall status
    overall_prev = meta.get("status")
    overall = recompute_overall(odm_state, oi_state)
    if overall != overall_prev:
        set_overall_status(db, fid, overall, dry_run=dry_run)
        logging.info("%s: status %s -> %s", fid, overall_prev, overall)

    # Bonus: attach artifact pointers (lightweight)
    artifacts = {}
    ortho = has_orthophoto(fdir)
    if ortho:
        artifacts["orthophoto"] = ortho
    cog = os.path.join(fdir, "odm_orthophoto", "odm_orthophoto_cog.tif")
    if exists_nonempty(cog):
        artifacts["orthophoto_cog"] = cog
    veg_dir = os.path.join(fdir, "veg_indices")
    if dir_exists_nonempty(veg_dir):
        artifacts["veg_indices_dir"] = veg_dir
    if artifacts:
        if not dry_run:
            db.update_one({"flight_id": fid}, {"$set": {"artifacts": artifacts}})
        else:
            logging.info("[dry-run] DB set %s: artifacts=%s", fid, artifacts)


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Reconcile flight records with real outputs")
    ap.add_argument("--station", help="Research station filter (e.g., central)", default=None)
    ap.add_argument("--limit", type=int, default=0, help="Max flights to process (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write to DB or move files")
    ap.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING)")
    args = ap.parse_args()

    setup_logging()

    client, col = utils.connectDb()

    col.update_many({"research_station":"sandhills","status":"processing"},{"$set":{"status":"failed"}})

if __name__ == "__main__":
    main()
