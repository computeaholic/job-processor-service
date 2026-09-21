from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    WORKER_ID: str | None = None
    LEASE_TTL_SECONDS: int = 30
    POLL_INTERVAL_SECONDS: float = 0.5
