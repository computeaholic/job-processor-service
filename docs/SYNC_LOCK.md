SYNC LOCK — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

Repository identity:

- one-entity PostgreSQL job processor
- public client API for create/read/list/retry
- internal worker loop for claim/process/reclaim

Non-negotiable demonstrations:

- explicit state model
- PostgreSQL claim safety with `FOR UPDATE SKIP LOCKED`
- stale-writer rejection with `version`
- lease recovery
- durable create replay with `client_request_id`
- Alembic-managed schema evolution
- honest at-least-once execution boundary

Guardrails:

- do not add public worker mutation endpoints
- do not claim exactly-once execution
- do not reintroduce speculative fields such as `next_run_at` without implementation and tests
- do not remove `version` or migration readiness checks without replacing the lost invariant