from collections.abc import MutableMapping
from typing import Any

config: MutableMapping[str, Any] = {
    # 'flights_dir': '/rs1/shares/cals-research-station/sandhills/transfer'
    #                '/flights/',
    "mount_dir": "/rs1/shares/cals-research-station/",
    "code_dir": "/usr/local/usrapps/drones/drone-pilot-upload/",
    "log_file": "/usr/local/usrapps/drones/drone-pilot-upload/logs/cron_log.json",
    "reconcile_log_file": "/usr/local/usrapps/drones/drone-pilot-upload/logs/reconcile.log",
    "python_exec": "/usr/local/usrapps/drones/drone-pilot-upload/backend/venv/bin/python3",
    "scratch_dir": "/share/drones/hpc.drone.svc/tmp",
    # ODM job defaults
    "odm_image_limit": 300,
    "odm_long": {
        "queue": "gpu",
        "n_cores": 8,
        "wall": "30:00",
        "mem_gb": 250,
        "pc_quality": "medium",
        "sif_file": "sif_files/odm_gpu-fixed.sif",
        "compression": "LZW",
        "resolution": 0.01,
        "min_features": 10000,
    },
    "odm_short": {
        "queue": "short_gpu",
        "n_cores": 8,
        "wall": "2:00",
        "mem_gb": 250,
        "pc_quality": "medium",
        "sif_file": "sif_files/odm_gpu-fixed.sif",
        "compression": "LZW",
        "resolution": 0.01,
        "min_features": 10000,
    },
    # Ortho Intel job defaults
    "ortho_intel": {
        "queue": "serial",
        "n_cores": 1,
        "wall": "10:00",
        "sif_file": "sif_files/drone_ortho_intel.sif",
    },
    "database_details": {
        "host": "<host>",
        "username": "<user>",
        "password": "<pass>",
        "database": "<db>",
        "auth_source": "<auth source>",
        "collection": "<collection>",
        "auth_mechanism": "<auth mech>",
        "connection_string": "<conn string>",
    },
}
