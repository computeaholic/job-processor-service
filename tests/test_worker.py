from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Callable

import pytest
from sqlalchemy import select

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/job_processor"
)


def prepare_database(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", database_url)
    from job_processor_service.infrastructure.db import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_worker_processes_job_success(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    worker = Worker(worker_id="worker-success", lease_seconds=30)
    processed = worker.run_once()

    assert processed is True

    with SessionLocal() as session:
        updated = session.get(Job, created.id)

    assert updated is not None
    assert updated.state == JobState.SUCCEEDED


def test_worker_retryable_failure_requeues(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    def failing_callback(_job: Job) -> None:
        raise ValueError("callback failure")

    worker = Worker(
        worker_id="worker-fail",
        lease_seconds=30,
        work_callback=failing_callback,
    )
    before_failure = datetime.now(UTC)
    processed = worker.run_once()
    after_failure = datetime.now(UTC)

    assert processed is True

    with SessionLocal() as session:
        updated = session.get(Job, created.id)

    assert updated is not None
    assert updated.state == JobState.PENDING
    assert updated.error_code == "JOB_PROCESSING_FAILED"
    assert updated.error_message == "callback failure"
    assert updated.retry_count == 1
    assert updated.claimed_by is None
    assert updated.lease_expires_at is None
    assert before_failure < updated.next_run_at <= after_failure + timedelta(seconds=5)


def test_worker_non_retryable_failure_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.exceptions import NonRetryableJobError
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    def failing_callback(_job: Job) -> None:
        raise NonRetryableJobError("unsupported type", code="JOB_TYPE_UNSUPPORTED")

    worker = Worker(
        worker_id="worker-fail-non-retryable",
        lease_seconds=30,
        work_callback=failing_callback,
    )
    processed = worker.run_once()

    assert processed is True

    with SessionLocal() as session:
        updated = session.get(Job, created.id)

    assert updated is not None
    assert updated.state == JobState.FAILED
    assert updated.error_code == "JOB_TYPE_UNSUPPORTED"
    assert updated.error_message == "unsupported type"


def test_worker_no_jobs_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.services.worker import Worker

    worker = Worker(worker_id="worker-empty", lease_seconds=30)

    assert worker.run_once() is False


def test_worker_parallel_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    total_jobs = 8

    with SessionLocal() as session:
        for _ in range(total_jobs):
            service.create_job(session)

    processed_ids: list[str] = []
    processed_lock = threading.Lock()
    worker_errors: list[Exception] = []
    error_lock = threading.Lock()

    def make_callback() -> Callable[[Job], None]:
        def callback(job: Job) -> None:
            with processed_lock:
                processed_ids.append(str(job.id))

        return callback

    def run_worker(worker_idx: int) -> None:
        worker = Worker(
            worker_id=f"worker-{worker_idx}",
            lease_seconds=30,
            work_callback=make_callback(),
        )
        try:
            worker.run_once()
        except Exception as exc:
            with error_lock:
                worker_errors.append(exc)

    threads = [
        threading.Thread(target=run_worker, args=(idx,)) for idx in range(total_jobs)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not worker_errors
    assert len(processed_ids) == total_jobs
    assert len(set(processed_ids)) == total_jobs

    with SessionLocal() as session:
        jobs = list(session.execute(select(Job)).scalars())

    assert len(jobs) == total_jobs
    assert all(job.state == JobState.SUCCEEDED for job in jobs)
    assert all(job.version == 2 for job in jobs)


def test_worker_escalates_to_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        with session.begin():
            model = session.get(Job, created.id)
            assert model is not None
            model.max_retries = 1
            session.add(model)

    def failing_callback(_job: Job) -> None:
        raise RuntimeError("fatal")

    worker = Worker(
        worker_id="worker-dead",
        lease_seconds=30,
        work_callback=failing_callback,
    )
    processed = worker.run_once()

    assert processed is True

    with SessionLocal() as session:
        updated = session.get(Job, created.id)

    assert updated is not None
    assert updated.state == JobState.DEAD
    assert updated.retry_count == 1


def test_run_forever_respects_pre_set_stop_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    stop_event = Event()
    stop_event.set()
    worker = Worker(worker_id="worker-stop", lease_seconds=30, poll_interval_seconds=0)
    worker.run_forever(stop_event)

    with SessionLocal() as session:
        updated = session.get(Job, created.id)

    assert updated is not None
    assert updated.state == JobState.PENDING


def test_run_forever_finishes_inflight_before_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService
    from job_processor_service.services.worker import Worker

    service = JobService()
    with SessionLocal() as session:
        first = service.create_job(session)
        second = service.create_job(session)

    processed_ids: list[str] = []
    stop_event = Event()

    def callback(job: Job) -> None:
        processed_ids.append(str(job.id))
        stop_event.set()

    worker = Worker(
        worker_id="worker-shutdown",
        lease_seconds=30,
        work_callback=callback,
        poll_interval_seconds=0,
    )
    worker.run_forever(stop_event)

    with SessionLocal() as session:
        first_job = session.get(Job, first.id)
        second_job = session.get(Job, second.id)

    assert processed_ids == [str(first.id)]
    assert first_job is not None
    assert second_job is not None
    assert first_job.state == JobState.SUCCEEDED
    assert second_job.state == JobState.PENDING
