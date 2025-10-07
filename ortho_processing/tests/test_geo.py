# tests/test_geo.py
from services.geo import read_crs


def test_read_crs_from_proj_txt(make_flight):
    f = make_flight("G1")
    (f / "odm_georeferencing").mkdir()
    (f / "odm_georeferencing" / "proj.txt").write_text("EPSG:4326")
    assert read_crs(str(f)) == "EPSG:4326"
