from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from job_processor_service.config.settings import Settings

settings = Settings()  # type: ignore[call-arg]
if not settings.DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL must be a PostgreSQL SQLAlchemy URL")

engine = create_engine(settings.DATABASE_URL, future=True)
REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = REPO_ROOT / "alembic"


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def expected_migration_revision() -> str:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Alembic head revision not found")
    return head


def current_migration_revision() -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def readiness_status() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False, "database unavailable"

    try:
        current = current_migration_revision()
        expected = expected_migration_revision()
    except SQLAlchemyError:
        return False, "migrations not initialized"

    if current != expected:
        return False, "migrations not current"

    return True, "ready"
