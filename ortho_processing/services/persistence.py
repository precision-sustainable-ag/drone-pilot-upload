from datetime import datetime, timezone
from typing import Optional
import os
from services.db import connect_db
from services.geo import read_crs
from config import config


def utcnow():
    return datetime.now(timezone.utc)

def set_stage(db, fid: str, stage: str, updates: dict, dry_run: bool=False) -> None:
    path = f"stages.{stage}"
    payload = {f"{path}.{k}": v for k, v in updates.items()}
    if dry_run:
        return
    db.update_one({"flight_id": fid}, {"$set": payload})

def update_record(flight_dir: str, flight_id: str, status: str, research_station: Optional[str] = None):
    client, col = connect_db()
    q = {'flight_id': flight_id}
    update = {'$set': {'status': status}}

    if status in ('processed', 'ortho generated') and research_station:
        crs = read_crs(flight_dir)
        ortho = os.path.join(research_station, 'flights', flight_id, 'odm_orthophoto', 'odm_orthophoto.tif')
        update['$set'].update({
            'orthophoto_path': ortho,
            'orthophoto_source_crs': crs
        })
        if status == 'processed':
            update['$set'].update({
                'cog_path': os.path.join(research_station, 'flights', flight_id, 'odm_orthophoto', 'odm_orthophoto_cog.tif'),
                'veg_index_folder': os.path.join(research_station, 'flights', flight_id, 'veg_indices'),
            })

    col.update_one(q, update, upsert=True)

def set_overall_status(fdir: str, fid: str, status: str, rs: str, dry_run: bool=False) -> None:
    if dry_run:
        return
    # utils.updateRecord handles audit/logging for you
    update_record(fdir, fid, status, rs)
