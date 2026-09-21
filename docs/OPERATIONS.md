OPERATIONS — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

This document defines runtime behavior, startup sequence, environment configuration, and recovery procedures.

No operational behavior is implicit.

1. Environment Variables

Required:

Variable	Required	Description	Default
DATABASE_URL	Yes	PostgreSQL connection string	None
WORKER_ID	No	Worker identity override	Hostname-derived
POLL_INTERVAL_SECONDS	No	Worker poll interval	0.5
LEASE_TTL_SECONDS	No	Lease expiration window	30

No environment variable may change system invariants.

2. Startup Sequence
2.1 API Startup

Load environment variables.

Establish DB engine.

Verify DB connectivity through readiness path.

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

Run claim / execute / finalize lifecycle.

Worker does not require the API process to be running.

Runnable command:

make worker

3. Worker Runtime Behavior
3.1 Poll Loop

At each interval:

Begin transaction.

Claim one eligible job.

Transition to PROCESSING.

Commit.

Execution phase:

Process job outside claim transaction.

Finalize in separate transaction.

No nested transactions permitted.

3.2 Lease Recovery Loop

Lease recovery is invoked through the worker-internal reclaim operation.

Identify stale PROCESSING jobs.

Transition stale jobs to PENDING.

Clear lock fields.

Set next_run_at = now.

Log once per recovered job.

Lease expiration condition:

lease_expires_at < now

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

Stop claiming new work after shutdown requested.

Allow in-flight job execution to complete.

Release process cleanly.

If worker terminated abruptly:

Lease TTL recovery will requeue orphaned jobs.

7. Logging Behavior

Structured JSON only.

State transitions logged at INFO.

Retry scheduling logged at INFO/WARNING.

Dead transitions logged at WARNING.

Unexpected errors logged at ERROR/WARNING as appropriate.

No payload bodies logged.

No stack traces exposed via API.

8. Failure Recovery Procedures
8.1 Database Outage

API readiness fails.

Worker exits or loops only under explicit caller control.

No state corruption occurs.

Recovery:

Restore DB.

Restart service.

8.2 Worker Crash

Effect:

Running jobs remain claimed.

Recovery:

Lease TTL requeues job.

No manual intervention required.

8.3 Poison Job

Condition:

retry_count >= max_retries on retryable processing failure

Effect:

Transition to DEAD.

No automatic retry.

Recovery:

No manual retry in this version.

9. Operational Assumptions

Single database authority.

No cross-region deployment.

System clock reasonably synchronized.

Environment variables correctly configured.

Violation of these assumptions invalidates guarantees.

10. Local Commands

make up

make wait-db

make migrate

make rollback

make worker

11. Container Runtime

The root Dockerfile runs the API by default with a pinned Python 3.12 base image and non-root runtime user.

The worker can be launched by overriding the container command to run `python -m job_processor_service.worker_main`.