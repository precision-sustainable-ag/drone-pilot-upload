# services/geo.py
from typing import Optional
import os
import pyproj

def read_crs(flight_dir: str) -> Optional[str]:
    """Return 'EPSG:xxxx' or None if not found."""
    crs_file = os.path.join(flight_dir, 'odm_georeferencing', 'proj.txt')
    try:
        with open(crs_file, 'r') as f:
            crs_string = f.readline().strip()
        epsg = pyproj.CRS.from_string(crs_string).to_epsg()
        return f"EPSG:{epsg}" if epsg else None
    except Exception:
        return None
