from fastapi import APIRouter
from fastapi.responses import JSONResponse

from job_processor_service.infrastructure.db import readiness_status

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def health_live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def health_ready() -> JSONResponse:
    ready, reason = readiness_status()
    if ready:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready", "reason": reason})
