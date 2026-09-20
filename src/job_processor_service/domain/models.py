from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from job_processor_service.infrastructure.db import Base
from job_processor_service.domain.state_machine import JobState


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="ck_jobs_retry_count_non_negative"),
        CheckConstraint("max_retries >= 1", name="ck_jobs_max_retries_positive"),
        CheckConstraint(
            "(state = 'PROCESSING' AND claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (state <> 'PROCESSING' AND claimed_by IS NULL AND lease_expires_at IS NULL)",
            name="ck_jobs_processing_claim_consistency",
        ),
        Index("ix_jobs_pending_claim", "state", "claimed_by", "created_at"),
        Index("ix_jobs_processing_lease", "state", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_request_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        unique=True,
    )
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, native_enum=False),
        nullable=False,
        default=JobState.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
