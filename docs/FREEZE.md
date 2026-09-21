SPECIFICATION FREEZE — job-processor-service

Repository: job-processor-service
Specification Version: v1.1
Freeze Date: 2026-09-20
Implementation Basis Commit: 378f3a4c5187bb56270cdf3de3094b433fa6c506
Baseline Commit: fea0779ab1e383147718ba5e0cf1ead90a3c4545
Reconciliation Branch: portfolio/reconcile-job-processor

This freeze supersedes the earlier v1.0 specification set.

This document records the formal freeze of the reconciled system definition.

The referenced Implementation Basis Commit is the runtime, tooling, test, and documentation reconciliation commit immediately preceding this freeze update.

Frozen authoritative artifacts:

- SPEC_PACK.md
- STATE_MODEL.md
- CONCURRENCY_MODEL.md
- FAILURE_MODES.md
- OPERATIONS.md
- TRADEOFFS.md
- INTERVIEW_DEFENSE.md
- PROJECT_INIT_CHECKLIST.md
- SYNC_LOCK.md

Frozen scope:

- one persisted entity: `Job`
- client-facing API limited to create/read/list/retry/health
- worker internals remain non-public
- PostgreSQL + Alembic remain authoritative
- execution semantics remain at-least-once

Reconciliation outcomes locked by this freeze:

- `version` is canonical and required
- `client_request_id` idempotency is canonical and required on the public create API
- `job_type`, `payload`, and `next_run_at` are canonical persisted fields
- deterministic exponential backoff is canonical for retryable failures
- `DEAD` is terminal

Frozen guarantees:

- explicit transaction boundaries (`with session.begin():`)
- row-level claiming via `FOR UPDATE SKIP LOCKED`
- lease TTL recovery semantics
- immutable create-contract replay safety via DB constraint
- version-guarded stale write rejection
- migration-aware readiness
- runnable standalone worker entrypoint

Any future change that alters these claims must update this file and the contract docs above.