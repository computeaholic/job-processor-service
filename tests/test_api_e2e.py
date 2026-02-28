from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

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
    from job_processor_service.infrastructure.db import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_client() -> TestClient:
    from job_processor_service.main import app

    return TestClient(app)


def test_create_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()

    response = client.post("/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == JobState.PENDING.value
    assert payload["version"] == 0


def test_claim_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()

    created = client.post("/jobs")
    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )

    assert created.status_code == 200
    assert claimed.status_code == 200
    payload = claimed.json()
    assert payload["state"] == JobState.PROCESSING.value
    assert payload["claimed_by"] == "worker-a"
    assert payload["lease_expires_at"] is not None


def test_process_success_flow_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()

    created = client.post("/jobs")
    job_id = created.json()["id"]

    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )
    succeeded = client.post(f"/jobs/{job_id}/succeed")

    assert created.status_code == 200
    assert claimed.status_code == 200
    assert succeeded.status_code == 200
    assert created.json()["version"] == 0
    assert claimed.json()["version"] == 1
    assert succeeded.json()["state"] == JobState.SUCCEEDED.value
    assert succeeded.json()["version"] == 2


def test_fail_and_retry_flow_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()

    created = client.post("/jobs")
    job_id = created.json()["id"]

    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )
    failed = client.post(f"/jobs/{job_id}/fail", json={"message": "boom"})
    retried = client.post(f"/jobs/{job_id}/retry")

    assert created.status_code == 200
    assert claimed.status_code == 200
    assert failed.status_code == 200
    assert retried.status_code == 200
    assert failed.json()["state"] == JobState.FAILED.value
    assert retried.json()["state"] == JobState.PENDING.value
    assert created.json()["version"] == 0
    assert claimed.json()["version"] == 1
    assert failed.json()["version"] == 2
    assert retried.json()["version"] == 3


def test_reclaim_expired_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal

    client = get_client()

    created = client.post("/jobs")
    job_id = created.json()["id"]

    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 1},
    )
    assert claimed.status_code == 200
    claimed_version = claimed.json()["version"]

    with SessionLocal() as session:
        with session.begin():
            job = session.get(Job, job_id)
            assert job is not None
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
            session.add(job)

    reclaimed = client.post("/jobs/reclaim-expired")
    assert reclaimed.status_code == 200
    assert reclaimed.json()["reclaimed"] == 1

    with SessionLocal() as session:
        job = session.get(Job, job_id)

    assert job is not None
    assert job.state == JobState.PENDING
    assert job.claimed_by is None
    assert job.lease_expires_at is None
    assert job.version == claimed_version + 1


def test_parallel_claim_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.models import Job
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal

    seed_client = get_client()
    for _ in range(5):
        created = seed_client.post("/jobs")
        assert created.status_code == 200

    claimed_ids: list[str] = []
    statuses: list[int] = []
    lock = threading.Lock()

    def claim_once(worker_idx: int) -> None:
        client = get_client()
        response = client.post(
            "/jobs/claim",
            json={"worker_id": f"worker-{worker_idx}", "lease_seconds": 30},
        )
        with lock:
            statuses.append(response.status_code)
            if response.status_code == 200:
                claimed_ids.append(response.json()["id"])

    threads = [threading.Thread(target=claim_once, args=(idx,)) for idx in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert statuses.count(200) == 5
    assert len(claimed_ids) == 5
    assert len(set(claimed_ids)) == 5

    with SessionLocal() as session:
        jobs = list(session.execute(select(Job).where(Job.id.in_(claimed_ids))).scalars())

    assert len(jobs) == 5
    assert all(job.state == JobState.PROCESSING for job in jobs)


def test_start_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()
    created = client.post("/jobs")
    job_id = created.json()["id"]

    started = client.post(f"/jobs/{job_id}/start")

    assert created.status_code == 200
    assert started.status_code == 200
    assert started.json()["state"] == JobState.PROCESSING.value
    assert started.json()["version"] == 1


def test_claim_no_content_when_empty_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    response = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )

    assert response.status_code == 204
    assert response.content in (b"", b"null")


def test_not_found_returns_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    response = client.post("/jobs/00000000-0000-0000-0000-000000000000/retry")

    assert response.status_code == 409
    payload: dict[str, Any] = response.json()
    assert payload["error"]["code"] == "ILLEGAL_STATE_TRANSITION"
    assert "Job not found" in payload["error"]["message"]


def test_start_not_found_returns_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    response = client.post("/jobs/00000000-0000-0000-0000-000000000000/start")

    assert response.status_code == 409
    payload: dict[str, Any] = response.json()
    assert payload["error"]["code"] == "ILLEGAL_STATE_TRANSITION"
    assert "Job not found" in payload["error"]["message"]


def test_fail_not_found_returns_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    response = client.post(
        "/jobs/00000000-0000-0000-0000-000000000000/fail",
        json={"message": "boom"},
    )

    assert response.status_code == 409
    payload: dict[str, Any] = response.json()
    assert payload["error"]["code"] == "ILLEGAL_STATE_TRANSITION"
    assert "Job not found" in payload["error"]["message"]


def test_reclaim_no_expired_jobs_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    create_response = client.post("/jobs")
    assert create_response.status_code == 200

    reclaim_response = client.post("/jobs/reclaim-expired")

    assert reclaim_response.status_code == 200
    assert reclaim_response.json() == {"reclaimed": 0}


def test_double_claim_same_worker_idempotent_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    client = get_client()

    created = client.post("/jobs")
    assert created.status_code == 200

    first_claim = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )
    second_claim = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )

    assert first_claim.status_code == 200
    assert second_claim.status_code == 200
    assert second_claim.json()["id"] == first_claim.json()["id"]
    assert second_claim.json()["version"] == first_claim.json()["version"]
    assert second_claim.json()["lease_expires_at"] == first_claim.json()["lease_expires_at"]


def test_double_transition_same_state_idempotent_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()
    created = client.post("/jobs")
    job_id = created.json()["id"]

    first_start = client.post(f"/jobs/{job_id}/start")
    second_start = client.post(f"/jobs/{job_id}/start")

    assert first_start.status_code == 200
    assert second_start.status_code == 200
    assert first_start.json()["state"] == JobState.PROCESSING.value
    assert second_start.json()["state"] == JobState.PROCESSING.value
    assert second_start.json()["version"] == first_start.json()["version"]


def test_double_fail_idempotent_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()
    created = client.post("/jobs")
    job_id = created.json()["id"]

    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )
    first_fail = client.post(f"/jobs/{job_id}/fail", json={"message": "boom"})
    second_fail = client.post(f"/jobs/{job_id}/fail", json={"message": "boom-again"})

    assert claimed.status_code == 200
    assert first_fail.status_code == 200
    assert second_fail.status_code == 200
    assert first_fail.json()["state"] == JobState.FAILED.value
    assert second_fail.json()["state"] == JobState.FAILED.value
    assert second_fail.json()["version"] == first_fail.json()["version"]


def test_double_retry_idempotent_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()
    created = client.post("/jobs")
    job_id = created.json()["id"]

    claimed = client.post(
        "/jobs/claim",
        json={"worker_id": "worker-a", "lease_seconds": 30},
    )
    failed = client.post(f"/jobs/{job_id}/fail", json={"message": "boom"})
    first_retry = client.post(f"/jobs/{job_id}/retry")
    second_retry = client.post(f"/jobs/{job_id}/retry")

    assert claimed.status_code == 200
    assert failed.status_code == 200
    assert first_retry.status_code == 200
    assert second_retry.status_code == 200
    assert first_retry.json()["state"] == JobState.PENDING.value
    assert second_retry.json()["state"] == JobState.PENDING.value
    assert second_retry.json()["version"] == first_retry.json()["version"]
