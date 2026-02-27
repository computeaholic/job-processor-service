FAILURE MATRIX — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: 1.0

All failure scenarios are explicitly modeled below.
No unmodeled failure is permitted.

Failure Matrix
Scenario	Detected At	User Response	HTTP Code	Log Level	Retry Strategy	Idempotent Behavior
Invalid input (schema validation)	Validation layer	Error envelope (VALIDATION_ERROR)	422	WARNING	No retry	Safe to retry with corrected input
Missing job (GET /jobs/{id})	Service layer	Error envelope (JOB_NOT_FOUND)	404	INFO	No retry	Safe to retry
Duplicate job submission (client_request_id unique violation)	Infrastructure layer (DB constraint)	Error envelope (JOB_IDEMPOTENCY_CONFLICT)	409	INFO	No retry	Protected by DB unique constraint
Illegal state transition (e.g., retry from non-dead_letter state)	Domain layer	Error envelope (JOB_ILLEGAL_TRANSITION)	409	WARNING	No retry	Safe to retry request; state unchanged
Concurrency lock contention (worker claim)	Infrastructure layer	No API response (worker internal skip)	N/A	DEBUG	Skip locked row	Safe
Database unavailable (startup or API)	Infrastructure layer	Error envelope (DB_UNAVAILABLE)	503	ERROR	Client may retry	Safe to retry
Handler timeout	Worker layer	Treated as retryable failure	N/A	ERROR	Exponential backoff until attempts exhausted	Safe
Retryable job failure	Worker layer	Transition to pending with backoff	N/A	WARNING	Exponential backoff	Safe
Non-retryable job failure	Worker layer	Transition directly to dead_letter	N/A	WARNING	No retry	Safe
Max attempts exceeded	Worker layer	Transition to dead_letter	N/A	WARNING	Escalation to dead_letter	Safe
Worker crash mid-processing	Recovery scan	Job requeued after lease TTL	N/A	WARNING	Retry after lease expiry	Safe
Partial transaction failure (API mutation)	Infrastructure layer	Error envelope (INTERNAL_ERROR)	500	ERROR	Client retry allowed	Safe
Partial transaction failure (worker finalize)	Infrastructure layer	Transaction rollback; no state mutation	N/A	ERROR	Worker retry next poll	Safe
Unexpected internal error	Service layer	Error envelope (INTERNAL_ERROR)	500	ERROR	Client retry allowed	Safe
Definitions
Detected At

Validation layer — Pydantic request parsing

Domain layer — State legality enforcement

Service layer — API orchestration

Worker layer — Background execution logic

Infrastructure layer — Database connectivity, transactions, engine failures

Logging Rules

Each failure logged exactly once at boundary mapping layer.

Worker execution failures logged during finalize phase.

API envelope mapping logs at service boundary.

No duplicate logs across layers.

No payload bodies logged.

No stack traces returned to client.

Log entries must include job ID where applicable.

Retry Semantics
Failure Type	Retry Allowed?	Policy
Validation error	No	Client must correct
DB unavailable	Yes	Immediate client retry
Retryable handler failure	Yes	Deterministic exponential backoff
Handler timeout	Yes	Treated as retryable failure
Non-retryable handler failure	No	Immediate dead_letter
Lease expiration	Yes	Requeue without attempt increment
Dead_letter	Manual only	API retry endpoint
Backoff Policy

Delay formula:

delay = min(base_delay * (2^(attempt_count - 1)), max_delay)

Defaults:

base_delay = 5 seconds

max_delay = 5 minutes

No jitter (intentional for determinism).

Enforcement Rules

Every endpoint maps to at least one failure above.

Every state transition must map to legality or illegal transition.

Every worker failure must map to retry or escalation.

All partial transaction paths must be atomic and rollback-safe.

All failure paths must be covered by tests.

Concurrency tests must validate lease recovery and single ownership.

Failure handling is first-class system behavior.