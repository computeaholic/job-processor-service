from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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


def job_request(
    *,
    client_request_id: str | None = None,
    job_type: str = "sample.noop",
    payload: dict[str, object] | None = None,
    max_retries: int = 3,
) -> dict[str, object]:
    return {
        "client_request_id": client_request_id or str(uuid4()),
        "job_type": job_type,
        "payload": payload or {"value": "ok"},
        "max_retries": max_retries,
    }


def create_failed_job(*, next_run_at: datetime | None = None) -> str:
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(
            session,
            client_request_id=uuid4(),
            job_type="sample.noop",
            payload={"kind": "failed"},
            next_run_at=next_run_at,
        )

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None
    assert claimed.id == created.id

    with SessionLocal() as session:
        failed = service.record_processing_failure(
            session,
            claimed.id,
            "boom\nwith noise",
            retryable=False,
            error_code="job sample failed",
        )

    return str(failed.id)


def create_dead_job() -> str:
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()
    with SessionLocal() as session:
        created = service.create_job(
            session,
            client_request_id=uuid4(),
            job_type="sample.noop",
            payload={"kind": "dead"},
            max_retries=1,
        )

    with SessionLocal() as session:
        claimed = service.claim_next_job(
            session, worker_id="worker-a", lease_seconds=30
        )

    assert claimed is not None
    assert claimed.id == created.id

    with SessionLocal() as session:
        dead = service.record_processing_failure(session, claimed.id, "fatal")

    return str(dead.id)


def test_create_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState

    client = get_client()
    request = job_request(payload={"account_id": 7})

    response = client.post("/jobs", json=request)

    assert response.status_code == 201
    body = response.json()
    assert body["client_request_id"] == request["client_request_id"]
    assert body["job_type"] == request["job_type"]
    assert body["payload"] == request["payload"]
    assert body["state"] == JobState.PENDING.value
    assert body["version"] == 0
    assert body["retry_count"] == 0
    assert body["max_retries"] == 3
    assert body["next_run_at"] is not None


def test_create_job_with_idempotency_key_replays_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    request = job_request(
        client_request_id=str(uuid4()),
        job_type="sample.noop",
        payload={"value": 5},
        max_retries=5,
    )

    created = client.post("/jobs", json=request)
    replayed = client.post("/jobs", json=request)

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json()["id"] == created.json()["id"]


def test_same_key_different_job_type_conflicts_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    client_request_id = str(uuid4())

    created = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, job_type="sample.noop"),
    )
    conflicted = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, job_type="sample.other"),
    )

    assert created.status_code == 201
    assert conflicted.status_code == 409
    assert conflicted.json()["error"]["code"] == "JOB_IDEMPOTENCY_CONFLICT"


def test_same_key_different_payload_conflicts_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    client_request_id = str(uuid4())

    created = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, payload={"value": 1}),
    )
    conflicted = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, payload={"value": 2}),
    )

    assert created.status_code == 201
    assert conflicted.status_code == 409
    assert conflicted.json()["error"]["code"] == "JOB_IDEMPOTENCY_CONFLICT"


def test_same_key_different_max_retries_conflicts_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    client_request_id = str(uuid4())

    created = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, max_retries=3),
    )
    conflicted = client.post(
        "/jobs",
        json=job_request(client_request_id=client_request_id, max_retries=4),
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
    request = job_request(payload={"city": "Oslo"})

    created = client.post("/jobs", json=request)
    job_id = created.json()["id"]
    response = client.get(f"/jobs/{job_id}")

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["payload"] == request["payload"]


def test_get_job_not_found_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    response = client.get("/jobs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_list_jobs_default_limit_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    for index in range(60):
        response = client.post(
            "/jobs",
            json=job_request(payload={"index": index}),
        )
        assert response.status_code == 201

    listed = client.get("/jobs")

    assert listed.status_code == 200
    assert len(listed.json()) == 50


def test_list_jobs_explicit_limit_and_offset_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    created_ids: list[str] = []
    for index in range(3):
        response = client.post(
            "/jobs",
            json=job_request(payload={"index": index}),
        )
        created_ids.append(response.json()["id"])

    listed = client.get("/jobs?limit=1&offset=1")

    assert listed.status_code == 200
    assert [job["id"] for job in listed.json()] == [created_ids[1]]


def test_list_jobs_filters_by_state_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)
    from job_processor_service.domain.state_machine import JobState
    from job_processor_service.infrastructure.db import SessionLocal
    from job_processor_service.services.job_service import JobService

    service = JobService()

    with SessionLocal() as session:
        pending = service.create_job(
            session,
            client_request_id=uuid4(),
            job_type="sample.noop",
            payload={"kind": "pending"},
            next_run_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    failed_id = create_failed_job()

    client = get_client()
    response = client.get(f"/jobs?state={JobState.FAILED.value}")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [failed_id]
    assert pending.id != failed_id


def test_list_jobs_invalid_excessive_limit_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    response = client.get("/jobs?limit=101")

    assert response.status_code == 422


def test_retry_failed_job_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    job_id = create_failed_job()

    before = client.get(f"/jobs/{job_id}")
    response = client.post(f"/jobs/{job_id}/retry")

    assert before.status_code == 200
    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["state"] == "PENDING"
    assert response.json()["retry_count"] == before.json()["retry_count"]
    assert response.json()["claimed_by"] is None
    assert response.json()["lease_expires_at"] is None
    assert response.json()["error_code"] is None
    assert response.json()["error_message"] is None


def test_dead_job_exposes_sanitized_failure_metadata_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    job_id = create_dead_job()

    response = client.get(f"/jobs/{job_id}")
    listed = client.get("/jobs?state=DEAD")

    assert response.status_code == 200
    assert response.json()["state"] == "DEAD"
    assert response.json()["error_code"] == "JOB_PROCESSING_FAILED"
    assert response.json()["error_message"] == "fatal"
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id


def test_retry_from_pending_returns_conflict_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    created = client.post("/jobs", json=job_request())
    job_id = created.json()["id"]

    response = client.post(f"/jobs/{job_id}/retry")

    assert created.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ILLEGAL_TRANSITION"


def test_retry_dead_returns_conflict_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    job_id = create_dead_job()

    response = client.post(f"/jobs/{job_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ILLEGAL_TRANSITION"


def test_retry_not_found_returns_404_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_database(monkeypatch)

    client = get_client()
    response = client.post("/jobs/00000000-0000-0000-0000-000000000000/retry")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
