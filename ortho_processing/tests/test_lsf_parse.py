import os
import time

from services.lsf_parse import lsf_terminal_status


def _touch_with_text(path, text, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_out_success_footer_wins(tmp_path):
    out = tmp_path / "odm_processing-out.txt"
    err = tmp_path / "odm_processing-err.txt"
    _touch_with_text(out, "...\nSuccessfully completed.\n")
    _touch_with_text(err, "old scary error\n")
    state, reason = lsf_terminal_status(str(out), str(err))
    assert state == "succeeded"
    assert "Successfully completed" in reason


def test_out_failure_footer_wins(tmp_path):
    out = tmp_path / "odm_processing-out.txt"
    err = tmp_path / "odm_processing-err.txt"
    _touch_with_text(out, "...\nExited with exit code 1.\n")
    _touch_with_text(err, "")
    state, reason = lsf_terminal_status(str(out), str(err))
    assert state == "failed"
    assert "exit code" in reason.lower()


def test_err_newer_can_trigger_heuristic_failure(tmp_path):
    out = tmp_path / "odm_processing-out.txt"
    err = tmp_path / "odm_processing-err.txt"
    t0 = time.time()
    _touch_with_text(str(out), "some progress\n", mtime=t0 - 120)  # older
    _touch_with_text(str(err), "insufficient memory\n", mtime=t0)  # newer
    state, reason = lsf_terminal_status(str(out), str(err))
    assert state == "failed"
    assert "heuristic" in reason.lower() or "err tail" in reason.lower()


def test_err_older_is_ignored(tmp_path):
    out = tmp_path / "odm_processing-out.txt"
    err = tmp_path / "odm_processing-err.txt"
    t0 = time.time()
    _touch_with_text(str(out), "some progress\n", mtime=t0)  # newer
    _touch_with_text(str(err), "insufficient memory\n", mtime=t0 - 300)  # older
    state, reason = lsf_terminal_status(str(out), str(err))
    assert state is None


def test_out_success_preempts_newer_err(tmp_path):
    out = tmp_path / "odm_processing-out.txt"
    err = tmp_path / "odm_processing-err.txt"
    t0 = time.time()
    _touch_with_text(str(out), "...\nSuccessfully completed.\n", mtime=t0 - 60)
    _touch_with_text(str(err), "insufficient memory\n", mtime=t0)  # newer but should be ignored
    state, reason = lsf_terminal_status(str(out), str(err))
    assert state == "succeeded"
