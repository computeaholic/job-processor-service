OPERATIONS — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

This document defines runtime behavior, startup sequence, environment configuration, and recovery procedures.

No operational behavior is implicit.

1. Environment Variables

Required:

Variable	Required	Description	Default
DATABASE_URL	Yes	PostgreSQL connection string	None
WORKER_ID	Yes	Unique identifier for worker instance	None
POLL_INTERVAL_SECONDS	No	Worker poll interval	1
LEASE_TTL_SECONDS	No	Lease expiration window	300
WORKER_BATCH_SIZE	No	Max jobs claimed per poll	10
BASE_BACKOFF_SECONDS	No	Initial retry delay	5
MAX_BACKOFF_SECONDS	No	Maximum retry delay	300

No environment variable may change system invariants.

2. Startup Sequence
2.1 API Startup

Load environment variables.

Establish DB engine.

Verify DB connectivity.

Verify migration level matches latest.

Start FastAPI server.

If DB unreachable:

Readiness returns 503.

API may start but not mark ready.

2.2 Worker Startup

Load environment variables.

Establish DB engine.

Verify DB connectivity.

Start polling loop.

Start lease recovery maintenance loop.

Worker does not start if DB unreachable.

3. Worker Runtime Behavior
3.1 Poll Loop

At each interval:

Begin transaction.

Claim up to WORKER_BATCH_SIZE jobs.

Transition to running.

Commit.

Execution phase:

Process jobs outside claim transaction.

Finalize each job in separate transaction.

No nested transactions permitted.

3.2 Lease Recovery Loop

Runs periodically (every POLL_INTERVAL_SECONDS):

Identify stale running jobs.

Transition stale jobs to pending.

Clear lock fields.

Log once per recovered job.

Lease expiration condition:

locked_at < now - LEASE_TTL_SECONDS

4. Deployment Model

Supported topology:

Single Postgres node

1+ API instances

1+ Worker instances

Concurrency safety guaranteed only within same database.

No cross-database coordination supported.

5. Migration Strategy

All schema changes require Alembic revision.

Upgrade must be applied before app start in production.

Downgrade path must exist.

No manual schema edits.

Startup fails readiness check if migration level is behind.

6. Graceful Shutdown

Worker must:

Stop polling.

Allow in-flight job execution to complete.

Finalize jobs before exit.

Release process cleanly.

If worker terminated abruptly:

Lease TTL recovery will requeue orphaned jobs.

7. Logging Behavior

Structured JSON only.

State transitions logged at INFO.

Retry escalation logged at WARNING.

Dead-letter transitions logged at WARNING.

Unexpected errors logged at ERROR.

No payload bodies logged.

No stack traces exposed via API.

8. Failure Recovery Procedures
8.1 Database Outage

API readiness fails.

Worker exits or loops with backoff.

No state corruption occurs.

Recovery:

Restore DB.

Restart service.

8.2 Worker Crash

Effect:

Running jobs remain locked.

Recovery:

Lease TTL requeues job.

No manual intervention required.

8.3 Poison Job

Condition:

attempt_count >= max_attempts

Effect:

Transition to dead_letter.

No automatic retry.

Recovery:

Manual retry endpoint.

9. Operational Assumptions

Single database authority.

No cross-region deployment.

System clock reasonably synchronized.

Environment variables correctly configured.

Violation of these assumptions invalidates guarantees.

10. Operational Boundaries

This system does not provide:

Horizontal scaling across databases

Automatic shard balancing

Job prioritization

Observability stack

SLA enforcement

Operational guarantees apply only within defined scope.