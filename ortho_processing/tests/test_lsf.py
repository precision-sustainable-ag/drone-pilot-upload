import itertools
import subprocess
import types

import services.lsf as lsf


def test_submit_parses_job_id(monkeypatch, tmp_path):
    script = tmp_path / "s.sh"
    script.write_text("#!/bin/bash\necho hi\n")

    def fake_run(*_a, **_k):
        return types.SimpleNamespace(
            returncode=0, stdout="Job <123456> is submitted to queue <gpu>.\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    jid = lsf.submit(str(script), str(tmp_path))
    assert jid == 123456


def test_submit_logs_error_on_failure(monkeypatch, tmp_path, caplog):
    script = tmp_path / "s.sh"
    script.write_text("#!/bin/bash\necho hi\n")

    def fake_run(*_a, **_k):
        return types.SimpleNamespace(
            returncode=1, stdout="Queue has been closed.", stderr="Queue has been closed."
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with caplog.at_level("ERROR"):
        jid = lsf.submit(str(script), str(tmp_path))
        assert jid is None
        assert any("lsf submit job" in rec.getMessage() for rec in caplog.records)


def test_monitor_transitions_run_to_done(monkeypatch):
    # Cycle RUN → DONE in two polls
    outputs = itertools.cycle(
        [
            types.SimpleNamespace(returncode=0, stdout="... STAT RUN ...", stderr=""),
            types.SimpleNamespace(returncode=0, stdout="... STAT DONE ...", stderr=""),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: next(outputs))
    assert lsf.monitor(999) == "DONE"


def test_monitor_returns_none_on_exception(monkeypatch, caplog):
    import subprocess

    from services import lsf

    def boom(*_a, **_k):
        raise RuntimeError("bjobs unavailable")

    monkeypatch.setattr(subprocess, "run", boom)
    with caplog.at_level("ERROR"):
        out = lsf.monitor(123)
        assert out is None
        assert any("lsf monitor job" in rec.getMessage() for rec in caplog.records)
