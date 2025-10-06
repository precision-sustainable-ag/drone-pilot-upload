from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from datetime import datetime, timezone

from config import config

from services.logs import get_logger

# setup logs
log = get_logger(__name__, component="fs")


def count_files(path: str) -> int:
    try:
        return sum(1 for e in os.scandir(path) if e.is_file())
    except FileNotFoundError:
        return 0


def exists_nonempty(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def dir_exists_nonempty(path: str) -> bool:
    try:
        return os.path.isdir(path) and any(os.scandir(path))
    except OSError:
        return False


def safe_move_tree(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)


def flight_dir_for(meta):
    """Resolve flight directory from metadata."""
    rs = meta["research_station"]
    fid = meta["flight_id"]
    return os.path.join(config["mount_dir"], rs, "flights", fid)


def purge_code_dir(
    flight_dir: str, *, flight_id: str | None = None, run_id: str | None = None
) -> bool:
    """
    Delete <flight_dir>/code if it exists.
    Returns True if a directory was removed, False if it didn't exist or on failure.
    """
    code_dir = os.path.join(flight_dir, "code")
    try:
        if os.path.isdir(code_dir):
            shutil.rmtree(code_dir)
            log.info(
                {
                    "event": "purge_code_dir",
                    "flight_id": flight_id,
                    "run_id": run_id,
                    "path": code_dir,
                }
            )
            return True
        log.debug(
            {
                "event": "purge_code_dir_skip",
                "flight_id": flight_id,
                "run_id": run_id,
                "reason": "not_found",
                "path": code_dir,
            }
        )
        return False
    except Exception as e:
        log.exception(
            "purge_code_dir_exception",
            extra={
                "event": "purge_code_dir_exception",
                "flight_id": flight_id,
                "run_id": run_id,
                "path": code_dir,
                "error": repr(e),
            },
        )
        return False


def latest_mtime(paths: Iterable[str]) -> datetime | None:
    """
    Return the latest modification time among the given file paths, or None if none exist.
    Returns a timezone aware datetime in UTC
    """
    latest: datetime | None = None
    for p in paths:
        if os.path.isfile(p):
            ts = os.path.getmtime(p)
            t = datetime.fromtimestamp(ts, tz=timezone.utc)
            latest = t if latest is None or t > latest else latest
    return latest


def tail_mtime_for_stage(fdir: str, stage: str) -> datetime | None:
    """
    Convenience wrapper: return latest mtime of expected tail files for a stage.
    """
    names = (
        ("odm_processing-out.txt", "odm_processing-err.txt")
        if stage == "odm"
        else ("ortho_intel_processing-out.txt", "ortho_intel_processing-err.txt")
    )
    return latest_mtime(os.path.join(fdir, n) for n in names)


def parse_iso(value: str | None) -> datetime | None:
    """
    Parse an ISO8601 string or datetime to a timezone-aware UTC datetime.
    Returns None if value is falsy or unparsable.
    """
    if not value:
        return None
    # Already a datetime object
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)

    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo:
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
