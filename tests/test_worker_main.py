from __future__ import annotations

import signal
from types import SimpleNamespace

import pytest


def test_dispatch_job_calls_registered_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from job_processor_service.worker_main import dispatch_job
    import job_processor_service.worker_main as worker_main

    seen_payloads: list[dict[str, object]] = []

    def handler(payload: dict[str, object]) -> None:
        seen_payloads.append(payload)

    monkeypatch.setattr(worker_main, "JOB_HANDLERS", {"sample.noop": handler})

    dispatch_job(SimpleNamespace(job_type="sample.noop", payload={"value": 1}))

    assert seen_payloads == [{"value": 1}]


def test_dispatch_job_unknown_type_is_non_retryable() -> None:
    from job_processor_service.domain.exceptions import NonRetryableJobError
    from job_processor_service.worker_main import dispatch_job

    with pytest.raises(NonRetryableJobError, match="unsupported job_type") as error:
        dispatch_job(SimpleNamespace(job_type="missing", payload={}))

    assert error.value.code == "JOB_TYPE_UNSUPPORTED"


def test_build_worker_id_prefers_setting() -> None:
    from job_processor_service.worker_main import build_worker_id

    assert build_worker_id(SimpleNamespace(WORKER_ID="worker-123")) == "worker-123"


def test_build_worker_id_uses_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    from job_processor_service.worker_main import build_worker_id
    import job_processor_service.worker_main as worker_main

    monkeypatch.setattr(worker_main.socket, "gethostname", lambda: "host-a")

    assert build_worker_id(SimpleNamespace(WORKER_ID=None)) == "worker-host-a"


def test_main_configures_worker_and_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    import job_processor_service.worker_main as worker_main

    events: list[tuple[int, object]] = []
    logged_events: list[str] = []
    captured: dict[str, object] = {}

    class FakeWorker:
        def __init__(
            self,
            worker_id: str,
            lease_seconds: int,
            work_callback: object,
            poll_interval_seconds: float,
        ) -> None:
            captured["worker_id"] = worker_id
            captured["lease_seconds"] = lease_seconds
            captured["poll_interval_seconds"] = poll_interval_seconds
            captured["work_callback"] = work_callback

        def run_forever(self, stop_event: object) -> None:
            captured["stop_event_before"] = stop_event.is_set()
            events[0][1](signal.SIGINT, None)
            captured["stop_event_after"] = stop_event.is_set()

    monkeypatch.setattr(
        worker_main,
        "Settings",
        lambda: SimpleNamespace(
            WORKER_ID="worker-main",
            LEASE_TTL_SECONDS=45,
            POLL_INTERVAL_SECONDS=0.25,
        ),
    )
    monkeypatch.setattr(worker_main, "Worker", FakeWorker)
    monkeypatch.setattr(worker_main, "configure_logging", lambda: None)
    monkeypatch.setattr(
        worker_main,
        "log_event",
        lambda _logger, _level, event, **_fields: logged_events.append(event),
    )
    monkeypatch.setattr(
        worker_main.signal,
        "signal",
        lambda signum, handler: events.append((signum, handler)),
    )

    worker_main.main()

    assert [event[0] for event in events] == [signal.SIGINT, signal.SIGTERM]
    assert captured == {
        "worker_id": "worker-main",
        "lease_seconds": 45,
        "poll_interval_seconds": 0.25,
        "work_callback": worker_main.dispatch_job,
        "stop_event_before": False,
        "stop_event_after": True,
    }
    assert logged_events == [
        "worker.started",
        "worker.shutdown_requested",
        "worker.stopped",
    ]
