from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def health_live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}
