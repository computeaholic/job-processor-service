from __future__ import annotations

from enum import StrEnum

from job_processor_service.domain.exceptions import DomainError


class JobState(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD = "DEAD"


TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.PROCESSING},
    JobState.PROCESSING: {JobState.SUCCEEDED, JobState.FAILED, JobState.DEAD},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: {JobState.PENDING, JobState.DEAD},
    JobState.DEAD: set(),
}


def validate_transition(current: JobState, target: JobState) -> None:
    allowed_targets = TRANSITIONS[current]
    if target not in allowed_targets:
        raise DomainError(f"Illegal transition: {current} -> {target}")
