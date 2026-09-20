from uuid import UUID

from fastapi import APIRouter, Body, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from job_processor_service.domain.exceptions import DomainError
from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState
from job_processor_service.infrastructure.db import SessionLocal
from job_processor_service.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = JobService()


class CreateJobRequest(BaseModel):
    client_request_id: UUID | None = None
    max_retries: int = Field(default=3, ge=1)


def job_envelope(job: Job) -> dict[str, str | int | None]:
    lease_expires_at = (
        job.lease_expires_at.isoformat() if job.lease_expires_at is not None else None
    )
    created_at = job.created_at.isoformat()
    updated_at = job.updated_at.isoformat()
    return {
        "id": str(job.id),
        "client_request_id": (
            str(job.client_request_id) if job.client_request_id is not None else None
        ),
        "state": job.state.value,
        "error_message": job.error_message,
        "version": job.version,
        "claimed_by": job.claimed_by,
        "lease_expires_at": lease_expires_at,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def success_response(job: Job, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=job_envelope(job))


def error_response(error: DomainError) -> JSONResponse:
    status_code = status.HTTP_409_CONFLICT
    if error.code == "JOB_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif error.code not in {
        "JOB_ILLEGAL_TRANSITION",
        "JOB_IDEMPOTENCY_CONFLICT",
        "VERSION_CONFLICT",
    }:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error.code,
                "message": str(error),
            }
        },
    )


@router.post("")
def create_job(
    payload: CreateJobRequest = Body(default_factory=CreateJobRequest),
) -> JSONResponse:
    with SessionLocal() as session:
        try:
            result = service.create_job(
                session,
                client_request_id=payload.client_request_id,
                max_retries=payload.max_retries,
            )
        except DomainError as error:
            return error_response(error)

        status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return success_response(result.job, status_code=status_code)


@router.get("")
def list_jobs(state: JobState | None = Query(default=None)) -> JSONResponse:
    with SessionLocal() as session:
        jobs = service.list_jobs(session, state=state)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=[job_envelope(job) for job in jobs],
        )


@router.get("/{id}")
def get_job(id: UUID) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.get_job(session, id)
            return success_response(job)
        except DomainError as error:
            return error_response(error)


@router.post("/{id}/retry")
def retry_job(id: UUID) -> JSONResponse:
    with SessionLocal() as session:
        try:
            job = service.retry_job(session, id)
            return success_response(job)
        except DomainError as error:
            return error_response(error)
