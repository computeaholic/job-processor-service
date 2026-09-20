from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5433/job_processor"
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


def create_failed_job() -> str:
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(session)

    with SessionLocal() as session:
        claimed = service.claim_next_job(session, worker_id="worker-a", lease_seconds=30)

    assert claimed is not None

    with SessionLocal() as session:
        failed = service.record_processing_failure(session, claimed.id, "boom")

    return str(failed.id)


def test_create_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()

    response = client.post("/jobs")

    assert response.status_code == 201
    payload = response.json()
    assert payload["state"] == JobState.PENDING.value
    assert payload["version"] == 0
    assert payload["retry_count"] == 0
    assert payload["max_retries"] == 3


def test_create_job_with_idempotency_key_replays_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    client_request_id = str(uuid4())

    created = client.post(
        "/jobs",
        json={"client_request_id": client_request_id, "max_retries": 5},
    )
    replayed = client.post(
        "/jobs",
        json={"client_request_id": client_request_id, "max_retries": 5},
    )

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json()["id"] == created.json()["id"]
    assert replayed.json()["client_request_id"] == client_request_id
    assert replayed.json()["max_retries"] == 5


def test_create_job_idempotency_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    client_request_id = str(uuid4())

    created = client.post(
        "/jobs",
        json={"client_request_id": client_request_id, "max_retries": 3},
    )
    conflicted = client.post(
        "/jobs",
        json={"client_request_id": client_request_id, "max_retries": 4},
    )

    assert created.status_code == 201
    assert conflicted.status_code == 409
    assert conflicted.json()["error"]["code"] == "JOB_IDEMPOTENCY_CONFLICT"


def test_create_job_validation_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    response = client.post("/jobs", json={"max_retries": 0})

    assert response.status_code == 422


def test_get_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()

    created = client.post("/jobs")
    job_id = created.json()["id"]
    response = client.get(f"/jobs/{job_id}")

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["state"] == "PENDING"


def test_get_job_not_found_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()

    response = client.get("/jobs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_list_jobs_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()

    first = client.post("/jobs")
    second = client.post("/jobs", json={"max_retries": 5})
    response = client.get("/jobs")

    assert first.status_code == 201
    assert second.status_code == 201
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [
        first.json()["id"],
        second.json()["id"],
    ]


def test_list_jobs_filters_by_state_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        pending = service.create_job(session)

    failed_id = create_failed_job()

    client = get_client()
    response = client.get(f"/jobs?state={JobState.FAILED.value}")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [failed_id]
    assert pending.id != failed_id


def test_retry_failed_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    job_id = create_failed_job()

    response = client.post(f"/jobs/{job_id}/retry")

    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["state"] == "PENDING"
    assert response.json()["retry_count"] == 1
    assert response.json()["claimed_by"] is None
    assert response.json()["lease_expires_at"] is None


def test_retry_from_pending_returns_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    created = client.post("/jobs")
    job_id = created.json()["id"]

    response = client.post(f"/jobs/{job_id}/retry")

    assert created.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ILLEGAL_TRANSITION"


def test_retry_not_found_returns_404_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    response = client.post("/jobs/00000000-0000-0000-0000-000000000000/retry")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
