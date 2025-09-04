# services/lsf.py
from __future__ import annotations
from typing import Optional, Tuple
import subprocess
import logging
import re

JOB_ID_RE = re.compile(r'Job <(\d+)>')

def submit(lsf_script_path: str, cwd: str) -> Optional[int]:
    """
    Run 'bsub < script' and return job id or None.
    Logs stderr details (closed queue, bad gpu, etc).
    """
    try:
        proc = subprocess.run(
            [f"bsub < {lsf_script_path}"],
            shell=True, capture_output=True, text=True, cwd=cwd
        )
        out, err = proc.stdout.strip(), proc.stderr.strip()

        # Common failures surface in stdout (LSF prints “Queue has been closed.” to stdout)
        if proc.returncode != 0 or "Job <" not in out:
            logging.error({"service": "lsf submit job", "message": err or out})
            # Helpful clues for callers
            return None

        m = JOB_ID_RE.search(out)
        if not m:
            logging.error({"service": "lsf submit job", "message": f"Could not parse job id from: {out}"})
            return None
        return int(m.group(1))
    except Exception as e:
        logging.error({"service": "lsf submit job", "message": repr(e)})
        return None


def monitor(job_id: int) -> Optional[str]:
    """
    Polls bjobs until job leaves RUN/PEND. Returns final LSF STAT string (e.g., DONE/EXIT) or None.
    """
    if not job_id:
        return None

    status = "PEND"
    try:
        while status in ("RUN", "PEND"):
            proc = subprocess.run(
                [f"bjobs -r {job_id}"],
                shell=True, capture_output=True, text=True
            )
            tokens = proc.stdout.split()
            # STAT column typically at index 10 in bjobs default format, but be defensive:
            status = next((t for t in tokens if t in ("RUN","PEND","DONE","EXIT","PSUSP","USUSP","SSUSP")), status)
        return status
    except Exception as e:
        logging.error({"service": "lsf monitor job", "message": repr(e)})
        return None
