# passenger_wsgi.py
import sys
import os

# Path to the venv created with Python 3.9
venv_path = "/usr/local/usrapps/drones/mspinega/drone-pilot-upload/backend/venv"
site_packages = os.path.join(venv_path, "lib/python3.9/site-packages")

# Update Python path and env
sys.path.insert(0, site_packages)
sys.path.insert(0, "/usr/local/usrapps/drones/mspinega/drone-pilot-upload/backend")
os.environ["VIRTUAL_ENV"] = venv_path
os.environ["PATH"] = os.path.join(venv_path, "bin") + ":" + os.environ["PATH"]

# Import your app
from app import app as application
