FAILURE MODES — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Public API Failures

- invalid `POST /jobs` payload: `422`
- missing job on `GET /jobs/{id}` or `POST /jobs/{id}/retry`: `404` with `JOB_NOT_FOUND`
- conflicting replay for the same `client_request_id`: `409` with `JOB_IDEMPOTENCY_CONFLICT`
- illegal retry from any non-`FAILED` state: `409` with `JOB_ILLEGAL_TRANSITION`

2. Worker Failures

- handler exception with remaining budget: `PROCESSING -> FAILED`, increment `retry_count`
- handler exception at budget boundary: `PROCESSING -> DEAD`, increment `retry_count`
- worker crash after claim: row remains `PROCESSING` until lease expiry, then reclaim requeues it

3. Persistence Failures

- DB unavailable: readiness returns `503`; runtime operations fail fast instead of faking success
- stale update attempt: write is rejected with `VERSION_CONFLICT`
- missing migration state: readiness returns `503`

4. External Side-Effect Boundary

If a handler performs an external side effect and the subsequent state write does not commit, the side effect may already have happened even though the job is not yet `SUCCEEDED`.

That is the critical honesty boundary of this sample.

Execution is at-least-once, not exactly-once.

5. Logging Rules

- lifecycle events are emitted as structured JSON strings through the stdlib logger
- payloads and secrets are not logged
- worker failure is logged once at the worker/service boundary
- API responses do not expose stack traces