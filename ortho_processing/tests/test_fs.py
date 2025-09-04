# tests/test_fs.py
from services.fs import count_files

def test_count_files_counts_images_nonrecursive(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    (d / "a.jpg").write_text("x")
    (d / "b.jpeg").write_text("x")
    (d / "c.tif").write_text("x")
    (d / "d.txt").write_text("x")
    assert count_files(str(d)) == 4
