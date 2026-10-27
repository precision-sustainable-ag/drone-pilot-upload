# tests/conftest.py
import json
import types

import pytest
from config import config


@pytest.fixture
def patch_config(tmp_path):
    """Point config at temporary locations and set defaults used by writers."""
    mount = tmp_path / "mount"
    scratch = tmp_path / "scratch"
    code = tmp_path / "code"
    logs = tmp_path / "logs"
    (mount / "central" / "flights").mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    (code / "sif_files").mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    # Fake SIFs (only paths are used)
    (code / "sif_files" / "odm_gpu-fixed.sif").write_text("sif")
    (code / "sif_files" / "drone_ortho_intel.sif").write_text("sif")

    config["mount_dir"] = str(mount)
    config["scratch_dir"] = str(scratch)
    config["code_dir"] = str(code)
    config["log_file"] = str(logs / "app.log")

    # Optional knobs some writers may read
    config.setdefault("queues", {"odm": "short_gpu", "ortho_intel": "short"})
    config.setdefault(
        "odm", {"n_cores": 32, "wall": "30:00", "mem_gb": 250, "pc_quality": "medium"}
    )
    config.setdefault("ortho_intel", {"n_cores": 32, "wall": "2:00"})

    return config


@pytest.fixture
def make_flight(tmp_path, patch_config):  # noqa: ARG001
    """Factory to create a flight directory with common structure."""

    def _make(fid: str, station: str = "central", n_images: int = 5, with_code=False):
        fdir = tmp_path / "mount" / station / "flights" / fid
        (fdir / "images").mkdir(parents=True, exist_ok=True)
        for i in range(n_images):
            (fdir / "images" / f"img_{i:03d}.jpg").write_text("x")
        if with_code:
            (fdir / "code").mkdir(exist_ok=True)
        return fdir

    return _make


# --- Fake DB objects ---------------------------------------------------------


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = {d["flight_id"]: d for d in (docs or [])}
        self.updates = []

    def find_one(self, q):
        return self.docs.get(q.get("flight_id"))

    def find(self, q):
        # crude filter on research_station if present
        out = []
        for d in self.docs.values():
            if "research_station" in q and d.get("research_station") != q["research_station"]:
                continue
            out.append(d.copy())
        return out

    def update_one(self, q, update, upsert=False):  # noqa: ARG002
        fid = q.get("flight_id")
        doc = self.docs.setdefault(fid, {"flight_id": fid})

        # support only $set used by the codebase
        if "$set" in update:
            doc.update(update["$set"])
        self.updates.append((fid, update))
        return types.SimpleNamespace(matched_count=1, modified_count=1)


@pytest.fixture
def fake_db(monkeypatch):
    """Monkeypatch services.db.connect_db to return a fake collection."""
    from services import db as db_module

    coll = FakeCollection()

    def _connect_db():
        return object(), coll

    monkeypatch.setattr(db_module, "connect_db", _connect_db)
    return coll


# --- Common small helpers ----------------------------------------------------


@pytest.fixture
def write_log_success():
    def _write_log_success(fdir):
        # ./code/log.json with {"success": true}
        (fdir / "code").mkdir(exist_ok=True)
        (fdir / "code" / "log.json").write_text(json.dumps({"success": True}))

    return _write_log_success
