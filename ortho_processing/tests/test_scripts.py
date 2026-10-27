# tests/test_scripts.py
from services.scripts import write_odm_script, write_ortho_intel_script


def test_write_odm_script_writes_bsub_script(make_flight):
    f = make_flight("SF1")
    script = f / "odm_lsf.sh"
    write_odm_script(
        flight_dir=str(f),
        images_dir=str(f / "images"),
        script_path=str(script),
    )
    text = script.read_text()
    assert "#BSUB -q" in text
    assert "--project-path" in text
    assert "odm_gpu-fixed.sif" in text


def test_write_ortho_intel_script_writes_bsub_script(make_flight):
    f = make_flight("SF2")
    script = f / "ortho_intel_lsf.sh"
    write_ortho_intel_script(
        flight_dir=str(f),
        ortho_file=str(f / "odm_orthophoto" / "odm_orthophoto.tif"),
        script_path=str(script),
    )
    text = script.read_text()
    assert "#BSUB -q" in text
    assert "drone_ortho_intel.sif" in text
