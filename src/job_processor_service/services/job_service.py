from __future__ import annotations

import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from job_processor_service.domain.exceptions import DomainError
from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState, validate_transition
from job_processor_service.infrastructure.logging_utils import log_event

logger = logging.getLogger(__name__)

DEFAULT_JOB_TYPE = "sample.noop"
BASE_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 300
MAX_ERROR_CODE_LENGTH = 64
MAX_ERROR_MESSAGE_LENGTH = 512


@dataclass(frozen=True, slots=True)
class CreateJobResult:
    job: Job
    created: bool

    def __getattr__(self, name: str) -> object:
        return getattr(self.job, name)


def compute_backoff_delay(retry_count: int) -> timedelta:
    if retry_count < 1:
        raise ValueError("retry_count must be >= 1")
    delay_seconds = min(
        BASE_BACKOFF_SECONDS * 2 ** (retry_count - 1),
        MAX_BACKOFF_SECONDS,
    )
    return timedelta(seconds=delay_seconds)


class JobService:
    def create_job(
        self,
        session: Session,
        *,
        client_request_id: UUID | None = None,
        job_type: str = DEFAULT_JOB_TYPE,
        payload: dict[str, Any] | None = None,
        max_retries: int = 3,
        next_run_at: datetime | None = None,
    ) -> CreateJobResult:
        normalized_job_type = self._normalize_job_type(job_type)
        normalized_payload = self._normalize_payload(payload)
        scheduled_for = next_run_at or datetime.now(UTC)

        try:
            with session.begin():
                if client_request_id is not None:
                    existing = self._get_by_client_request_id(
                        session, client_request_id
                    )
                    if existing is not None:
                        self._validate_create_replay(
                            existing,
                            job_type=normalized_job_type,
                            payload=normalized_payload,
                            max_retries=max_retries,
                        )
                        return CreateJobResult(job=existing, created=False)

                job = Job(
                    client_request_id=client_request_id,
                    job_type=normalized_job_type,
                    payload=normalized_payload,
                    state=JobState.PENDING,
                    version=0,
                    max_retries=max_retries,
                    next_run_at=scheduled_for,
                )
                session.add(job)
                session.flush()
                session.refresh(job)
                log_event(
                    logger,
                    logging.INFO,
                    "job.created",
                    job_id=job.id,
                    client_request_id=job.client_request_id,
                    job_type=job.job_type,
                    max_retries=job.max_retries,
                )
                return CreateJobResult(job=job, created=True)
        except IntegrityError as error:
            session.rollback()
            if client_request_id is None:
                raise error

            existing = self._get_by_client_request_id(session, client_request_id)
            if existing is None:
                raise error

            self._validate_create_replay(
                existing,
                job_type=normalized_job_type,
                payload=normalized_payload,
                max_retries=max_retries,
            )
            log_event(
                logger,
                logging.INFO,
                "job.create_replayed",
                job_id=existing.id,
                client_request_id=existing.client_request_id,
            )
            return CreateJobResult(job=existing, created=False)

    def get_job(self, session: Session, job_id: UUID) -> Job:
        job = session.get(Job, job_id)
        if job is None:
            raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")
        return job

    def list_jobs(
        self,
        session: Session,
        state: JobState | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        query = select(Job).order_by(
            Job.next_run_at.asc(),
            Job.created_at.asc(),
            Job.id.asc(),
        )
        if state is not None:
            query = query.where(Job.state == state)
        query = query.limit(limit).offset(offset)
        return list(session.execute(query).scalars())

    def transition_job(
        self, session: Session, job_id: UUID, target_state: JobState
    ) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")

            if job.state == target_state:
                return job

            validate_transition(job.state, target_state)
            current_version = job.version
            values: dict[str, JobState | str | int | datetime | None] = {
                "state": target_state,
                "version": current_version + 1,
            }
            if target_state is not JobState.FAILED:
                values["error_code"] = None
                values["error_message"] = None
            if target_state is not JobState.PROCESSING:
                values["claimed_by"] = None
                values["lease_expires_at"] = None

            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(**values)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")
            log_event(
                logger,
                logging.INFO,
                "job.transitioned",
                job_id=updated.id,
                state=updated.state.value,
                version=updated.version,
            )
            return updated

    def fail_job(self, session: Session, job_id: UUID, message: str) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")

            if job.state == JobState.FAILED:
                return job

            validate_transition(job.state, JobState.FAILED)
            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(
                    state=JobState.FAILED,
                    error_code=self._sanitize_error_code("JOB_NON_RETRYABLE_FAILURE"),
                    error_message=self._sanitize_error_message(message),
                    claimed_by=None,
                    lease_expires_at=None,
                    next_run_at=datetime.now(UTC),
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")
            log_event(
                logger,
                logging.WARNING,
                "job.failed",
                job_id=updated.id,
                state=updated.state.value,
                error_code=updated.error_code,
                version=updated.version,
            )
            return updated

    def retry_job(self, session: Session, job_id: UUID) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")

            validate_transition(job.state, JobState.PENDING)

            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(
                    state=JobState.PENDING,
                    error_code=None,
                    error_message=None,
                    claimed_by=None,
                    lease_expires_at=None,
                    next_run_at=datetime.now(UTC),
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")
            log_event(
                logger,
                logging.INFO,
                "job.retried",
                job_id=updated.id,
                state=updated.state.value,
                retry_count=updated.retry_count,
                version=updated.version,
            )
            return updated

    def record_processing_failure(
        self,
        session: Session,
        job_id: UUID,
        message: str,
        *,
        retryable: bool = True,
        error_code: str = "JOB_PROCESSING_FAILED",
    ) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")

            if job.state in {JobState.FAILED, JobState.DEAD}:
                return job

            now = datetime.now(UTC)
            next_retry_count = job.retry_count + 1
            if retryable:
                target_state = (
                    JobState.DEAD
                    if next_retry_count >= job.max_retries
                    else JobState.PENDING
                )
                scheduled_for = (
                    now
                    if target_state is JobState.DEAD
                    else now + compute_backoff_delay(next_retry_count)
                )
            else:
                target_state = JobState.FAILED
                scheduled_for = now

            validate_transition(job.state, target_state)

            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(
                    state=target_state,
                    error_code=self._sanitize_error_code(error_code),
                    error_message=self._sanitize_error_message(message),
                    retry_count=next_retry_count,
                    claimed_by=None,
                    lease_expires_at=None,
                    next_run_at=scheduled_for,
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}", code="JOB_NOT_FOUND")
            log_event(
                logger,
                (
                    logging.WARNING
                    if updated.state in {JobState.FAILED, JobState.DEAD}
                    else logging.INFO
                ),
                "job.processing_failed",
                job_id=updated.id,
                state=updated.state.value,
                error_code=updated.error_code,
                retry_count=updated.retry_count,
                version=updated.version,
            )
            return updated

    def claim_next_job(
        self,
        session: Session,
        worker_id: str,
        lease_seconds: int,
    ) -> Job | None:
        with session.begin():
            now = datetime.now(UTC)
            owned_query = (
                select(Job)
                .where(Job.state == JobState.PROCESSING)
                .where(Job.claimed_by == worker_id)
                .where(Job.lease_expires_at.is_not(None))
                .where(Job.lease_expires_at > now)
                .order_by(Job.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            owned_job = session.execute(owned_query).scalars().first()
            if owned_job is not None:
                owned_guard = session.execute(
                    select(Job.id)
                    .where(Job.id == owned_job.id)
                    .where(Job.claimed_by == worker_id)
                    .where(Job.lease_expires_at.is_not(None))
                    .where(Job.lease_expires_at > now)
                ).scalar_one_or_none()
                if owned_guard is not None:
                    return owned_job

            query = (
                select(Job)
                .where(Job.state == JobState.PENDING)
                .where(Job.next_run_at <= now)
                .where(Job.claimed_by.is_(None))
                .order_by(Job.next_run_at.asc(), Job.created_at.asc(), Job.id.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = session.execute(query).scalars().first()
            if job is None:
                return None

            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job.id)
                .where(Job.version == current_version)
                .where(Job.state == JobState.PENDING)
                .where(Job.claimed_by.is_(None))
                .values(
                    state=JobState.PROCESSING,
                    claimed_by=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job.id)
            if updated is None:
                raise DomainError(f"Job not found: {job.id}", code="JOB_NOT_FOUND")
            log_event(
                logger,
                logging.INFO,
                "job.claimed",
                job_id=updated.id,
                worker_id=worker_id,
                lease_expires_at=updated.lease_expires_at,
                version=updated.version,
            )
            return updated

    def reclaim_expired_jobs(self, session: Session) -> int:
        with session.begin():
            now = datetime.now(UTC)
            query = (
                select(Job)
                .where(Job.state == JobState.PROCESSING)
                .where(Job.lease_expires_at.is_not(None))
                .where(Job.lease_expires_at < now)
                .with_for_update(skip_locked=True)
            )
            jobs = list(session.execute(query).scalars())

            reclaimed = 0
            for job in jobs:
                current_version = job.version
                result = session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .where(Job.version == current_version)
                    .values(
                        state=JobState.PENDING,
                        claimed_by=None,
                        lease_expires_at=None,
                        next_run_at=now,
                        version=current_version + 1,
                    )
                )
                if result.rowcount != 1:
                    raise DomainError("VERSION_CONFLICT", code="VERSION_CONFLICT")
                log_event(
                    logger,
                    logging.WARNING,
                    "job.reclaimed",
                    job_id=job.id,
                    worker_id=job.claimed_by,
                )
                reclaimed += 1

            session.flush()
            return reclaimed

    def _get_by_client_request_id(
        self,
        session: Session,
        client_request_id: UUID,
    ) -> Job | None:
        return session.execute(
            select(Job).where(Job.client_request_id == client_request_id)
        ).scalar_one_or_none()

    def _validate_create_replay(
        self,
        existing: Job,
        *,
        job_type: str,
        payload: dict[str, Any],
        max_retries: int,
    ) -> None:
        if (
            existing.job_type != job_type
            or existing.payload != payload
            or existing.max_retries != max_retries
        ):
            raise DomainError(
                "client_request_id already used for a different create request",
                code="JOB_IDEMPOTENCY_CONFLICT",
            )

    def _normalize_job_type(self, job_type: str) -> str:
        normalized = job_type.strip()
        if not normalized:
            raise DomainError("job_type must not be blank", code="VALIDATION_ERROR")
        return normalized

    def _normalize_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if payload is None:
            return {}
        return deepcopy(payload)

    def _sanitize_error_code(self, error_code: str) -> str:
        sanitized = re.sub(r"[^A-Z0-9_]+", "_", error_code.upper()).strip("_")
        return (sanitized or "JOB_PROCESSING_FAILED")[:MAX_ERROR_CODE_LENGTH]

    def _sanitize_error_message(self, message: str) -> str:
        sanitized = re.sub(r"[\x00-\x1f\x7f]+", " ", message)
        collapsed = " ".join(sanitized.split())
        return (collapsed or "Processing failed")[:MAX_ERROR_MESSAGE_LENGTH]
