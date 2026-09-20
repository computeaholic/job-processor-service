"""jobs baseline

Revision ID: 0001_jobs_baseline
Revises:
Create Date: 2026-09-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_jobs_baseline"
down_revision = None
branch_labels = None
depends_on = None


job_state_enum = sa.Enum(
    "PENDING",
    "PROCESSING",
    "SUCCEEDED",
    "FAILED",
    "DEAD",
    name="jobstate",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", job_state_enum, nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("retry_count >= 0", name="ck_jobs_retry_count_non_negative"),
        sa.CheckConstraint("max_retries >= 1", name="ck_jobs_max_retries_positive"),
        sa.CheckConstraint(
            "(state = 'PROCESSING' AND claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (state <> 'PROCESSING' AND claimed_by IS NULL AND lease_expires_at IS NULL)",
            name="ck_jobs_processing_claim_consistency",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_request_id"),
    )
    op.create_index(
        "ix_jobs_pending_claim",
        "jobs",
        ["state", "claimed_by", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_processing_lease",
        "jobs",
        ["state", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_processing_lease", table_name="jobs")
    op.drop_index("ix_jobs_pending_claim", table_name="jobs")
    op.drop_table("jobs")