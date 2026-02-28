STATE MODEL — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: 1.0

This document defines the authoritative lifecycle for the Job entity.

No implicit transitions permitted.
All transitions must be explicitly modeled and tested.

1. States

Valid States:

pending

running

failed

completed (terminal)

dead_letter (terminal)

Terminal States:

completed

dead_letter

Terminal states may not transition except via explicitly defined manual retry rule.

2. State Definitions
pending

Job is eligible for execution when:

next_run_at <= now

No worker currently owns the job.

locked_by must be NULL.

locked_at must be NULL.

running

Job is actively being processed by a worker.

locked_by must be set.

locked_at must be set.

Worker must hold row-level lock at claim time.

failed

Job execution failed.

Failure may be retryable.

attempt_count incremented.

May transition back to pending if retryable and attempts remain.

completed (terminal)

Job successfully executed.

No further transitions allowed.

dead_letter (terminal)

Job exceeded max attempts or escalated.

Requires manual retry to re-enter lifecycle.

3. Legal Transitions
From	To	Condition	Enforced In
pending	running	Worker acquires job via FOR UPDATE SKIP LOCKED	Worker
running	completed	Handler returns success	Worker
running	failed	Handler raises NonRetryableJobError	Worker
running	failed	Handler raises RetryableJobError (intermediate state)	Worker
failed	pending	attempt_count < max_attempts AND error retryable	Worker
failed	dead_letter	attempt_count >= max_attempts	Worker
dead_letter	pending	Manual retry endpoint invoked	API + Domain
4. Illegal Transitions

The following transitions are explicitly illegal:

Attempted	Behavior	Error Code
completed → any state	Reject	JOB_ILLEGAL_TRANSITION
pending → completed (external)	Reject	JOB_ILLEGAL_TRANSITION
running → pending (external)	Reject	JOB_ILLEGAL_TRANSITION
dead_letter → running	Reject	JOB_ILLEGAL_TRANSITION
any undefined transition	Reject	JOB_ILLEGAL_TRANSITION

Illegal transitions:

Return HTTP 409 (if API initiated)

Log once at WARNING level

Do not mutate state

All illegal transitions must be tested.

5. Attempt Counting Semantics

attempt_count starts at 0.

Increment occurs after handler failure.

Retry allowed when:

attempt_count < max_attempts

When:

attempt_count >= max_attempts

Transition to dead_letter.

No off-by-one ambiguity permitted.

6. Lease & Recovery Rules

Lease TTL: configurable (default 300 seconds)

A job in running is considered stale when:

locked_at < now - lease_ttl

Recovery behavior:

Stale job transitions to pending

locked_by cleared

locked_at cleared

next_run_at = now

attempt_count unchanged

Logged as:
JOB_LEASE_EXPIRED

Recovery is worker responsibility.

7. Invariant Guarantees

A job may only exist in one state.

A job may only be in running when owned by exactly one worker.

A job in completed or dead_letter must never be auto-retried.

State transitions must occur inside explicit transaction boundaries.

No state mutation may occur outside transaction.

8. Enforcement Requirements

All state transitions must pass through domain logic.

Worker must never mutate state directly without domain validation.

API retry endpoint must validate legal source state.

Tests must derive from this document.

State discipline is core system integrity.