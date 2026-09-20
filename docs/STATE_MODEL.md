STATE MODEL — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. States

- `PENDING`
- `PROCESSING`
- `FAILED`
- `SUCCEEDED` (terminal)
- `DEAD` (terminal)

2. State Definitions

`PENDING`

- eligible to be claimed
- `claimed_by` and `lease_expires_at` must both be `NULL`

`PROCESSING`

- owned by exactly one worker
- `claimed_by` and `lease_expires_at` must both be non-`NULL`

`FAILED`

- last processing attempt failed
- `retry_count` has already been incremented
- may be manually retried back to `PENDING`

`SUCCEEDED`

- processing completed successfully
- terminal

`DEAD`

- processing failure budget exhausted
- terminal in this sample

3. Legal Transitions

- `PENDING -> PROCESSING` via worker claim
- `PROCESSING -> SUCCEEDED` on successful handler completion
- `PROCESSING -> FAILED` on failed processing while retries remain
- `PROCESSING -> DEAD` on failed processing when `retry_count` reaches `max_retries`
- `FAILED -> PENDING` via manual retry endpoint

4. Illegal Transitions

Any transition not listed above is illegal.

Examples:

- `PENDING -> SUCCEEDED`
- `PENDING -> PENDING` via retry
- `SUCCEEDED -> PROCESSING`
- `DEAD -> PENDING`

Illegal transitions raise `JOB_ILLEGAL_TRANSITION` and do not mutate state.

5. Retry Counting Semantics

- `retry_count` starts at `0`
- increment happens only when processing fails
- manual retry preserves the current `retry_count`
- `max_retries` is a failure budget, not a count of retry requests

6. Lease and Recovery

- a claim sets `claimed_by` and `lease_expires_at`
- if `lease_expires_at < now`, the job may be reclaimed
- reclaim moves `PROCESSING -> PENDING`
- reclaim clears claim fields
- reclaim does not increment `retry_count`

7. Terminal-State Rules

- `SUCCEEDED` never leaves terminal state
- `DEAD` never leaves terminal state in this repository
- terminal jobs are visible through `GET` and `LIST` only