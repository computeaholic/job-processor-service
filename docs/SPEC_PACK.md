SPEC PACK — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Mission

This service demonstrates a durable background-job lifecycle implemented with FastAPI, SQLAlchemy, PostgreSQL, and an internal worker loop.

The primary invariant is:

- a job may only follow legal state transitions
- no two workers may claim the same pending job concurrently
- stale writers must fail on `version` mismatch instead of silently overwriting state

2. In Scope

- create job
- get job
- list jobs with optional state filter
- manual retry from `FAILED`
- worker claim / success / failure / reclaim logic
- lease recovery for expired `PROCESSING` jobs
- durable create replay using optional `client_request_id`
- Alembic-managed schema changes
- readiness based on DB connectivity and current migration revision

3. Out of Scope

- message brokers
- scheduled execution and `next_run_at`
- exponential backoff scheduler
- payload routing or typed job handlers
- authentication / RBAC
- exactly-once execution guarantees
- tracing and metrics stacks

4. Domain Model

Entity: `Job`

Persisted fields:

- `id`: primary key
- `client_request_id`: optional durable idempotency key, unique when present
- `state`: one of `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `DEAD`
- `error_message`: last processing error for failed or dead jobs
- `claimed_by`: worker identity while processing
- `lease_expires_at`: claim expiration timestamp while processing
- `version`: optimistic concurrency counter
- `retry_count`: number of processing failures recorded so far
- `max_retries`: failure budget, minimum `1`
- `created_at`, `updated_at`: audit timestamps

5. Public API Contract

- `POST /jobs`
  Request: optional `client_request_id`, optional `max_retries >= 1`
  Response: `201` on create, `200` on durable replay of the same request
- `GET /jobs/{id}`
- `GET /jobs?state=...`
- `POST /jobs/{id}/retry`
  Legal only from `FAILED`
- `GET /health/live`
- `GET /health/ready`

All error responses use:

```json
{
  "error": {
    "code": "machine_identifier",
    "message": "human readable"
  }
}
```

Relevant error codes:

- `JOB_NOT_FOUND`
- `JOB_IDEMPOTENCY_CONFLICT`
- `JOB_ILLEGAL_TRANSITION`
- `VERSION_CONFLICT`

6. Internal Worker Operations

- claim next `PENDING` job
- mark `PROCESSING -> SUCCEEDED`
- record `PROCESSING -> FAILED|DEAD`
- reclaim expired `PROCESSING` jobs back to `PENDING`

These are not public API endpoints.

7. Retry Contract

- `retry_count` increments only when processing fails.
- manual retry does not increment or reset `retry_count`.
- if a processing failure would make `retry_count >= max_retries`, the job becomes `DEAD` immediately.
- `DEAD` is terminal in this sample and is not requeued by the public API.

8. Execution Semantics

- claim concurrency safety is provided by `SELECT ... FOR UPDATE SKIP LOCKED`
- stale write protection is provided by `version` guards on updates
- execution is at-least-once
- external side effects may be duplicated if they succeed before the final state write commits

9. Persistence Contract

- PostgreSQL is authoritative
- schema changes are managed by Alembic
- job invariants are enforced by a combination of DB constraints and service-layer transition checks
- indexes support pending polling and lease-recovery scans

PostgreSQL

Alembic

pytest

ruff

black

mypy

GitHub Actions CI

Docker (pinned image)

New dependencies require ADR.

11. Complexity Budget

Max endpoints: 6

Max entities: 1

Max background processes: 1 worker loop

Target LOC: 2.5k–3.2k

Max abstraction layers: 3 (API / Domain / Worker)

Exceeding requires spec revision.

12. Testing Strategy

Unit:

State transitions

Backoff function

Illegal transitions

Integration:

Job lifecycle

Idempotency

Retry escalation

Concurrency:

2 workers, single ownership

Lease recovery

Migration:

Upgrade + downgrade tested

Coverage:

80–85%

All illegal transitions explicitly tested.

13. Security Considerations

No authentication (internal service assumption)

No authorization model

Input validation via Pydantic

No secrets stored in DB

Error messages sanitized

14. Operational Considerations

Environment Variables:

DATABASE_URL

WORKER_ID

POLL_INTERVAL

LEASE_TTL_SECONDS

Startup:

Run migrations

Start API

Start worker

Rollback:

Alembic downgrade supported

Deployment:

Single database assumption

Multiple workers allowed

15. Tradeoffs

Why not Celery/Kafka?

Intentional constraint to demonstrate DB-native queue.

Avoided complexity:

External brokers

Priority queues

Distributed locks

At 10x scale:

Polling becomes inefficient.

DB contention increases.

Requires sharding or broker.

First thing to break:

Lock contention under high worker concurrency.

16. Definition of Done

 Spec Pack complete

 Scope frozen (date stamped)

 FREEZE.md committed

 Constraints frozen

 Failure matrix complete

 State model complete

 Concurrency model defined

 Complexity budget declared

 Tests passing

 CI passing

 No TODO placeholders

 Documentation complete

 Interview Defense doc written

17. Risk Register

Technical risk:

Lease recovery edge cases
Mitigation: Explicit recovery tests

Operational risk:

Worker stuck in loop
Mitigation: Health readiness + logging

Complexity risk:

State explosion over time
Mitigation: Single entity policy

Owner: Repository maintainer
Monitoring: CI + test suite
Trigger: Failed concurrency or state transition test