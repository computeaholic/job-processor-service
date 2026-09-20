INTERVIEW DEFENSE — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Design Intent

This repository demonstrates a single-database job processor where lifecycle truth lives in PostgreSQL and worker coordination is enforced in the database, not in an external queue.

2. Strongest Defensible Claims

- single-row claim contention is controlled with `FOR UPDATE SKIP LOCKED`
- stale writers are rejected with `version` guards
- crashed workers do not strand jobs permanently because lease expiry enables reclaim
- public create replay is durable when `client_request_id` is supplied
- the public API is restricted to client-facing operations, not worker state mutation

3. Hostile Questions and Answers

- Can two workers claim the same pending job concurrently?
	No. The claim path locks and skips competing rows inside PostgreSQL.
- Is execution exactly once?
	No. It is at-least-once. External effects can duplicate if the effect succeeds but the final commit does not.
- Why keep `version` if row locking already exists?
	Because finalize, retry, and reclaim can race with stale state loaded in earlier sessions. `version` turns that into an explicit conflict instead of a lost update.
- What does `DEAD` mean?
	The job exhausted its processing-failure budget and will not re-enter the queue through the public API.

4. Honest Limits

- no broker-backed scaling story
- no delayed retry scheduler
- no typed payload execution contract
- no authentication or multi-tenancy