# services/logs.py
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from config import config


def setup_logging(log_file=None, level=logging.INFO, to_console=True):
    """
    Configure logging to both a rotating file and the console (stderr).
    Clears existing handlers to avoid duplicates and the FileHandler/StreamHandler
    inheritance gotcha.
    """
    if log_file is None:
        log_file = config["log_file"]

    log_folder = os.path.dirname(log_file) or "."
    os.makedirs(log_folder, exist_ok=True)

    root = logging.getLogger()
    # Remove existing handlers to avoid dupes and inheritance confusion

    for h in list(root.handlers):
        try:
            root.removeHandler(h)
            h.close()
        except Exception:
            pass

    root.setLevel(level)

    # File handler (rotating by date)
    fh = TimedRotatingFileHandler(log_file, when="D", interval=30)
    fh.setLevel(level)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler (to stderr)
    if to_console:
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        root.addHandler(ch)
