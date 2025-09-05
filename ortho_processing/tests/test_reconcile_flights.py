# tests/test_reconcile_flights.py
import pytest
import reconcile_flights as rf

# --- shared helpers ---------------------------------------------------------


def _meta(fid, station="central", status="processing", stages=None, num_files=None):
    m = {
        "flight_id": fid,
        "research_station": station,
        "status": status,
    }
    if stages is not None:
        m["stages"] = stages
    if num_files is not None:
        m["num_files"] = num_files
    return m


@pytest.fixture
def patch_records_connect_db(monkeypatch, fake_db):
    # Make records.update_record() write to our fake_db
    import services.persistence as records_mod

    monkeypatch.setattr(records_mod, "connect_db", lambda: (object(), fake_db))
    return fake_db


@pytest.fixture
def neutral_tails(monkeypatch):
    # Default: no terminal marker anywhere
    monkeypatch.setattr(rf, "lsf_terminal_status", lambda *_a, **_k: (None, "no terminal marker"))


# --- tests ------------------------------------------------------------------


def test_file_count_mismatch_blocks_and_sets_status(
    make_flight, patch_records_connect_db, monkeypatch
):
    make_flight("C1", n_images=5)
    meta = _meta("C1", num_files=6, status="processing")

    # Ensure no other side effects run
    monkeypatch.setattr(rf, "odm_done", lambda _d: (False, "no"))
    monkeypatch.setattr(rf, "ortho_intel_done", lambda _d: (False, "no"))
    monkeypatch.setattr(rf, "lsf_terminal_status", lambda *_a, **_k: (None, ""))

    # Run
    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=True)

    # Stage should be blocked (look across all updates for this flight)
    updates = [u for (fid, u) in patch_records_connect_db.updates if fid == "C1"]
    assert updates, "no DB updates recorded"

    payloads = [u.get("$set", {}) for (fid, u) in patch_records_connect_db.updates if fid == "C1"]
    flatten_keys = [k for p in payloads for k in p.keys()]

    assert any(k.endswith("stages.odm.state") or k == "stages.odm.state" for k in flatten_keys)
    assert any(k.endswith("stages.odm.message") or k == "stages.odm.message" for k in flatten_keys)

    # Overall status should be set by update_record
    assert patch_records_connect_db.docs["C1"]["status"] == "file count mismatch"


def test_odm_success_promotes_to_ortho_generated(make_flight, patch_records_connect_db):
    f = make_flight("S1", with_code=True)
    # Make ODM success via log.json
    (f / "code" / "log.json").write_text('{"success": true}')

    meta = _meta("S1", status="processing")

    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=True)

    # Overall promoted
    assert patch_records_connect_db.docs["S1"]["status"] == "ortho generated"
    # Orthophoto path stamped for station
    assert patch_records_connect_db.docs["S1"]["orthophoto_path"].endswith(
        "central/flights/S1/odm_orthophoto/odm_orthophoto.tif"
    )

    # We should have a stage update to succeeded (flattened path)
    [u for (fid, u) in patch_records_connect_db.updates if fid == "S1"]
    flat = {}
    for _, u in patch_records_connect_db.updates:
        if "$set" in u:
            flat.update(u["$set"])
    assert any(k.endswith("stages.odm.state") or k == "stages.odm.state" for k in flat.keys())


def test_ortho_intel_success_yields_processed(make_flight, patch_records_connect_db):
    f = make_flight("S2", with_code=True)
    # ODM already succeeded
    (f / "code" / "log.json").write_text('{"success": true}')
    # Ortho_intel artifacts present
    (f / "veg_indices").mkdir()
    (f / "veg_indices" / "NDVI.tif").write_text("x")

    meta = _meta("S2", status="processing")

    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=True)

    doc = patch_records_connect_db.docs["S2"]
    assert doc["status"] == "processed"
    assert doc["orthophoto_path"].endswith("central/flights/S2/odm_orthophoto/odm_orthophoto.tif")
    # When processed, update_record also stamps COG/veg paths
    assert doc["cog_path"].endswith("central/flights/S2/odm_orthophoto/odm_orthophoto_cog.tif")
    assert doc["veg_index_folder"].endswith("central/flights/S2/veg_indices")


def test_fresh_tail_failure_drops_to_failed(make_flight, patch_records_connect_db, monkeypatch):
    make_flight("F1", with_code=True)
    meta = _meta("F1", status="processing")

    # No artifact success
    monkeypatch.setattr(rf, "odm_done", lambda _d: (False, "no"))
    monkeypatch.setattr(rf, "ortho_intel_done", lambda _d: (False, "no"))

    # Fresh failure on ODM tail
    def fake_tail(out, _err, **_):
        if out.endswith("odm_processing-out.txt"):
            return ("failed", "Exited with exit code 1.")
        return (None, "no")

    monkeypatch.setattr(rf, "lsf_terminal_status", fake_tail)

    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=False)

    assert patch_records_connect_db.docs["F1"]["status"] == "failed"


def test_stale_failure_does_not_downgrade_overall(
    make_flight, patch_records_connect_db, monkeypatch
):
    make_flight("F2", with_code=True)
    meta = _meta("F2", status="processing", stages={"odm": {"state": "failed"}})

    # No artifact success, no fresh tail failure
    monkeypatch.setattr(rf, "odm_done", lambda _d: (False, "no"))
    monkeypatch.setattr(rf, "ortho_intel_done", lambda _d: (False, "no"))
    monkeypatch.setattr(rf, "lsf_terminal_status", lambda *_a, **_k: (None, "no terminal marker"))

    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=False)

    # Overall should remain 'processing' (no fresh failure now)
    assert patch_records_connect_db.docs.get("F2", {}).get("status", "processing") == "processing"


def test_processed_is_terminal(make_flight, patch_records_connect_db, monkeypatch):
    make_flight("T1", with_code=True)
    meta = _meta(
        "T1",
        status="processed",
        stages={"odm": {"state": "succeeded"}, "ortho_intel": {"state": "succeeded"}},
    )

    # Even if tails now say failed, processed overall should not downgrade
    monkeypatch.setattr(
        rf, "lsf_terminal_status", lambda *_a, **_k: ("failed", "Exited with exit code 137.")
    )
    monkeypatch.setattr(rf, "odm_done", lambda _d: (True, "log success"))
    monkeypatch.setattr(rf, "ortho_intel_done", lambda _d: (True, "veg present"))

    rf.reconcile_one(patch_records_connect_db, meta, dry_run=False, finalize=False)

    # No doc written or status remains processed
    doc = patch_records_connect_db.docs.get("T1")
    if doc is None:
        # No write => still effectively processed
        assert True
    else:
        assert doc.get("status", "processed") == "processed"


def test_dry_run_writes_nothing(make_flight, patch_records_connect_db, monkeypatch):
    f = make_flight("DR1", with_code=True)
    (f / "code" / "log.json").write_text('{"success": true}')
    meta = _meta("DR1", status="processing")

    # Ensure tails neutral
    monkeypatch.setattr(rf, "lsf_terminal_status", lambda *_a, **_k: (None, ""))
    rf.reconcile_one(patch_records_connect_db, meta, dry_run=True, finalize=True)

    # No DB updates on dry-run
    assert all(fid != "DR1" for fid, _ in patch_records_connect_db.updates)
    assert "DR1" not in patch_records_connect_db.docs
