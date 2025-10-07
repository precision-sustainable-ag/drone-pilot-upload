# tests/test_artifacts.py
from services.artifacts import finalize_outputs, has_orthophoto, odm_done, ortho_intel_done


def test_has_orthophoto_finds_final_or_code(make_flight):
    f = make_flight("F1", with_code=True)
    # nothing yet
    assert has_orthophoto(str(f)) is None

    # under ./code first
    (f / "code" / "odm_orthophoto").mkdir(parents=True)
    (f / "code" / "odm_orthophoto" / "odm_orthophoto.tif").write_text("x")
    p = has_orthophoto(str(f))
    assert p is not None and p.endswith("code/odm_orthophoto/odm_orthophoto.tif")

    # final takes precedence
    (f / "odm_orthophoto").mkdir()
    (f / "odm_orthophoto" / "odm_orthophoto.tif").write_text("y")
    p2 = has_orthophoto(str(f))
    assert p2 is not None and p2.endswith("odm_orthophoto/odm_orthophoto.tif")


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
        assert [p.name for p in code.iterdir()] == ["images"]


def test_finalize_outputs_skips_existing_dest(make_flight):
    f = make_flight("FEXIST", with_code=True)
    # Put a file under code and a pre-existing destination copy
    (f / "code" / "odm_orthophoto").mkdir(parents=True)
    (f / "code" / "odm_orthophoto" / "odm_orthophoto.tif").write_text("SRC")
    (f / "odm_orthophoto").mkdir()
    (f / "odm_orthophoto" / "odm_orthophoto.tif").write_text("DST")  # pre-existing

    from services.artifacts import finalize_outputs

    finalize_outputs(str(f))

    # Destination should remain untouched ("DST"), not overwritten by "SRC"
    assert (f / "odm_orthophoto" / "odm_orthophoto.tif").read_text() == "DST"
