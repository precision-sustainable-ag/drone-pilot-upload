# services/lsf.py
from __future__ import annotations

import re
import subprocess

from services.logs import get_logger

JOB_ID_RE = re.compile(r"Job <(\d+)>")

# setup logging
log = get_logger(__name__, component="lsf")


def submit(lsf_script_path: str, cwd: str) -> int | None:
    """
    Run 'bsub < script' and return job id or None.
    Logs stderr details (closed queue, bad gpu, etc).
    """
    try:
        proc = subprocess.run(
            [f"bsub < {lsf_script_path}"], shell=True, capture_output=True, text=True, cwd=cwd
        )
        out, err = proc.stdout.strip(), proc.stderr.strip()

        # Common failures surface in stdout (LSF prints “Queue has been closed.” to stdout)
        if proc.returncode != 0 or "Job <" not in out:
            log.error(
                {
                    "event": "lsf_submit_error",
                    "cwd": cwd,
                    "script": lsf_script_path,
                    "stdout": out[:500],
                    "stderr": err[:500],
                }
            )
            # Helpful clues for callers
            return None

        m = JOB_ID_RE.search(out)
        if not m:
            log.error({"event": "lsf_submit_parse_error", "stdout": out[:500]})
            return None
        job_id = int(m.group(1))
        log.info(
            {
                "event": "lsf_submit_ok",
                "job_id": job_id,
                "queue_line": out.splitlines()[-1] if out else "",
            }
        )
        return job_id
    except Exception as e:
        log.error({"event": "lsf_submit_exception", "error": repr(e)})
        return None


def monitor(job_id: int) -> str | None:
    """
    Polls bjobs until job leaves RUN/PEND. Returns final LSF STAT string (e.g., DONE/EXIT) or None.
    """
    if not job_id:
        return None

    status = "PEND"
    try:
        while status in ("RUN", "PEND"):
            proc = subprocess.run(
                [f"bjobs -r {job_id}"], shell=True, capture_output=True, text=True
            )
            tokens = proc.stdout.split()
            # STAT column typically at index 10 in bjobs default format, but be defensive:
            status = next(
                (
                    t
                    for t in tokens
                    if t in ("RUN", "PEND", "DONE", "EXIT", "PSUSP", "USUSP", "SSUSP")
                ),
                status,
            )
            log.debug({"event": "lsf_poll", "job_id": job_id, "status": status})
        log.info({"event": "lsf_terminal", "job_id": job_id, "status": status})
        return status
    except Exception as e:
        log.error({"event": "lsf_monitor_exception", "job_id": job_id, "error": repr(e)})
        return None
