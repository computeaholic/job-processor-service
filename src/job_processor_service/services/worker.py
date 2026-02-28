from __future__ import annotations

from threading import Event
from time import sleep
from typing import Callable, Protocol

from job_processor_service.domain.models import Job
from job_processor_service.domain.state_machine import JobState
from job_processor_service.infrastructure.db import SessionLocal
from job_processor_service.services.job_service import JobService


class WorkCallbackProtocol(Protocol):
    def __call__(self, job: Job) -> None: ...


WorkCallback = Callable[[Job], None]


class Worker:
    def __init__(
        self,
        worker_id: str,
        lease_seconds: int,
        work_callback: WorkCallback | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
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
            except Exception as exc:
                self.service.record_processing_failure(session, job.id, str(exc))
                return True

            self.service.transition_job(session, job.id, JobState.SUCCEEDED)
            return True

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            claimed = self.run_once()
            if not claimed:
                sleep(0.5)
