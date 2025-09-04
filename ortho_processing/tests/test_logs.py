# tests/test_logs.py
import logging
from services.logs import setup_logging

def test_setup_logging_creates_file(monkeypatch, tmp_path, patch_config):
    logf = tmp_path / "t.log"
    # Temporarily force a custom path if your setup_logging reads config['log_file']
    from config import config as cfg
    old = cfg["log_file"]
    cfg["log_file"] = str(logf)
    try:
        setup_logging()
        logging.getLogger().info("hello")
        assert logf.exists()
    finally:
        cfg["log_file"] = old
