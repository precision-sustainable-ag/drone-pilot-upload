# tests/test_new_cron.py
import os
from datetime import datetime, timedelta

import new_cron as nc

# --- helpers ----------------------------------------------------------------


class Calls:
    def __init__(self):
        self.items = []

    def append(self, *_args, **_kwargs):
        self.items.append((_args, _kwargs))

    def statuses(self):
        # capture 3rd positional arg (status)
        out = []
        for args, kwargs in self.items:
            if len(args) >= 3:
                out.append(args[2])
            elif "status" in kwargs:
                out.append(kwargs["status"])
        return out


def mk_meta(fid, station="central", status=None, num_files=5):
    return {
        "flight_id": fid,
        "research_station": station,
        "status": status,
        "num_files": num_files,
    }


# Use conftest.make_flight / patch_config fixtures to create dirs + images
def flight_dir_for(cfg, meta):
    return os.path.join(cfg["mount_dir"], meta["research_station"], "flights", meta["flight_id"])


# --- processFlight tests -----------------------------------------------------


def test_processFlight_no_record(fake_db):
    # no doc in db
    assert nc.processFlight("MISSING", fake_db) is None


def test_processFlight_file_count_mismatch(monkeypatch, make_flight, fake_db):
    # create flight with 5 images but DB says 6
    make_flight("MM1", n_images=5)
    meta = mk_meta("MM1", status="processing", num_files=6)
    fake_db.docs["MM1"] = meta

    # Spy: update_record should NOT be called for mismatch
    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))
    # Pipeline should not be called either
    monkeypatch.setattr(
        nc,
        "write_and_run_odm",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("ODM should not run")),
    )
    monkeypatch.setattr(
        nc,
        "write_and_run_ortho_intel",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("OI should not run")),
    )

    out = nc.processFlight("MM1", fake_db)
    assert out is None
    assert calls.items == []


def test_processFlight_ortho_generated_success(monkeypatch, make_flight, fake_db):
    make_flight("OG1", n_images=5)
    meta = mk_meta("OG1", status="ortho generated", num_files=5)
    fake_db.docs["OG1"] = meta

    # write_and_run_ortho_intel succeeds, ODM must be skipped
    monkeypatch.setattr(nc, "write_and_run_ortho_intel", lambda *_a, **_k: True)
    monkeypatch.setattr(
        nc,
        "write_and_run_odm",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("ODM should be skipped")),
    )

    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))

    out = nc.processFlight("OG1", fake_db)
    assert out == "OG1"
    # Only one update: processed (with research_station)
    assert calls.statuses() == ["processed"]
    # Ensure RS passed as 4th positional arg (optional), if your signature uses it
    # i.e., (flight_dir, flight_id, status, research_station)
    assert calls.items[-1][0][3] == "central"


def test_processFlight_ortho_generated_failure(monkeypatch, make_flight, fake_db):
    make_flight("OG2", n_images=5)
    meta = mk_meta("OG2", status="ortho generated", num_files=5)
    fake_db.docs["OG2"] = meta

    monkeypatch.setattr(nc, "write_and_run_ortho_intel", lambda *_a, **_k: False)
    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))

    out = nc.processFlight("OG2", fake_db)
    assert out is None
    assert calls.statuses() == ["failed"]


def test_processFlight_default_success(monkeypatch, make_flight, fake_db):
    make_flight("DF1", n_images=5)
    meta = mk_meta("DF1", status=None, num_files=5)
    fake_db.docs["DF1"] = meta

    # ODM then OI succeed
    monkeypatch.setattr(nc, "write_and_run_odm", lambda *_a, **_k: True)
    monkeypatch.setattr(nc, "write_and_run_ortho_intel", lambda *_a, **_k: True)

    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))

    out = nc.processFlight("DF1", fake_db)
    assert out == "DF1"
    # processing -> ortho generated -> processed
    assert calls.statuses() == ["processing", "ortho generated", "processed"]


def test_processFlight_default_odm_fail(monkeypatch, make_flight, fake_db):
    make_flight("DF2", n_images=5)
    meta = mk_meta("DF2", status=None, num_files=5)
    fake_db.docs["DF2"] = meta

    monkeypatch.setattr(nc, "write_and_run_odm", lambda *_a, **_k: False)
    # OI must not be called
    monkeypatch.setattr(
        nc,
        "write_and_run_ortho_intel",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("OI should not run")),
    )

    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))

    out = nc.processFlight("DF2", fake_db)
    assert out is None
    assert calls.statuses() == ["processing", "failed"]


def test_processFlight_default_oi_fail(monkeypatch, make_flight, fake_db):
    make_flight("DF3", n_images=5)
    meta = mk_meta("DF3", status=None, num_files=5)
    fake_db.docs["DF3"] = meta

    monkeypatch.setattr(nc, "write_and_run_odm", lambda *_a, **_k: True)
    monkeypatch.setattr(nc, "write_and_run_ortho_intel", lambda *_a, **_k: False)

    calls = Calls()
    monkeypatch.setattr(nc, "update_record", lambda *a, **k: calls.append(*a, **k))

    out = nc.processFlight("DF3", fake_db)

    assert out is None
    assert calls.statuses() == ["processing", "ortho generated", "failed"]


# --- main() selection tests --------------------------------------------------


def test_main_selects_expected_records(monkeypatch, caplog):
    # Freeze time inside new_cron
    fixed_now = datetime(2025, 9, 5, 12, 0, 0)

    class _DT(datetime):  # keep classmethods like .combine
        @classmethod
        def now(cls, *_a, **_k):
            return fixed_now

    monkeypatch.setattr(nc, "datetime", _DT, raising=True)

    # Fake DB
    class Coll:
        def __init__(self, docs):
            self._docs = docs

        def find(self, q):
            yesterday = q["upload_time"]["$lt"]
            rs = q["research_station"]
            return [
                d
                for d in self._docs
                if d["research_station"] == rs and d["upload_time"] < yesterday
            ]

        def find_one(self, q):
            fid = q.get("flight_id")
            for d in self._docs:
                if d["flight_id"] == fid:
                    return d
            return None

    docs = [
        {
            "flight_id": "a",
            "research_station": "central",
            "upload_time": fixed_now - timedelta(days=2),
            "status": "processing",
            "num_files": 0,
        },
        {
            "flight_id": "b",
            "research_station": "central",
            "upload_time": fixed_now,
            "status": "processing",
            "num_files": 0,
        },  # too new
        {
            "flight_id": "c",
            "research_station": "west",
            "upload_time": fixed_now - timedelta(days=2),
            "status": "processing",
            "num_files": 0,
        },
        {
            "flight_id": "d",
            "research_station": "central",
            "upload_time": fixed_now - timedelta(days=3),
            "status": "ortho generated",
            "num_files": 0,
        },
    ]
    coll = Coll(docs)
    monkeypatch.setattr(nc, "connect_db", lambda: (object(), coll), raising=True)

    # Make the file-count check deterministic (optional safeguard)
    monkeypatch.setattr(nc, "count_files", lambda _p: 0, raising=True)

    # Stub pipeline & update_record (only record final 'processed' stamps)
    calls: dict[str, list[str]] = {"processed": []}
    monkeypatch.setattr(nc, "write_and_run_odm", lambda *_a, **_k: True, raising=True)
    monkeypatch.setattr(nc, "write_and_run_ortho_intel", lambda *_a, **_k: True, raising=True)

    def _update_record(_fdir, fid, status, _rs=None):
        if status == "processed":
            calls["processed"].append(fid)

    monkeypatch.setattr(nc, "update_record", _update_record, raising=True)

    with caplog.at_level("INFO"):
        nc.main()

    # Only "d" should be processed (since "a" is processing, "b" too new, "c" wrong RS)
    assert calls["processed"] == ["d"]
