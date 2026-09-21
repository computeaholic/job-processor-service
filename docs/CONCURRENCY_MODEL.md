CONCURRENCY MODEL — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: 1.1

This document defines how concurrent workers interact safely with the database and guarantees single ownership of a job during execution.

Concurrency correctness is enforced via database row-level locking plus version-guarded writes.

No distributed coordination mechanisms are used.

1. Concurrency Strategy

The system relies on:

PostgreSQL row-level locking

SELECT ... FOR UPDATE SKIP LOCKED

Explicit transaction boundaries

Lease-based recovery

Optimistic concurrency via version column

No distributed locks.
No external brokers.

2. Job Claim Algorithm

Workers poll eligible jobs:

Criteria:

state = 'PENDING'

next_run_at <= now

claimed_by IS NULL

Acquisition query:

SELECT *
FROM jobs
WHERE state = 'PENDING'
AND next_run_at <= now()
AND claimed_by IS NULL
ORDER BY next_run_at, created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 1;

Behavior:

Rows locked immediately upon selection.

Locked rows are invisible to competing workers.

Workers skipping locked rows prevents duplicate ownership.

Claim transition occurs inside:

with session.begin():

State mutation to PROCESSING occurs before commit.

3. Ownership Guarantees

A job is considered owned when:

state = 'PROCESSING'

claimed_by is set

lease_expires_at is set

Stale finalize, retry, or reclaim attempts must also satisfy the current version value.

If the row version has changed, the write fails with VERSION_CONFLICT.

4. Worker Crash Handling

If worker crashes after claim but before finalize:

Job remains in PROCESSING

Lease TTL governs recovery

Lease expiration condition:

lease_expires_at < now

Recovery behavior:

Job requeued to PENDING

Lock fields cleared

next_run_at = now

No retry_count increment

Logged once

Recovery executed by worker maintenance loop.

5. Isolation Level

Database isolation level:

READ COMMITTED (PostgreSQL default)

Justification:

Row locks guarantee single-claim semantics.

Version guards reject stale writers.

Higher isolation unnecessary for scope.

6. Duplicate Execution Safety

System guarantees:

No two workers claim the same eligible PENDING job concurrently.

Duplicate execution may occur only after lease expiration or after external effect / commit mismatch.

Handlers must be idempotent.

Execution safety assumptions:

Side effects must tolerate re-run.

No external side effect tracking provided in v1.

7. Contention Behavior

Under high worker concurrency:

Workers may skip locked rows.

No API-level errors generated.

Lock contention is internal and logged at DEBUG/INFO boundaries as needed.

Throughput degrades gracefully.

No spin-locking.
No busy-wait loops.

Polling interval governs load.

8. Idempotent API Concurrency

Duplicate job creation prevented by:

Unique constraint on client_request_id

DB-level enforcement

409 returned on immutable create-contract mismatch

No race condition possible due to constraint.

9. Concurrency Boundaries

Concurrency safety is guaranteed only when:

All state transitions occur inside explicit transactions.

All claims use FOR UPDATE SKIP LOCKED.

Lease recovery follows defined TTL.

All stale writes respect version guards.

Violation of these rules breaks correctness and is not permitted.

10. Enforcement Requirements

Concurrency test must simulate ≥2 workers.

Tests must verify:

No double claim

Proper lease recovery

Correct DEAD escalation

No test may mock row-level locking.

Integration DB required for concurrency validation.

Concurrency correctness is a first-class system guarantee.