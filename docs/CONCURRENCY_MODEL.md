CONCURRENCY MODEL — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: 1.0

This document defines how concurrent workers interact safely with the database and guarantees single ownership of a job during execution.

Concurrency correctness is enforced via database row-level locking.

No distributed coordination mechanisms are used.

1. Concurrency Strategy

The system relies exclusively on:

PostgreSQL row-level locking

SELECT ... FOR UPDATE SKIP LOCKED

Explicit transaction boundaries

Lease-based recovery

No optimistic locking.
No version columns.
No distributed locks.
No external brokers.

2. Job Claim Algorithm

Workers poll eligible jobs:

Criteria:

status = 'pending'

next_run_at <= now

Acquisition query:

SELECT *
FROM jobs
WHERE status = 'pending'
AND next_run_at <= now()
ORDER BY next_run_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;

Behavior:

Rows locked immediately upon selection.

Locked rows are invisible to competing workers.

Workers skipping locked rows prevents duplicate ownership.

Claim transition occurs inside:

with session.begin():

State mutation to running occurs before commit.

3. Ownership Guarantees

A job is considered owned when:

status = 'running'

locked_by is set

locked_at is set

Only the worker that set locked_by may finalize the job.

Before finalization, worker must revalidate:

Job still running

locked_by == worker_id

If ownership lost, worker aborts without mutation.

4. Worker Crash Handling

If worker crashes after claim but before finalize:

Job remains in running

Lease TTL governs recovery

Lease expiration condition:

locked_at < now - lease_ttl

Recovery behavior:

Job requeued to pending

Lock fields cleared

No attempt_count increment

Logged once

Recovery executed by worker maintenance loop.

5. Isolation Level

Database isolation level:

READ COMMITTED (PostgreSQL default)

Justification:

Row locks guarantee single-writer semantics.

No phantom issues impact correctness.

Higher isolation unnecessary for scope.

6. Duplicate Execution Safety

System guarantees:

No two workers execute same job concurrently.

Duplicate execution may occur only after lease expiration.

Handlers must be idempotent.

Execution safety assumptions:

Side effects must tolerate re-run.

No external side effect tracking provided in v1.

Determinism enforced at handler level.

7. Contention Behavior

Under high worker concurrency:

Workers may skip locked rows.

No API-level errors generated.

Lock contention is internal and logged at DEBUG.

Throughput degrades gracefully.

No spin-locking.
No busy-wait loops.

Polling interval governs load.

8. Idempotent API Concurrency

Duplicate job creation prevented by:

Unique constraint on client_request_id

DB-level enforcement

409 returned on violation

No race condition possible due to constraint.

9. Concurrency Boundaries

Concurrency safety is guaranteed only when:

All state transitions occur inside explicit transactions.

All claims use FOR UPDATE SKIP LOCKED.

Lease recovery follows defined TTL.

Violation of these rules breaks correctness and is not permitted.

10. Enforcement Requirements

Concurrency test must simulate ≥2 workers.

Tests must verify:

No double execution

Proper lease recovery

Correct dead-letter escalation

No test may mock row-level locking.

Integration DB required for concurrency validation.

Concurrency correctness is a first-class system guarantee.