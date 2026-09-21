from fastapi import FastAPI

from job_processor_service.api.health import router as health_router
from job_processor_service.api.jobs import router as jobs_router
from job_processor_service.infrastructure.logging_utils import configure_logging

configure_logging()
app = FastAPI()
app.include_router(health_router)
app.include_router(jobs_router)
