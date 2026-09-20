from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.log(level, json.dumps(payload, default=str, sort_keys=True))