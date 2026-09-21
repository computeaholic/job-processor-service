STATE MODEL — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: 1.1

This document defines the authoritative lifecycle for the Job entity.

No implicit transitions permitted.
All transitions must be explicitly modeled and tested.

1. States

Valid States:

PENDING

PROCESSING

FAILED

SUCCEEDED (terminal)

DEAD (terminal)

Terminal States:

SUCCEEDED

DEAD

Terminal states may not transition except via explicitly defined rules.

2. State Definitions
PENDING

Job is eligible for execution when:

next_run_at <= now

No worker currently owns the job.

claimed_by must be NULL.

lease_expires_at must be NULL.

PROCESSING

Job is actively being processed by a worker.

claimed_by must be set.

lease_expires_at must be set.

Worker must hold row-level lock at claim time.

FAILED

Job execution failed in a non-retryable or operator-intervention path.

retry_count has already been incremented.

May transition back to PENDING only through manual retry.

SUCCEEDED (terminal)

Job successfully executed.

No further transitions allowed.

DEAD (terminal)

Job exceeded max retries through retryable processing failure.

No manual retry is allowed in this version.

3. Legal Transitions
From	To	Condition	Enforced In
PENDING	PROCESSING	Worker acquires job via FOR UPDATE SKIP LOCKED	Worker
PROCESSING	SUCCEEDED	Handler returns success	Worker
PROCESSING	PENDING	Retryable failure and retry_count < max_retries	Worker
PROCESSING	FAILED	Handler raises NonRetryableJobError	Worker
PROCESSING	DEAD	Retryable failure and retry_count >= max_retries	Worker
FAILED	PENDING	Manual retry endpoint invoked	API + Domain
4. Illegal Transitions

The following transitions are explicitly illegal:

Attempted	Behavior	Error Code
SUCCEEDED → any state	Reject	JOB_ILLEGAL_TRANSITION
PENDING → SUCCEEDED (external)	Reject	JOB_ILLEGAL_TRANSITION
PENDING → PENDING (retry)	Reject	JOB_ILLEGAL_TRANSITION
DEAD → PENDING	Reject	JOB_ILLEGAL_TRANSITION
any undefined transition	Reject	JOB_ILLEGAL_TRANSITION

Illegal transitions:

Return HTTP 409 (if API initiated)

Log once at WARNING level

Do not mutate state

All illegal transitions must be tested.

5. Attempt Counting Semantics

retry_count starts at 0.

Increment occurs after processing failure.

Automatic retry allowed when:

retry_count < max_retries

When:

retry_count >= max_retries

Transition to DEAD.

Manual retry preserves retry_count.

No off-by-one ambiguity permitted.

6. Lease & Recovery Rules

Lease TTL: configurable (default 30 seconds in local entrypoint settings)

A job in PROCESSING is considered stale when:

lease_expires_at < now

Recovery behavior:

Stale job transitions to PENDING

claimed_by cleared

lease_expires_at cleared

next_run_at = now

retry_count unchanged

Recovery is worker responsibility.

7. Invariant Guarantees

A job may only exist in one state.

A job may only be in PROCESSING when owned by exactly one worker.

A job in SUCCEEDED or DEAD must never be auto-retried.

State transitions must occur inside explicit transaction boundaries.

No state mutation may occur outside transaction.

8. Enforcement Requirements

All state transitions must pass through domain logic.

Worker must never mutate state directly without domain validation.

API retry endpoint must validate legal source state.

Tests must derive from this document.

State discipline is core system integrity.