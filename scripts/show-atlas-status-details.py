#!/usr/bin/env python3
"""Show an Atlas ODM job and its logs within one terminal screen.

The submission receipt is the authoritative job-to-flight mapping. Read-only;
no MongoDB access or Slurm job modification. Fits ordinary ``watch`` screens,
reserving two rows for watch's own heading.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

DEFAULT_DATA_ROOT = Path("/project/dash_drone/user/stephen.amerige/dpu-data")
RECEIPT = "odm-submission.submitted.json"
MAX_LINES = 80
WATCH_ROWS = 2
ANSI_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def submitted_flights(root):
    for path in (root / "site-id").glob(f"*/flights/*/{RECEIPT}"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            job_id = str(record["slurm_job_id"])
            if not re.fullmatch(r"[0-9]+", job_id):
                continue
            if record.get("flight_id") != path.parent.name:
                continue
            yield path, record
        except (OSError, KeyError, TypeError, ValueError):
            continue


def dimensions():
    """Get real terminal dimensions even when watch pipes our stdout."""
    size = shutil.get_terminal_size(fallback=(100, 24))
    columns, rows = size.columns, size.lines
    try:
        fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
        try:
            size = os.get_terminal_size(fd)
            if size.columns and size.lines:
                columns, rows = size.columns, size.lines
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass

    # Explicit overrides are useful for batch sessions and testing.
    for key, current in (("DPU_STATUS_COLUMNS", columns),
                         ("DPU_STATUS_ROWS", rows)):
        candidate = os.environ.get(key, "")
        if candidate.isdecimal() and int(candidate) > 0:
            if key.endswith("COLUMNS"):
                columns = int(candidate)
            else:
                rows = int(candidate)
    return max(1, columns), max(1, rows)


def clean(line):
    """Ensure a log line cannot move the cursor or introduce a newline."""
    line = ANSI_SEQUENCE.sub("", line.rstrip("\r\n")).expandtabs(4)
    return "".join(ch if ch.isprintable() else " " for ch in line)


def fit(line, columns):
    """Keep each displayed line narrower than the terminal to avoid wrapping."""
    return clean(line)[:max(1, columns - 1)]


def fit_folder(path, columns):
    """Preserve the useful end of a long flight path when space is tight."""
    prefix = "Folder: "
    value = str(path)
    allowance = max(1, columns - len(prefix) - 1)
    if len(value) > allowance:
        value = "..."[:allowance] if allowance <= 3 else "..." + value[-(allowance - 3):]
    return fit(prefix + value, columns)


def slurm_status(job_id):
    lines = ["Slurm:"]
    try:
        queue = subprocess.run(
            ["squeue", "-h", "-j", job_id,
             "-o", "%.18i %.9P %.8T %.10M %.10L %.10l %.6D %R"],
            text=True, capture_output=True, check=False,
        )
        if queue.returncode == 0 and queue.stdout.strip():
            return lines + [
                "JOBID              PARTITION STATE    ELAPSED    LEFT       LIMIT      NODES REASON",
                queue.stdout.splitlines()[0],
            ]
        if queue.returncode != 0:
            lines.append(f"  squeue: {queue.stderr.strip() or 'query failed'}")
        accounting = subprocess.run(
            ["sacct", "-X", "-j", job_id,
             "--format=JobID,State,ExitCode,Elapsed"],
            text=True, capture_output=True, check=False,
        )
        if accounting.returncode == 0 and accounting.stdout.strip():
            # One allocation record is expected with -X; keep the header and
            # the first record even if a site returns additional lines.
            lines.extend(accounting.stdout.rstrip().splitlines()[:3])
        else:
            lines.append(f"  sacct: {accounting.stderr.strip() or 'No accounting record yet'}")
    except FileNotFoundError as exc:
        lines.append(f"  Slurm command unavailable: {exc.filename}")
    return lines


def log_tail(path, count):
    if count <= 0:
        return []
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            lines = list(deque(stream, maxlen=count))
        return lines if lines else ["  (empty)"]
    except FileNotFoundError:
        return ["  (not created yet)"]
    except OSError as exc:
        return [f"  Unable to read log: {exc}"]


def log_has_content(path):
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def render(flight_dir, job_id, columns, rows):
    head = [
        f"Flight: {flight_dir.name}",
        f"Job:    {job_id}",
        fit_folder(flight_dir, columns),
        "",
    ]
    slurm = slurm_status(job_id)
    # Save enough room for both log headings and at least a log row per
    # stream when the terminal is reasonably sized.
    max_slurm = max(1, rows - WATCH_ROWS - len(head) - 5)
    head.extend(slurm[:max_slurm])
    head.append("")

    out_path = flight_dir / f"odm-slurm-{job_id}.out"
    err_path = flight_dir / f"odm-slurm-{job_id}.err"

    # Two headings are always present; split the remaining screen rows.
    remaining = max(0, rows - WATCH_ROWS - len(head) - 2)
    if remaining >= 2 and not log_has_content(err_path):
        out_count, err_count = remaining - 1, 1
    elif remaining >= 2 and not log_has_content(out_path):
        out_count, err_count = 1, remaining - 1
    else:
        out_count = (remaining + 1) // 2
        err_count = remaining // 2

    max_lines = os.environ.get("DPU_STATUS_LINES", "")
    cap = min(1000, int(max_lines)) if max_lines.isdecimal() else MAX_LINES
    out_count = min(out_count, cap)
    err_count = min(err_count, cap)

    output = head + [f"ODM stdout (last {out_count} lines):"]
    output.extend(log_tail(out_path, out_count))
    output.append(f"ODM stderr (last {err_count} lines):")
    output.extend(log_tail(err_path, err_count))

    # Reserve two rows for watch's heading and blank separator. A final slice
    # guarantees bounded output even on unusually short terminals.
    return [fit(line, columns) for line in output[:max(1, rows - WATCH_ROWS)]]


def main(argv):
    if len(argv) > 1 or (argv and not re.fullmatch(r"[0-9]+", argv[0])):
        print("Usage: atlas.sh status details [job-id]", file=sys.stderr)
        return 2

    root = Path(os.environ.get("DPU_DATA_ROOT", str(DEFAULT_DATA_ROOT)))
    if not (root / "site-id").is_dir():
        print(f"Atlas flight storage not found: {root / 'site-id'}", file=sys.stderr)
        return 1

    flights = list(submitted_flights(root))
    if argv:
        matches = [item for item in flights
                   if str(item[1]["slurm_job_id"]) == argv[0]]
        if not matches:
            print(f"No submitted flight receipt for job {argv[0]}",
                  file=sys.stderr)
            return 1
        path, record = matches[0]
    else:
        if not flights:
            print("No submitted ODM flights found", file=sys.stderr)
            return 1
        path, record = max(
            flights,
            key=lambda item: (item[1].get("submitted_at", ""),
                              item[0].stat().st_mtime_ns),
        )

    columns, rows = dimensions()
    for line in render(path.parent, str(record["slurm_job_id"]), columns, rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
