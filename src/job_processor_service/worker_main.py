from __future__ import annotations

import logging
import signal
import socket
from threading import Event
from typing import Any, Callable

from job_processor_service.config.settings import Settings
from job_processor_service.domain.exceptions import NonRetryableJobError
from job_processor_service.domain.models import Job
from job_processor_service.infrastructure.logging_utils import configure_logging, log_event
from job_processor_service.services.worker import Worker

logger = logging.getLogger(__name__)
JobHandler = Callable[[dict[str, Any]], None]


def sample_noop_handler(_payload: dict[str, Any]) -> None:
    return None


JOB_HANDLERS: dict[str, JobHandler] = {
    "sample.noop": sample_noop_handler,
}


def dispatch_job(job: Job) -> None:
    handler = JOB_HANDLERS.get(job.job_type)
    if handler is None:
        raise NonRetryableJobError(
            f"unsupported job_type: {job.job_type}",
            code="JOB_TYPE_UNSUPPORTED",
        )
    handler(job.payload)


def build_worker_id(settings: Settings) -> str:
    return settings.WORKER_ID or f"worker-{socket.gethostname()}"


def main() -> None:
    configure_logging()
    settings = Settings()  # type: ignore[call-arg]
    stop_event = Event()
    worker_id = build_worker_id(settings)

    def handle_shutdown(_signum: int, _frame: object) -> None:
        stop_event.set()
        log_event(
            logger,
            logging.INFO,
            "worker.shutdown_requested",
            worker_id=worker_id,
        )

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    worker = Worker(
        worker_id=worker_id,
        lease_seconds=settings.LEASE_TTL_SECONDS,
        work_callback=dispatch_job,
        poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
    )
    log_event(logger, logging.INFO, "worker.started", worker_id=worker_id)
    worker.run_forever(stop_event)
    log_event(logger, logging.INFO, "worker.stopped", worker_id=worker_id)


if __name__ == "__main__":
    main()