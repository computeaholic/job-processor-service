FAILURE MATRIX — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: 1.1

All failure scenarios are explicitly modeled below.
No unmodeled failure is permitted.

Failure Matrix
Scenario	Detected At	User Response	HTTP Code	Log Level	Retry Strategy	Idempotent Behavior
Invalid input (schema validation)	Validation layer	Error envelope (VALIDATION_ERROR)	422	WARNING	No retry	Safe to retry with corrected input
Missing job (GET /jobs/{id})	Service layer	Error envelope (JOB_NOT_FOUND)	404	INFO	No retry	Safe to retry
Duplicate job submission (client_request_id unique violation or immutable-contract mismatch)	Infrastructure/service	Error envelope (JOB_IDEMPOTENCY_CONFLICT)	409	INFO	No retry	Protected by DB unique constraint
Illegal state transition (e.g., retry from non-FAILED state)	Domain layer	Error envelope (JOB_ILLEGAL_TRANSITION)	409	WARNING	No retry	Safe to retry request; state unchanged
Concurrency lock contention (worker claim)	Infrastructure layer	No API response (worker internal skip)	N/A	DEBUG	Skip locked row	Safe
Database unavailable (startup or API)	Infrastructure layer	Error envelope (DB_UNAVAILABLE)	503	ERROR	Client may retry	Safe to retry
Retryable job failure	Worker layer	Transition to pending with backoff or DEAD	N/A	WARNING/INFO	Deterministic exponential backoff	Safe
Non-retryable job failure	Worker layer	Transition to FAILED	N/A	WARNING	Manual retry only	Safe
Max retries exhausted	Worker layer	Transition to DEAD	N/A	WARNING	Escalation to DEAD	Safe
Worker crash mid-processing	Recovery scan	Job requeued after lease TTL	N/A	WARNING	Retry after lease expiry	Safe
Partial transaction failure (API mutation)	Infrastructure layer	Error envelope (INTERNAL_ERROR)	500	ERROR	Client retry allowed	Safe
Partial transaction failure (worker finalize)	Infrastructure layer	Transaction rollback; no state mutation	N/A	ERROR	Worker retry next poll	Safe
Unexpected internal error	Service layer	Error envelope (INTERNAL_ERROR)	500	ERROR	Client retry allowed	Safe

Logging Rules

Each failure logged exactly once at boundary mapping layer.

Worker execution failures logged during finalize phase.

API envelope mapping logs at service boundary.

No duplicate logs across layers.

No payload bodies logged.

No stack traces returned to client.

No stack traces persisted.

Log entries include job ID where applicable.

Retry Semantics
Failure Type	Retry Allowed?	Policy
Validation error	No	Client must correct
DB unavailable	Yes	Immediate client retry
Retryable handler failure	Yes	Automatic deterministic backoff while budget remains
Non-retryable handler failure	Manual only	Transition to FAILED
Lease expiration	Yes	Requeue without retry_count increment
DEAD	No	Terminal

Backoff Policy

Delay formula:

delay = min(base_delay_seconds * (2^(retry_count - 1)), max_delay_seconds)

Defaults:

base_delay_seconds = 5 seconds

max_delay_seconds = 5 minutes

No jitter (intentional for determinism).

Failure Metadata

Persisted fields:

error_code

error_message

Messages are sanitized, control characters normalized, and capped in length.

Enforcement Rules

Every endpoint maps to at least one failure above.

Every state transition must map to legality or illegal transition.

Every worker failure must map to retry, FAILED, or DEAD.

All partial transaction paths must be atomic and rollback-safe.

All failure paths must be covered by tests.