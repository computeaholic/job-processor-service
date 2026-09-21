INTERVIEW DEFENSE — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Design Intent

This system provides a database-backed background job processor using PostgreSQL row-level locking instead of an external broker. It is responsible for durable job execution, explicit retry semantics, and deterministic state transitions. The primary invariant protected is: a job may only move through legal state transitions and may only be claimed by one worker at a time. The most important design decision is using SELECT FOR UPDATE SKIP LOCKED with explicit transaction boundaries to guarantee single ownership and eliminate duplicate concurrent claim. All failure behavior and retry escalation are explicitly modeled.

2. What This Project Demonstrates

Explicit state transition enforcement in domain layer

Row-level concurrency control using FOR UPDATE SKIP LOCKED

Lease-based recovery of crashed workers

Deterministic retry/backoff policy without jitter

Idempotent job creation via immutable create contract and database unique constraint

Explicit transaction boundaries (with session.begin():)

Version-guarded state updates

Deterministic error envelope contract

Separation of API, domain, worker, and infrastructure layers

All items above correspond to implemented behavior.

3. Tradeoffs Made
Decision	Alternative	Why Rejected	Cost
DB-native queue	Redis/Kafka/Celery	Expands scope and operational complexity	DB contention at scale
Retain version column	Row-lock-only updates	Lost-update detection would be weaker	Slightly more bookkeeping
Deterministic backoff	Jittered retry	Non-determinism complicates testing	Possible synchronized retries
No external heartbeat system	Distributed lease coordination	Adds coordination layer	Duplicate execution possible after TTL expiry
No priority queues	Multi-queue scheduler	Out of scope	No SLA-tiering
4. Scaling Considerations (10x Scenario)

First bottleneck: database contention during job polling.

Next bottleneck: connection pool exhaustion.

Mitigation: tune poll interval, connection pool size, and index design.

Architectural change: introduce broker-backed dispatch while preserving the Job table as state authority.

Stable components: domain state machine, failure matrix, retry semantics, idempotent create contract.

First extraction boundary: replace DB polling with external queue while keeping Job table as lifecycle authority.

5. Concurrency & Failure Analysis

Race condition risk:

Multiple workers attempting to claim same job.

Prevented via FOR UPDATE SKIP LOCKED.

Partial failure risk:

Worker crash after claim.

Mitigated via lease TTL recovery.

Duplicate execution risk:

Possible after lease expiry or after external side-effect / commit mismatch.

Handlers required to be idempotent.

Idempotency guarantee:

Unique constraint on client_request_id plus immutable create-contract comparison prevents duplicate create.

Retry safety:

Retryable handler failures are automatically requeued with deterministic backoff.

Non-retryable failures transition to FAILED and require deliberate manual retry.

DEAD is terminal.

6. Operational Readiness

Startup sequence:

Apply migrations.

Start API.

Start worker loop independently if desired.

Health checks:

Liveness: process active.

Readiness: database reachable and migrations current.

Logs:

Structured JSON.

State transitions logged once.

Worker failures logged at finalization.

Recovery from failed deployment:

Rollback via Alembic downgrade.

Restart workers; lease recovery requeues orphaned jobs.

7. Known Limits

Single-node PostgreSQL assumption.

No horizontal scaling across databases.

Polling-based queue.

No priority scheduling.

No distributed locking.

No rate limiting.

No authentication.

Limitations are intentional.