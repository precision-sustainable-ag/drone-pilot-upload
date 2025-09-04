# services/logs.py
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from config import config

def setup_logging():
    log_file = config['log_file']
    log_folder = os.path.dirname(log_file) or "."
    os.makedirs(log_folder, exist_ok=True)

    # root logger (idempotent: avoid duplicate handlers)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers):
        fh = TimedRotatingFileHandler(log_file, when='D', interval=30)
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root.addHandler(fh)

    # keep console output too (optional)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root.addHandler(ch)
