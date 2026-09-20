CONCURRENCY MODEL — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Concurrency Strategy

This repository deliberately uses two mechanisms together:

- PostgreSQL row-level locking via `SELECT ... FOR UPDATE SKIP LOCKED`
- `version`-guarded updates to reject stale writers during finalize, retry, and reclaim operations

2. Claim Algorithm

Eligible work is defined as:

- `state = 'PENDING'`
- `claimed_by IS NULL`

Workers claim the oldest pending row by `created_at` under `FOR UPDATE SKIP LOCKED`, then update it to:

- `state = 'PROCESSING'`
- `claimed_by = worker_id`
- `lease_expires_at = now + lease_seconds`
- `version = version + 1`

3. Ownership Guarantees

- competing workers cannot claim the same pending row concurrently
- only rows with no current owner are claimable
- stale finalize or retry writes fail with `VERSION_CONFLICT`

4. Lease Recovery

If a worker dies after claim, the row stays in `PROCESSING` until `lease_expires_at` passes.

Recovery path:

- `PROCESSING -> PENDING`
- clear `claimed_by`
- clear `lease_expires_at`
- increment `version`
- leave `retry_count` unchanged

5. Duplicate Execution Boundary

This system is not exactly-once.

It prevents concurrent duplicate claim of a pending row, but duplicate external side effects are still possible when:

- a worker performs the effect
- the final `SUCCEEDED` write does not commit
- the lease later expires and another worker reprocesses the job

Handlers must therefore be idempotent.

6. Version/OCC Role

`version` is part of the canonical architecture.

It is not decorative. It protects against lost updates when a worker or operator acts on stale state after another transaction has already changed the row.