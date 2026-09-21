from __future__ import annotations

import logging
from threading import Event
from time import sleep
from typing import Callable, Protocol

from job_processor_service.domain.exceptions import NonRetryableJobError
from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState
from job_processor_service.infrastructure.db import SessionLocal
from job_processor_service.infrastructure.logging_utils import log_event
from job_processor_service.services.job_service import JobService

logger = logging.getLogger(__name__)


class WorkCallbackProtocol(Protocol):
    def __call__(self, job: Job) -> None: ...


WorkCallback = Callable[[Job], None]


class Worker:
    def __init__(
        self,
        worker_id: str,
        lease_seconds: int,
        work_callback: WorkCallback | None = None,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds
        if work_callback is None:
            def _noop(job: Job) -> None:
                return None

            self.work_callback: WorkCallback = _noop
        else:
            self.work_callback = work_callback
        self.service = JobService()

    def run_once(self) -> bool:
        with SessionLocal() as session:
            job = self.service.claim_next_job(
                session,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if job is None:
                return False

            try:
                self.work_callback(job)
            except NonRetryableJobError as exc:
                failed = self.service.record_processing_failure(
                    session,
                    job.id,
                    str(exc),
                    retryable=False,
                    error_code=exc.code,
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "worker.job_non_retryable_failed",
                    worker_id=self.worker_id,
                    job_id=job.id,
                    state=failed.state.value,
                    error_code=failed.error_code,
                )
                return True
            except Exception as exc:
                failed = self.service.record_processing_failure(
                    session,
                    job.id,
                    str(exc),
                    retryable=True,
                    error_code="JOB_PROCESSING_FAILED",
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "worker.job_failed",
                    worker_id=self.worker_id,
                    job_id=job.id,
                    state=failed.state.value,
                    error_code=failed.error_code,
                )
                return True

            completed = self.service.transition_job(session, job.id, JobState.SUCCEEDED)
            log_event(
                logger,
                logging.INFO,
                "worker.job_succeeded",
                worker_id=self.worker_id,
                job_id=job.id,
                state=completed.state.value,
            )
            return True

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            claimed = self.run_once()
            if not claimed:
                sleep(self.poll_interval_seconds)
