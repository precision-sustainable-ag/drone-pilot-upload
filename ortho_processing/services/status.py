# services/reconcile.py
from __future__ import annotations


def recompute_overall(
    odm_state: str, oi_state: str, overall_prev: str | None, *, failed_now: bool
) -> str:
    # processed is terminal
    if overall_prev == "processed":
        return "processed"

    # Only downgrade on a fresh failure
    if failed_now:
        return "failed"

    # Success paths (no stale-failure promotion)
    if oi_state == "succeeded":
        return "processed"
    if odm_state == "succeeded" and oi_state != "failed":
        return "ortho generated"

    # Otherwise keep prior or default to processing (no promotion on stale OI failure)
    return overall_prev or "processing"


def reconcile_state(
    prev: str | None,
    ok_by_artifacts: bool,
    tail_state: str | None,
    tail_reason: str | None = None,
) -> tuple[str, str]:
    """
    Decide a new state for one stage.
    Priority:
      1. Tail markers (succeeded/failed) win
      2. Otherwise artifacts can mark success
      3. Otherwise stick to previous (failed/succeeded are sticky)
      4. Else 'unknown'

    Returns: (state, reason)
    """
    # Tail log is authoritative
    if tail_state == "failed":
        return "failed", tail_reason or "log tail shows failure"
    if tail_state == "succeeded":
        return "succeeded", tail_reason or "log tail shows success"

    # Artifact-level success
    if ok_by_artifacts:
        return "succeeded", "artifacts indicate success"

    # Stickiness: never undo a terminal state
    if prev in ("failed", "succeeded"):
        return prev, "sticky"

    return prev or "unknown", "no markers"
