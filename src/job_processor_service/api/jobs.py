from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from job_processor_service.domain.exceptions import DomainError
from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState
from job_processor_service.infrastructure.db import SessionLocal
from job_processor_service.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = JobService()


class FailRequest(BaseModel):
    message: str


class ClaimRequest(BaseModel):
    worker_id: str
    lease_seconds: int


def job_envelope(job: Job) -> dict[str, str | int | None]:
    lease_expires_at = (
        job.lease_expires_at.isoformat() if job.lease_expires_at is not None else None
    )
    return {
        "id": str(job.id),
        "state": job.state.value,
        "version": job.version,
        "claimed_by": job.claimed_by,
        "lease_expires_at": lease_expires_at,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
    }


def success_response(job: Job) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_200_OK, content=job_envelope(job))


def transition_conflict(error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "ILLEGAL_STATE_TRANSITION",
                "message": str(error),
            }
        },
    )


@router.post("")
def create_job() -> JSONResponse:
    with SessionLocal() as session:
        job = service.create_job(session)
        return success_response(job)


@router.post("/{id}/retry")
def retry_job(id: UUID) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.retry_job(session, id)
            return success_response(job)
        except DomainError as error:
            return transition_conflict(error)


@router.post("/{id}/start")
def start_job(id: UUID) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.transition_job(session, id, JobState.PROCESSING)
            return success_response(job)
        except DomainError as error:
            return transition_conflict(error)


@router.post("/{id}/succeed")
def succeed_job(id: UUID) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.transition_job(session, id, JobState.SUCCEEDED)
            return success_response(job)
        except DomainError as error:
            return transition_conflict(error)


@router.post("/{id}/fail")
def fail_job(id: UUID, payload: FailRequest) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.fail_job(session, id, payload.message)
            return success_response(job)
        except DomainError as error:
            return transition_conflict(error)


@router.post("/claim")
def claim_job(payload: ClaimRequest) -> JSONResponse:
    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session,
            worker_id=payload.worker_id,
            lease_seconds=payload.lease_seconds,
        )
        if claimed is None:
            return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
        return success_response(claimed)


@router.post("/reclaim-expired")
def reclaim_expired_jobs() -> JSONResponse:
    with SessionLocal() as session:
        reclaimed = service.reclaim_expired_jobs(session)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"reclaimed": reclaimed})
