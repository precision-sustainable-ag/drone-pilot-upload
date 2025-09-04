# tests/test_pipeline.py
import json
import services.pipeline as pipeline

def test_write_and_run_odm_success(monkeypatch, make_flight, patch_config):
    f = make_flight("P1", with_code=True)

    # Patch the names used inside services.pipeline
    monkeypatch.setattr("services.pipeline.submit", lambda *a, **k: 12345)
    monkeypatch.setattr("services.pipeline.monitor", lambda *a, **k: "DONE")

    # Make ODM success marker appear after run (pipeline checks artifacts)
    def fake_odm_done(fdir):
        (f / "code").mkdir(exist_ok=True)
        (f / "code" / "log.json").write_text(json.dumps({"success": True}))
        return True, "log.json success=true"

    monkeypatch.setattr("services.pipeline.odm_done", fake_odm_done)
    # Optionally, avoid any file moves during the test
    monkeypatch.setattr("services.pipeline.finalize_outputs", lambda *a, **k: None)

    ok = pipeline.write_and_run_odm(str(f), "P1")
    assert ok

def test_write_and_run_odm_failure_when_no_artifacts(monkeypatch, make_flight, patch_config):
    f = make_flight("P2", with_code=True)
    monkeypatch.setattr("services.pipeline.submit", lambda *a, **k: 222)
    monkeypatch.setattr("services.pipeline.monitor", lambda *a, **k: "DONE")
    monkeypatch.setattr("services.pipeline.odm_done", lambda d: (False, "no outputs"))
    monkeypatch.setattr("services.pipeline.finalize_outputs", lambda *a, **k: None)

    ok = pipeline.write_and_run_odm(str(f), "P2")
    assert not ok

def test_write_and_run_ortho_intel_success(monkeypatch, make_flight, patch_config):
    f = make_flight("P3")
    (f / "odm_orthophoto").mkdir()
    (f / "odm_orthophoto" / "odm_orthophoto.tif").write_text("x")

    monkeypatch.setattr("services.pipeline.submit", lambda *a, **k: 333)
    monkeypatch.setattr("services.pipeline.monitor", lambda *a, **k: "DONE")

    ok = pipeline.write_and_run_ortho_intel(str(f), "P3")
    assert ok

def test_write_and_run_ortho_intel_missing_ortho(make_flight, patch_config):
    f = make_flight("P4")
    assert not pipeline.write_and_run_ortho_intel(str(f), "P4")

