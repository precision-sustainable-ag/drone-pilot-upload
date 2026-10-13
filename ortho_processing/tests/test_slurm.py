from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ortho_processing.services.slurm import (
    SlurmSubmissionError,
    submit,
)


def test_submit_returns_job_id(tmp_path):
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")

    completed = Mock(
        returncode=0,
        stdout="20881329\n",
        stderr="",
    )

    with patch(
        "ortho_processing.services.slurm.subprocess.run",
        return_value=completed,
    ) as run:
        job_id = submit(script)

    assert job_id == 20881329
    assert run.call_args.args[0] == [
        "sbatch",
        "--parsable",
        str(script.resolve()),
    ]


def test_submit_reports_scheduler_failure(tmp_path):
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n")

    completed = Mock(
        returncode=1,
        stdout="",
        stderr="sbatch: error: Invalid account",
    )

    with patch(
        "ortho_processing.services.slurm.subprocess.run",
        return_value=completed,
    ):
        with pytest.raises(SlurmSubmissionError):
            submit(script)


def test_submit_rejects_missing_script(tmp_path):
    with pytest.raises(FileNotFoundError):
        submit(tmp_path / "missing.sh")
