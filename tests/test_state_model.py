from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/job_processor"
)


def prepare_database(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", database_url)
    from job_processor_service.domain import models  # noqa: F401
    from job_processor_service.infrastructure.db import Base, SessionLocal, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.commit()


def test_valid_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        started = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    with SessionLocal() as session:
        succeeded = service.transition_job(session, created.id, JobState.SUCCEEDED)

    assert started is not None
    assert created.state is JobState.PENDING
    assert started.state is JobState.PROCESSING
    assert succeeded.state is JobState.SUCCEEDED


def test_version_increments_on_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        processing = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    with SessionLocal() as session:
        succeeded = service.transition_job(session, created.id, JobState.SUCCEEDED)

    assert processing is not None
    assert created.version == 0
    assert processing.version == 1
    assert succeeded.version == 2


def test_illegal_transition_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.main import app

    client = TestClient(app)
    created = client.post(
        "/jobs",
        json={
            "client_request_id": "11111111-1111-1111-1111-111111111111",
            "job_type": "sample.noop",
            "payload": {"value": "ok"},
            "max_retries": 3,
        },
    )
    job_id = created.json()["id"]

    response = client.post(f"/jobs/{job_id}/retry")

    assert created.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ILLEGAL_TRANSITION"


def test_claim_returns_single_job(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        oldest = service.create_job(session)

    with SessionLocal() as session:
        newest = service.create_job(session)

    with SessionLocal() as session:
        first_claim = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    with SessionLocal() as session:
        second_claim = service.claim_next_job(
            session, worker_id="worker-b", lease_seconds=30
        )

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim.id == oldest.id
    assert second_claim.id == newest.id


def test_future_next_run_at_job_is_not_claimable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        service.create_job(
            session, next_run_at=datetime.now(UTC) + timedelta(minutes=5)
        )

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is None


def test_eligible_next_run_at_job_is_claimable(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(
            session, next_run_at=datetime.now(UTC) - timedelta(seconds=1)
        )

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None
    assert claimed.id == created.id


def test_claim_skip_locked_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        first = service.create_job(session)

    with SessionLocal() as session:
        second = service.create_job(session)

    session_one = SessionLocal()
    try:
        with session_one.begin():
            now = datetime.now(UTC)
            query = (
                select(Job)
                .where(Job.state == JobState.PENDING)
                .where(Job.next_run_at <= now)
                .where(Job.claimed_by.is_(None))
                .order_by(Job.next_run_at.asc(), Job.created_at.asc(), Job.id.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            locked_job = session_one.execute(query).scalars().first()
            assert locked_job is not None
            assert locked_job.id == first.id

            locked_job.state = JobState.PROCESSING
            locked_job.claimed_by = "worker-a"
            locked_job.lease_expires_at = now + timedelta(seconds=30)
            locked_job.version += 1
            session_one.flush()

            with SessionLocal() as session_two:
                claimed_second = service.claim_next_job(
                    session_two,
                    worker_id="worker-b",
                    lease_seconds=30,
                )

            assert claimed_second is not None
            assert claimed_second.id == second.id
    finally:
        session_one.close()


def test_real_version_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        job_a = session_a.get(Job, created.id)
        job_b = session_b.get(Job, created.id)

        assert job_a is not None
        assert job_b is not None

        session_a.commit()
        session_b.commit()

        service.transition_job(session_b, created.id, JobState.SUCCEEDED)

        with pytest.raises(DomainError, match="VERSION_CONFLICT"):
            service.transition_job(session_a, created.id, JobState.SUCCEEDED)
    finally:
        session_a.close()
        session_b.close()


def test_claim_query_contains_skip_locked_postgresql() -> None:
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState

    query = (
        select(Job)
        .where(Job.state == JobState.PENDING)
        .where(Job.claimed_by.is_(None))
        .order_by(Job.next_run_at.asc(), Job.created_at.asc(), Job.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    compiled = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FOR UPDATE SKIP LOCKED" in compiled.upper()


def test_parallel_claim_no_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        for _ in range(5):
            service.create_job(session)

    claimed_ids: list[str] = []
    ids_lock = threading.Lock()

    def worker_claim(worker_idx: int) -> None:
        with SessionLocal() as session:
            claimed = service.claim_next_job(
                session,
                worker_id=f"worker-{worker_idx}",
                lease_seconds=30,
            )
            if claimed is not None:
                with ids_lock:
                    claimed_ids.append(str(claimed.id))

    threads = [threading.Thread(target=worker_claim, args=(idx,)) for idx in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed_ids) == 5
    assert len(set(claimed_ids)) == 5

    with SessionLocal() as session:
        claimed_jobs = list(
            session.execute(select(Job).where(Job.id.in_(claimed_ids))).scalars()
        )

    assert len(claimed_jobs) == 5
    assert all(job.state == JobState.PROCESSING for job in claimed_jobs)


def test_reclaim_expired_job(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None
    assert claimed.state is JobState.PROCESSING

    with SessionLocal() as session:
        with session.begin():
            job = session.get(Job, created.id)
            assert job is not None
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.add(job)

    reclaimed_before = datetime.now(UTC)
    with SessionLocal() as session:
        reclaimed_count = service.reclaim_expired_jobs(session)
    reclaimed_after = datetime.now(UTC)

    assert reclaimed_count == 1

    with SessionLocal() as session:
        reclaimed_job = session.get(Job, created.id)
        assert reclaimed_job is not None
        assert reclaimed_job.state is JobState.PENDING
        assert reclaimed_job.claimed_by is None
        assert reclaimed_job.lease_expires_at is None
        assert reclaimed_job.retry_count == 0
        assert reclaimed_before <= reclaimed_job.next_run_at <= reclaimed_after


def test_claim_returns_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is None


def test_compute_backoff_delay_first_retry() -> None:
    from job_processor_service.services.job_service import compute_backoff_delay

    assert compute_backoff_delay(1) == timedelta(seconds=5)


def test_compute_backoff_delay_doubles_deterministically() -> None:
    from job_processor_service.services.job_service import compute_backoff_delay

    assert compute_backoff_delay(2) == timedelta(seconds=10)
    assert compute_backoff_delay(3) == timedelta(seconds=20)


def test_compute_backoff_delay_caps_at_300_seconds() -> None:
    from job_processor_service.services.job_service import compute_backoff_delay

    assert compute_backoff_delay(7) == timedelta(seconds=300)
    assert compute_backoff_delay(8) == timedelta(seconds=300)


def test_retryable_failure_requeues_pending_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session, max_retries=3)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    failed_before = datetime.now(UTC)
    with SessionLocal() as session:
        retried = service.record_processing_failure(session, claimed.id, "boom\nline")
    failed_after = datetime.now(UTC)

    assert retried.state is JobState.PENDING
    assert retried.retry_count == 1
    assert retried.error_code == "JOB_PROCESSING_FAILED"
    assert retried.error_message == "boom line"
    assert retried.claimed_by is None
    assert retried.lease_expires_at is None
    assert retried.version == claimed.version + 1
    assert (
        failed_before + timedelta(seconds=5)
        <= retried.next_run_at
        <= failed_after + timedelta(seconds=5)
    )
    assert retried.id == created.id


def test_retryable_failure_exhausted_budget_reaches_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session, max_retries=1)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    with SessionLocal() as session:
        dead = service.record_processing_failure(session, claimed.id, "fatal")

    assert dead.id == created.id
    assert dead.state is JobState.DEAD
    assert dead.retry_count == 1
    assert dead.claimed_by is None
    assert dead.lease_expires_at is None


def test_non_retryable_failure_transitions_to_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    failed_before = datetime.now(UTC)
    with SessionLocal() as session:
        failed = service.record_processing_failure(
            session,
            claimed.id,
            "bad\nvalue",
            retryable=False,
            error_code="custom code",
        )
    failed_after = datetime.now(UTC)

    assert failed.id == created.id
    assert failed.state is JobState.FAILED
    assert failed.retry_count == 1
    assert failed.error_code == "CUSTOM_CODE"
    assert failed.error_message == "bad value"
    assert failed.claimed_by is None
    assert failed.lease_expires_at is None
    assert failed_before <= failed.next_run_at <= failed_after


def test_manual_retry_from_failed_preserves_retry_count_and_resets_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    with SessionLocal() as session:
        failed = service.record_processing_failure(
            session,
            created.id,
            "needs help",
            retryable=False,
            error_code="job failed",
        )

    retry_before = datetime.now(UTC)
    with SessionLocal() as session:
        retried = service.retry_job(session, created.id)
    retry_after = datetime.now(UTC)

    assert failed.state is JobState.FAILED
    assert retried.state is JobState.PENDING
    assert retried.retry_count == failed.retry_count
    assert retry_before <= retried.next_run_at <= retry_after
    assert retried.error_code is None
    assert retried.error_message is None
    assert retried.claimed_by is None
    assert retried.lease_expires_at is None


def test_dead_cannot_be_manually_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session, max_retries=1)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    with SessionLocal() as session:
        service.record_processing_failure(session, created.id, "fatal")

    with SessionLocal() as session:
        with pytest.raises(DomainError, match="Illegal transition: DEAD -> PENDING"):
            service.retry_job(session, created.id)


def test_version_conflict_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.domain.models import Job
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        job = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None

    with SessionLocal() as session:
        service.record_processing_failure(
            session,
            job.id,
            "manual",
            retryable=False,
            error_code="JOB_FAILED",
        )

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        job_a = session_a.get(Job, job.id)
        job_b = session_b.get(Job, job.id)

        assert job_a is not None
        assert job_b is not None

        session_a.commit()
        session_b.commit()

        service.retry_job(session_b, job.id)

        with pytest.raises(DomainError, match="VERSION_CONFLICT"):
            service.retry_job(session_a, job.id)
    finally:
        session_a.close()
        session_b.close()


def test_retry_from_pending_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        with pytest.raises(DomainError, match="Illegal transition: PENDING -> PENDING"):
            service.retry_job(session, created.id)
