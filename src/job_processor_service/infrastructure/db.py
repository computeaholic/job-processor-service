from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from job_processor_service.config.settings import Settings

settings = Settings()
if not settings.DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL must be a PostgreSQL SQLAlchemy URL")

engine = create_engine(settings.DATABASE_URL, future=True)


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
