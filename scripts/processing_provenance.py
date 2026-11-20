"""Capture lightweight submission-time ODM version provenance.

The SIF metadata and filename are not a cryptographic image fingerprint.
Content hashes are recorded for the small processing/submission scripts only;
large container images are not rehashed by recurring coordinators.
"""

import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

GIT_SHA = re.compile(r"^[0-9a-f]{40,64}$")


def _git(repo, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True,
            text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _sha256(path):
    """Fingerprint small scripts; do not hash original imagery or large SIFs."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_processing_provenance(repo, sandbox, submitter_script):
    """Snapshot the exact checkout and expected ODM image at submission.

    The batch job may run later; this is a submission-time observation, not
    attestation of which image bytes actually executed on a compute node.
    """
    repo = Path(repo).resolve(strict=True)
    submitter_script = Path(submitter_script)
    job_script = repo / "scripts" / f"odm-{sandbox}-flight.sh"
    default_image = repo / "sif_files" / (
        "odm-3.6.2-gpu.sif" if sandbox == "atlas" else "odm-3.6.2-cpu.sif"
    )
    configured_image = Path(os.environ.get("DPU_ODM_SIF") or default_image).expanduser()
    image_path = configured_image.resolve(strict=False)
    try:
        stat = image_path.stat() if image_path.is_file() else None
    except OSError:
        stat = None

    git_sha = _git(repo, "rev-parse", "--verify", "HEAD")
    status = _git(repo, "status", "--porcelain", "--untracked-files=normal")

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_sha if git_sha and GIT_SHA.fullmatch(git_sha) else None,
        "working_tree": (
            "unknown" if status is None else "modified" if status else "clean"
        ),
        "job_script_sha256": _sha256(job_script),
        "submitter_script_sha256": _sha256(submitter_script),
        "odm_image": {
            "configured_path": str(configured_image),
            "resolved_path": str(image_path),
            "version_hint": image_path.name,
            "size_bytes": stat.st_size if stat else None,
            "mtime_ns": stat.st_mtime_ns if stat else None,
            "sha256": None,  # Not computed during normal submissions.
        },
    }
