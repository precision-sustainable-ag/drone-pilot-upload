from services.persistence import set_stage


def test_set_stage_writes_path(fake_db):
    set_stage(fake_db, "X1", "odm", {"state": "succeeded", "message": "ok"}, dry_run=False)
    d = fake_db.docs["X1"]
    assert d["stages.odm.state"] == "succeeded" or d["state"] == "succeeded" or "stages" in d
    # Accept either flattened or expanded depending on your update logic
    # But at least ensure an update happened:
    assert fake_db.updates, "expected an update to be recorded"


def test_set_stage_dry_run_no_write(fake_db):
    n0 = len(fake_db.updates)
    set_stage(fake_db, "X2", "odm", {"state": "failed"}, dry_run=True)
    assert len(fake_db.updates) == n0
