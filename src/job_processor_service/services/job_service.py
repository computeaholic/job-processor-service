from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from job_processor_service.domain.exceptions import DomainError
from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState, validate_transition


class JobService:
    def create_job(self, session: Session) -> Job:
        with session.begin():
            job = Job(state=JobState.PENDING, version=0)
            session.add(job)
            session.flush()
            session.refresh(job)
            return job

    def transition_job(self, session: Session, job_id: UUID, target_state: JobState) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}")

            if job.state == target_state:
                return job

            validate_transition(job.state, target_state)
            current_version = job.version
            values: dict[str, JobState | str | int | None] = {
                "state": target_state,
                "version": current_version + 1,
            }
            if target_state is not JobState.FAILED:
                values["error_message"] = None

            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(**values)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}")
            return updated

    def fail_job(self, session: Session, job_id: UUID, message: str) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}")

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
                    error_message=message,
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}")
            return updated

    def retry_job(self, session: Session, job_id: UUID) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}")

            if job.state in {JobState.PENDING, JobState.DEAD}:
                return job

            target_state = (
                JobState.DEAD
                if job.retry_count >= job.max_retries
                else JobState.PENDING
            )
            validate_transition(job.state, target_state)

            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(
                    state=target_state,
                    error_message=None,
                    retry_count=(
                        job.retry_count + 1
                        if target_state == JobState.PENDING
                        else job.retry_count
                    ),
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}")
            return updated

    def record_processing_failure(
        self,
        session: Session,
        job_id: UUID,
        message: str,
    ) -> Job:
        with session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise DomainError(f"Job not found: {job_id}")

            if job.state in {JobState.FAILED, JobState.DEAD}:
                return job

            next_retry_count = job.retry_count + 1
            target_state = (
                JobState.DEAD
                if next_retry_count >= job.max_retries
                else JobState.FAILED
            )
            validate_transition(job.state, target_state)

            current_version = job.version
            result = session.execute(
                update(Job)
                .where(Job.id == job_id)
                .where(Job.version == current_version)
                .values(
                    state=target_state,
                    error_message=message,
                    retry_count=next_retry_count,
                    version=current_version + 1,
                )
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job_id)
            if updated is None:
                raise DomainError(f"Job not found: {job_id}")
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
                .where(Job.claimed_by.is_(None))
                .order_by(Job.created_at.asc())
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
                raise DomainError("VERSION_CONFLICT")

            session.flush()
            updated = session.get(Job, job.id)
            if updated is None:
                raise DomainError(f"Job not found: {job.id}")
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
                        version=current_version + 1,
                    )
                )
                if result.rowcount != 1:
                    raise DomainError("VERSION_CONFLICT")
                reclaimed += 1

            session.flush()
            return reclaimed
