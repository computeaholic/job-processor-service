from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError


def test_configure_logging_is_idempotent() -> None:
    from job_processor_service.infrastructure.logging_utils import configure_logging

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    try:
        configure_logging()
        configured_handlers = list(root_logger.handlers)

        assert configured_handlers
        assert isinstance(configured_handlers[0], logging.StreamHandler)

        configure_logging()

        assert root_logger.handlers == configured_handlers
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
        for handler in original_handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(original_level)


def test_log_event_emits_json(caplog: object) -> None:
    from job_processor_service.infrastructure.logging_utils import log_event

    logger = logging.getLogger("job_processor_service.tests.logging")

    caplog.set_level(logging.INFO, logger=logger.name)
    log_event(logger, logging.INFO, "job.test", job_id="abc", retry_count=2)

    payload = json.loads(caplog.records[0].message)
    assert payload == {"event": "job.test", "job_id": "abc", "retry_count": 2}


def test_readiness_status_reports_database_unavailable(monkeypatch: object) -> None:
    from job_processor_service.infrastructure import db

    class BrokenEngine:
        def connect(self) -> None:
            raise SQLAlchemyError()

    monkeypatch.setattr(db, "engine", BrokenEngine())

    assert db.readiness_status() == (False, "database unavailable")


def test_readiness_status_reports_migration_mismatch(monkeypatch: object) -> None:
    from job_processor_service.infrastructure import db

    class ReadyConnection:
        def __enter__(self) -> ReadyConnection:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def execute(self, _statement: object) -> None:
            return None

    class ReadyEngine:
        def connect(self) -> ReadyConnection:
            return ReadyConnection()

    monkeypatch.setattr(db, "engine", ReadyEngine())
    monkeypatch.setattr(db, "current_migration_revision", lambda: "0001")
    monkeypatch.setattr(db, "expected_migration_revision", lambda: "0002")

    assert db.readiness_status() == (False, "migrations not current")