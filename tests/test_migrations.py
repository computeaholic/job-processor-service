from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/job_processor"
)


def migration_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def reset_database(database_url: str) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def test_alembic_upgrade_and_downgrade(monkeypatch: object) -> None:
    database_url = os.getenv("DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", database_url)
    from sqlalchemy import create_engine

    reset_database(database_url)
    config = migration_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    assert "jobs" in inspector.get_table_names()
    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    assert {
        "id",
        "client_request_id",
        "job_type",
        "payload",
        "state",
        "error_code",
        "error_message",
        "claimed_by",
        "lease_expires_at",
        "version",
        "retry_count",
        "max_retries",
        "next_run_at",
        "created_at",
        "updated_at",
    } <= job_columns

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert revision == "0001_jobs_baseline"

    command.downgrade(config, "base")

    inspector = inspect(engine)
    assert "jobs" not in inspector.get_table_names()

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert "jobs" in inspector.get_table_names()