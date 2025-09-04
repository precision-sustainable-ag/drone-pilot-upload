# tests/test_records.py
import json
from services.records import update_record

def test_update_record_processed(monkeypatch, make_flight, patch_config, fake_db):
    f = make_flight("R1", station="central")
    # write minimal CRS file
    (f / "odm_georeferencing").mkdir()
    (f / "odm_georeferencing" / "proj.txt").write_text("EPSG:4326")

    # Patch connect_db used by records.update_record to return our fake collection
    from services import records as rec_mod
    monkeypatch.setattr(rec_mod, "connect_db", lambda: (object(), fake_db))

    update_record(str(f), "R1", "processed", "central")

    doc = fake_db.docs["R1"]
    assert doc["status"] == "processed"
    assert "orthophoto_path" in doc
    assert doc["orthophoto_path"].endswith("central/flights/R1/odm_orthophoto/odm_orthophoto.tif")
    assert doc["orthophoto_source_crs"] == "EPSG:4326"

def test_update_record_ortho_generated(monkeypatch, make_flight, patch_config, fake_db):
    f = make_flight("R2", station="central")
    (f / "odm_georeferencing").mkdir()
    (f / "odm_georeferencing" / "proj.txt").write_text("EPSG:32617")

    from services import records as rec_mod
    monkeypatch.setattr(rec_mod, "connect_db", lambda: (object(), fake_db))

    update_record(str(f), "R2", "ortho generated", "central")
    doc = fake_db.docs["R2"]
    assert doc["status"] == "ortho generated"
    assert doc["orthophoto_path"].endswith("central/flights/R2/odm_orthophoto/odm_orthophoto.tif")
