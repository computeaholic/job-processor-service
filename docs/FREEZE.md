SPECIFICATION FREEZE — job-processor-service

Repository: job-processor-service
Specification Version: v1.1
Freeze Date: 2026-09-20
Baseline Commit: fea0779ab1e383147718ba5e0cf1ead90a3c4545
Reconciliation Branch: portfolio/reconcile-job-processor

This freeze supersedes the earlier v1.0 specification set.

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
- `client_request_id` idempotency is canonical and optional on create
- no backoff scheduler or `next_run_at` exists in scope
- `DEAD` is terminal

Any future change that alters these claims must update this file and the contract docs above.