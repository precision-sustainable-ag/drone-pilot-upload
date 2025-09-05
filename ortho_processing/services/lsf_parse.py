# services/lsf_parse.py
from __future__ import annotations
from typing import Optional, Tuple, List
import os

SUCCESS_LINE = "successfully completed."

# Things we only trust if they appear at the *end* of the file
FAIL_LINE_PREFIXES = (
    "exited with exit code",          # generic EXIT footer
    "term_",                          # TERM_RUNLIMIT, TERM_OUT_OF_MEMORY, etc.
    "job was terminated",             # admin/user termination
)

# Strong failure phrases we accept at tail even without the LSF footer
FAIL_LINE_SNIPPETS = (
    "insufficient memory",
    "failed to allocate",
    "subprocessexception",
    "processing stopped",
    "command not found",
    "no such file or directory",
)

def _tail_lines(path: str, n: int) -> List[str]:
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except Exception:
        return []

def tail_lines(paths: list[str], n: int = 50) -> List[str]:
    """Read last n lines from multiple files, concatenated in mtime order (newest last)."""
    existing = [(p, os.path.getmtime(p)) for p in paths if os.path.isfile(p)]
    if not existing:
        return []
    # sort by mtime ascending so the newest file tail ends up last
    existing.sort(key=lambda x: x[1])
    out: List[str] = []
    for p, _ in existing:
        out.extend(_tail_lines(p, n))
    # keep only the last n overall to stay bounded
    return out[-n:]

def lsf_terminal_status(out_path, err_path, tail_len=50):
    # get tails and mtimes separately
    out_tail = _tail_lines(out_path, tail_len)
    err_tail = _tail_lines(err_path, tail_len)
    m_out = os.path.getmtime(out_path) if os.path.isfile(out_path) else 0
    m_err = os.path.getmtime(err_path) if os.path.isfile(err_path) else 0

    # 1) Trust OUT for terminal markers (authoritative)
    for s in reversed(out_tail):
        low = s.strip().lower()
        if not low: 
            continue
        if low == SUCCESS_LINE:                      # "successfully completed."
            return "succeeded", "LSF footer: Successfully completed."
        if any(low.startswith(p) for p in FAIL_LINE_PREFIXES):
            return "failed", f"LSF tail: {s.strip()}"

    # 2) Use ERR only if it's newer than OUT and we don't have an OUT footer
    if m_err >= m_out:
        for s in reversed(err_tail):
            low = s.strip().lower()
            if not low:
                continue
            if any(sn in low for sn in FAIL_LINE_SNIPPETS):
                return "failed", f"ERR tail (heuristic): {s.strip()}"

    # 3) No terminal marker
    return None, "no terminal marker near tail"
