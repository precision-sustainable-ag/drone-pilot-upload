# services/geo.py
from __future__ import annotations

import os

import pyproj


def read_crs(flight_dir: str) -> str | None:
    """Return 'EPSG:xxxx' or None if not found."""
    crs_file = os.path.join(flight_dir, "odm_georeferencing", "proj.txt")
    try:
        with open(crs_file) as f:
            crs_string = f.readline().strip()
        epsg = pyproj.CRS.from_string(crs_string).to_epsg()
        return f"EPSG:{epsg}" if epsg else None
    except Exception:
        return None
