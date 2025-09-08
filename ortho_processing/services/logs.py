# services/logs.py
import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging import Logger
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Optional, Union

from config import config

# Attributes that are part of the standard LogRecord and should not be duplicated
_RESERVED_LOGRECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "process",
    "processName",
}


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter that merges `extra` fields safely."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any attributes added via LoggerAdapter(extra=...) or logger calls with extra=...
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_KEYS or key.startswith("_"):
                continue
            try:
                json.dumps(value)  # ensure serializable
                payload[key] = value
            except Exception:
                payload[key] = repr(value)

        if record.exc_info:
            try:
                payload["exc_info"] = self.formatException(record.exc_info)
            except Exception:
                payload["exc_info"] = "unprintable exception"

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _coerce_level(level: Optional[Union[str, int]]) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        return getattr(logging, level.upper(), logging.INFO)
    env = os.getenv("LOG_LEVEL")
    if env:
        return getattr(logging, env.upper(), logging.INFO)
    return logging.INFO


def setup_logging(
    log_file: Optional[str] = None,
    level: Optional[Union[str, int]] = None,
    to_console: bool = True,
    json_logs: Optional[bool] = None,
) -> None:
    """
    Configure the root logger.

    - Rotating file handler (every 30 days, keep a few backups)
    - Optional console handler (stderr)
    - JSON output by default (toggle with json_logs or $LOG_JSON)
    - Clears any existing handlers to avoid duplicate logs
    """
    if log_file is None:
        log_file = config["log_file"]

    # Decide JSON vs plaintext
    if json_logs is None:
        env = os.getenv("LOG_JSON")
        json_logs = (env or "true").lower() in {"1", "true", "yes", "y"}

    lvl = _coerce_level(level)

    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    root = logging.getLogger()
    # Remove existing handlers to avoid duplication across repeated setup calls
    for h in list(root.handlers):
        try:
            root.removeHandler(h)
            h.close()
        except Exception:
            pass

    root.setLevel(lvl)

    # File handler (rotate daily every 30 days)
    fh = TimedRotatingFileHandler(log_file, when="D", interval=30, backupCount=3)
    fh.setLevel(lvl)
    if json_logs:
        fh.setFormatter(JsonFormatter())
    else:
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    root.addHandler(fh)

    if to_console:
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setLevel(lvl)
        if json_logs:
            ch.setFormatter(JsonFormatter())
        else:
            ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
        root.addHandler(ch)


def get_logger(name: Optional[str] = None, **context: Any) -> Union[Logger, logging.LoggerAdapter]:
    """
    Get a logger. If context is provided, returns a LoggerAdapter that always
    includes those fields in the record via `extra=...`.
    """
    base = logging.getLogger(name)
    if context:
        return logging.LoggerAdapter(base, context)
    return base


def with_context(
    logger: Union[Logger, logging.LoggerAdapter],
    **context: Any,
) -> logging.LoggerAdapter:
    """
    Return a LoggerAdapter that merges the provided context with any existing context
    on the given logger.
    """
    if isinstance(logger, logging.LoggerAdapter):
        base = logger.logger
        merged = dict(getattr(logger, "extra", {}) or {})
        merged.update(context)
        return logging.LoggerAdapter(base, merged)
    return logging.LoggerAdapter(logger, context)
