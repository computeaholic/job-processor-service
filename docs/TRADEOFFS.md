TRADEOFFS — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Deliberate Choices

- PostgreSQL claim coordination with `FOR UPDATE SKIP LOCKED` instead of a broker
	Cost: polling overhead and DB contention under load
- retained `version` checks in addition to row locking
	Benefit: stale finalize/retry/reclaim writes fail loudly instead of silently winning
- optional `client_request_id` for durable create replay
	Benefit: public create semantics are stronger without expanding the domain model
- manual retry only
	Cost: no scheduler, no delayed backoff queue, no `next_run_at`
- `DEAD` is terminal
	Benefit: the final failure boundary is explicit and easy to defend

2. Explicit Non-Builds

- no external broker
- no delayed scheduling
- no priority queues
- no authentication
- no exactly-once side-effect protocol
- no metrics or tracing framework

3. Scale Notes

The first bottleneck remains database contention during polling and claim.

The first extraction boundary would be claim transport, not the state model: move dispatch to a broker while preserving the `jobs` table as lifecycle authority.