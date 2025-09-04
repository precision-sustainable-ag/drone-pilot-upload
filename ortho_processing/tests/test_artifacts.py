# tests/test_artifacts.py
import os
from services.artifacts import has_orthophoto, odm_done, ortho_intel_done, finalize_outputs

def test_has_orthophoto_finds_final_or_code(make_flight):
    f = make_flight("F1", with_code=True)
    # nothing yet
    assert has_orthophoto(str(f)) is None

    # under ./code first
    (f / "code" / "odm_orthophoto").mkdir(parents=True)
    (f / "code" / "odm_orthophoto" / "odm_orthophoto.tif").write_text("x")
    assert has_orthophoto(str(f)).endswith("code/odm_orthophoto/odm_orthophoto.tif")

    # final takes precedence
    (f / "odm_orthophoto").mkdir()
    (f / "odm_orthophoto" / "odm_orthophoto.tif").write_text("y")
    assert has_orthophoto(str(f)).endswith("odm_orthophoto/odm_orthophoto.tif")

def test_odm_done_by_log_success(make_flight):
    f = make_flight("F2", with_code=True)
    (f / "code" / "log.json").write_text('{"success": true}')
    ok, why = odm_done(str(f))
    assert ok and "success=true" in why

def test_odm_done_by_artifact(make_flight):
    f = make_flight("F3", with_code=True)
    (f / "code" / "odm_orthophoto").mkdir(parents=True)
    (f / "code" / "odm_orthophoto" / "odm_orthophoto.tif").write_text("x")
    ok, why = odm_done(str(f))
    assert ok and "orthophoto" in why

def test_ortho_intel_done_requires_veg_index(make_flight):
    f = make_flight("F4")
    # COG only -> not success
    (f / "odm_orthophoto").mkdir()
    (f / "odm_orthophoto" / "odm_orthophoto_cog.tif").write_text("x")
    ok, why = ortho_intel_done(str(f))
    assert not ok and "COG present" in why

    # veg_indices raster -> success
    (f / "veg_indices").mkdir()
    (f / "veg_indices" / "NDVI.tif").write_text("x")
    ok2, why2 = ortho_intel_done(str(f))
    assert ok2 and "veg_indices" in why2

def test_finalize_outputs_moves_from_code(make_flight):
    f = make_flight("F5", with_code=True)
    # prepare content under ./code
    (f / "code" / "odm_orthophoto").mkdir()
    (f / "code" / "odm_orthophoto" / "odm_orthophoto.tif").write_text("x")
    (f / "code" / "images").mkdir(exist_ok=True)  # should be preserved

    finalize_outputs(str(f))

    # moved
    assert (f / "odm_orthophoto" / "odm_orthophoto.tif").exists()
    # code should remain only with images or be gone
    code = f / "code"
    if code.exists():
        assert list(p.name for p in code.iterdir()) == ["images"]
