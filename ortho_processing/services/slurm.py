"""Slurm job submission utilities."""

import re
import subprocess
from pathlib import Path


class SlurmSubmissionError(RuntimeError):
    """Raised when Slurm rejects a job submission."""


def submit(script_path, *, cwd=None):
    """Submit an existing Slurm script and return its job ID.

    Does not wait for the job to complete.
    """
    script = Path(script_path).resolve()

    if not script.is_file():
        raise FileNotFoundError(script)

    result = subprocess.run(
        ["sbatch", "--parsable", str(script)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise SlurmSubmissionError(
            f"sbatch failed ({result.returncode}): {result.stderr.strip()}"
        )

    output = result.stdout.strip()
    match = re.fullmatch(r"(\d+)(?:;[\w.-]+)?", output)

    if not match:
        raise SlurmSubmissionError(
            f"Unexpected sbatch response: {output!r}"
        )

    return int(match.group(1))
