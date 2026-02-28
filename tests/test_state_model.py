import os
import threading

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
        started = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        succeeded = service.transition_job(session, created.id, JobState.SUCCEEDED)

    assert created.state is JobState.PENDING
    assert started.state is JobState.PROCESSING
    assert succeeded.state is JobState.SUCCEEDED
    assert created.version == 0
    assert started.version == 1
    assert succeeded.version == 2


def test_version_increments_on_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        processing = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        succeeded = service.transition_job(session, created.id, JobState.SUCCEEDED)

    assert created.version == 0
    assert processing.version == 1
    assert succeeded.version == 2


def test_illegal_transition_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.main import app

    client = TestClient(app)

    created = client.post("/jobs")
    job_id = created.json()["id"]

    response = client.post(f"/jobs/{job_id}/succeed")

    assert created.status_code == 200
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "ILLEGAL_STATE_TRANSITION",
            "message": "Illegal transition: PENDING -> SUCCEEDED",
        }
    }


def test_retry_from_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        failed = service.fail_job(session, created.id, "boom")

    with SessionLocal() as session:
        retried = service.retry_job(session, created.id)

    assert failed.state is JobState.FAILED
    assert failed.error_message == "boom"
    assert retried.state is JobState.PENDING
    assert retried.error_message is None
    assert retried.version == failed.version + 1


def test_cannot_transition_from_succeeded(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        service.transition_job(session, created.id, JobState.SUCCEEDED)

    with SessionLocal() as session:
        with pytest.raises(DomainError, match="Illegal transition: SUCCEEDED -> PROCESSING"):
            service.transition_job(session, created.id, JobState.PROCESSING)


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
        first_claim = service.claim_next_job(session, worker_id="worker-a", lease_seconds=30)

    with SessionLocal() as session:
        second_claim = service.claim_next_job(session, worker_id="worker-b", lease_seconds=30)

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim.id == oldest.id
    assert second_claim.id == newest.id


def test_claim_skip_locked_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from datetime import UTC, datetime, timedelta

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
            query = (
                select(Job)
                .where(Job.state == JobState.PENDING)
                .where(Job.claimed_by.is_(None))
                .order_by(Job.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            locked_job = session_one.execute(query).scalars().first()
            assert locked_job is not None
            assert locked_job.id == first.id

            locked_job.state = JobState.PROCESSING
            locked_job.claimed_by = "worker-a"
            locked_job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
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

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        job_a = session_a.get(Job, created.id)
        job_b = session_b.get(Job, created.id)

        assert job_a is not None
        assert job_b is not None

        session_a.commit()
        session_b.commit()

        service.transition_job(session_b, created.id, JobState.PROCESSING)

        with pytest.raises(DomainError, match="VERSION_CONFLICT"):
            service.transition_job(session_a, created.id, JobState.PROCESSING)
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
        .order_by(Job.created_at.asc())
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


def test_version_conflict_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.exceptions import DomainError
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        job = service.create_job(session)

    with SessionLocal() as session:
        service.transition_job(session, job.id, JobState.PROCESSING)
        service.transition_job(session, job.id, JobState.FAILED)

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


def test_reclaim_expired_job(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from datetime import UTC, datetime, timedelta

    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(session, worker_id="worker-a", lease_seconds=30)

    assert claimed is not None
    assert claimed.state is JobState.PROCESSING

    with SessionLocal() as session:
        with session.begin():
            job = session.get(Job, created.id)
            assert job is not None
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.add(job)

    with SessionLocal() as session:
        reclaimed_count = service.reclaim_expired_jobs(session)

    assert reclaimed_count == 1

    with SessionLocal() as session:
        reclaimed_job = session.get(Job, created.id)
        assert reclaimed_job is not None
        assert reclaimed_job.state is JobState.PENDING
        assert reclaimed_job.claimed_by is None
        assert reclaimed_job.lease_expires_at is None


def test_claim_returns_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        claimed = service.claim_next_job(session, worker_id="worker-a", lease_seconds=30)

    assert claimed is None


def test_retry_until_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        processing = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        failed_1 = service.record_processing_failure(session, processing.id, "fail-1")

    with SessionLocal() as session:
        pending_1 = service.retry_job(session, created.id)

    with SessionLocal() as session:
        processing_2 = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        dead = service.record_processing_failure(session, processing_2.id, "fail-2")

    with SessionLocal() as session:
        dead_retry = service.retry_job(session, created.id)

    assert failed_1.state is JobState.FAILED
    assert failed_1.retry_count == 1
    assert pending_1.state is JobState.PENDING
    assert pending_1.retry_count == 2
    assert dead.state is JobState.DEAD
    assert dead.retry_count == 3
    assert dead_retry.state is JobState.DEAD
    assert dead_retry.retry_count == 3


def test_dead_is_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
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
        with session.begin():
            created_model = session.get(Job, created.id)
            assert created_model is not None
            created_model.max_retries = 1
            session.add(created_model)

    with SessionLocal() as session:
        processing = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        dead = service.record_processing_failure(session, processing.id, "terminal")

    with SessionLocal() as session:
        with pytest.raises(DomainError, match="Illegal transition: DEAD -> PROCESSING"):
            service.transition_job(session, dead.id, JobState.PROCESSING)

    assert dead.state is JobState.DEAD


def test_retry_count_increments_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        processing = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        failed = service.record_processing_failure(session, processing.id, "boom")

    with SessionLocal() as session:
        pending = service.retry_job(session, created.id)

    assert failed.retry_count == 1
    assert pending.retry_count == 2


def test_retry_idempotent_no_double_increment(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        processing = service.transition_job(session, created.id, JobState.PROCESSING)

    with SessionLocal() as session:
        failed = service.record_processing_failure(session, processing.id, "boom")

    with SessionLocal() as session:
        first_retry = service.retry_job(session, created.id)

    with SessionLocal() as session:
        second_retry = service.retry_job(session, created.id)

    assert failed.retry_count == 1
    assert first_retry.retry_count == 2
    assert second_retry.retry_count == first_retry.retry_count
