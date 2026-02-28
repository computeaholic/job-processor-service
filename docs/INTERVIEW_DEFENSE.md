INTERVIEW DEFENSE — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

1. Design Intent

This system provides a database-backed background job processor using PostgreSQL row-level locking instead of an external broker. It is responsible for durable job execution, explicit retry semantics, and deterministic state transitions. The primary invariant protected is: a job may only move through legal state transitions and may only be executed by one worker at a time. The most important design decision is using SELECT FOR UPDATE SKIP LOCKED with explicit transaction boundaries to guarantee single ownership and eliminate duplicate concurrent execution. All failure behavior and retry escalation are explicitly modeled.

2. What This Project Demonstrates

Explicit state transition enforcement in domain layer

Row-level concurrency control using FOR UPDATE SKIP LOCKED

Lease-based recovery of crashed workers

Deterministic retry/backoff policy without jitter

Idempotent job creation via database unique constraint

Explicit transaction boundaries (with session.begin():)

Deterministic error envelope contract

Separation of API, domain, worker, and infrastructure layers

All items above correspond to implemented behavior.

3. Tradeoffs Made
Decision	Alternative	Why Rejected	Cost
DB-native queue	Redis/Kafka/Celery	Expands scope and operational complexity	DB contention at scale
No optimistic locking	Version columns	Row locks sufficient for single-writer model	Less flexibility
Deterministic backoff	Jittered retry	Non-determinism complicates testing	Possible synchronized retries
No external heartbeat system	Distributed lease coordination	Adds coordination layer	Duplicate execution possible after TTL expiry
No priority queues	Multi-queue scheduler	Out of scope	No SLA-tiering
4. Scaling Considerations (10x Scenario)

First bottleneck: database contention during job polling.

Next bottleneck: connection pool exhaustion.

Mitigation: tune batch size and poll interval; increase pool size.

Architectural change: introduce broker-backed queue while preserving state model.

Stable components: domain state machine, failure matrix, retry semantics.

First extraction boundary: replace DB polling with external queue while keeping Job table as state authority.

5. Concurrency & Failure Analysis

Race condition risk:

Multiple workers attempting to claim same job.

Prevented via FOR UPDATE SKIP LOCKED.

Partial failure risk:

Worker crash after claim.

Mitigated via lease TTL recovery.

Duplicate execution risk:

Possible after lease expiry.

Handlers required to be idempotent.

Idempotency guarantee:

Unique constraint on client_request_id prevents duplicate create.

Retry safety:

Safe for retryable handler failures.

Unsafe for non-retryable errors (transition to failed/dead_letter).

All failure paths map to explicit state transitions.

6. Operational Readiness

Startup sequence:

Apply migrations.

Start API.

Start worker loop.

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