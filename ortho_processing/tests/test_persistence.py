# tests/test_records.py
from services.persistence import update_record


def test_update_record_processed(monkeypatch, make_flight, fake_db):
    f = make_flight("R1", station="central")
    # write minimal CRS file
    (f / "odm_georeferencing").mkdir()
    (f / "odm_georeferencing" / "proj.txt").write_text("EPSG:4326")

    # Patch connect_db used by records.update_record to return our fake collection
    from services import persistence as rec_mod

    monkeypatch.setattr(rec_mod, "connect_db", lambda: (object(), fake_db))

    update_record(str(f), "R1", "processed", "central")

    doc = fake_db.docs["R1"]
    assert doc["status"] == "processed"
    assert "orthophoto_path" in doc
    assert doc["orthophoto_path"].endswith("central/flights/R1/odm_orthophoto/odm_orthophoto.tif")
    assert doc["orthophoto_source_crs"] == "EPSG:4326"


def test_update_record_ortho_generated(monkeypatch, make_flight, fake_db):
    f = make_flight("R2", station="central")
    (f / "odm_georeferencing").mkdir()
    (f / "odm_georeferencing" / "proj.txt").write_text("EPSG:32617")

    from services import persistence as rec_mod

    monkeypatch.setattr(rec_mod, "connect_db", lambda: (object(), fake_db))

    update_record(str(f), "R2", "ortho generated", "central")
    doc = fake_db.docs["R2"]
    assert doc["status"] == "ortho generated"
    assert doc["orthophoto_path"].endswith("central/flights/R2/odm_orthophoto/odm_orthophoto.tif")


def test_set_overall_status_dry_run_skips_update(monkeypatch):
    from services import persistence as rec

    calls = {"count": 0}

    def spy_update_record(*_args, **_kwargs):
        calls["count"] += 1

    monkeypatch.setattr(rec, "update_record", spy_update_record)

    # Dry-run: should not call update_record
    rec.set_overall_status("/tmp/fdir", "FID", "failed", "central", dry_run=True)
    assert calls["count"] == 0

    # Non-dry-run: should call once
    rec.set_overall_status("/tmp/fdir", "FID", "failed", "central", dry_run=False)
    assert calls["count"] == 1
