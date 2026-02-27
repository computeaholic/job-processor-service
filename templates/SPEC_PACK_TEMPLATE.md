SPEC PACK — job-processor-service
1. Mission
1.1 System Purpose

When complete, this system provides a database-backed background job processor with deterministic state transitions, controlled retry semantics, and concurrency-safe execution using PostgreSQL row-level locking. It solves the problem of reliably executing asynchronous tasks without introducing external brokers (e.g., Redis, Kafka, Celery) while maintaining strict transaction discipline and explicit failure modeling. The primary user is a backend system or service that needs durable job processing within a single-database architecture. The invariant that must always hold true is: a job may only transition through explicitly legal states, and no job may be concurrently executed by more than one worker.

2. Scope Definition
2.1 In Scope

Create job

Retrieve job

List jobs (filter by status)

Manual retry (for eligible states)

Background worker loop

Row-level lock job acquisition

Retry/backoff escalation

Dead-letter terminal state

Explicit state legality enforcement

Deterministic error envelope

Health endpoints

Structured logging

2.2 Out of Scope

Horizontal distributed coordination across databases

Message brokers (Redis/Kafka/Celery)

Cron scheduling features

Multi-tenant authentication/RBAC

UI/frontend

Metrics dashboards/tracing systems

Distributed tracing

Cross-region failover

External task orchestration

AI integrations

2.3 Non-Goals

High-throughput event streaming

Millisecond latency guarantees

At-least-once delivery across networks

Complex job DAG orchestration

Job prioritization queues

Multi-queue routing systems

3. Domain Model
3.1 Entities
Entity	Purpose	Owner	Persistence	Notes
Job	Represents a background task and its lifecycle	System	PostgreSQL	Single authoritative entity

No additional entities are defined in this version.

3.2 Invariants

Job id must be unique (DB constraint).

client_request_id must be unique if provided (DB unique constraint).

A job must have exactly one valid state.

Only legal state transitions are permitted.

A job in running must have locked_by and locked_at set.

A job not in running must not have locked_by.

attempt_count must never exceed max_attempts.

Terminal states (completed, dead_letter) cannot transition except via manual retry (if allowed).

All state transitions must occur inside explicit transaction boundaries.

Only one worker may hold a row lock on a job at a time.

Enforced in:

Database constraints (uniqueness)

Domain logic (state transitions)

Worker transaction boundaries

4. State Model
4.1 States

pending

running

completed (terminal)

failed

dead_letter (terminal)

4.2 Legal Transitions
From	To	Condition	Enforced Where
pending	running	Worker acquires row lock	Worker domain logic
running	completed	Handler success	Worker domain logic
running	failed	Non-retryable failure	Worker domain logic
failed	pending	Retryable + attempts remain	Worker domain logic
failed	dead_letter	Attempts exhausted	Worker domain logic
dead_letter	pending	Manual retry endpoint	API + domain
4.3 Illegal Transitions
Attempted	Expected Error	Code
completed → pending	409	JOB_ILLEGAL_TRANSITION
dead_letter → running	409	JOB_ILLEGAL_TRANSITION
running → pending (external)	409	JOB_ILLEGAL_TRANSITION
any undefined transition	409	JOB_ILLEGAL_TRANSITION

All illegal transitions must be tested.

5. Interface / API Contract
5.1 Endpoints
Method	Path	Purpose	Idempotent?
POST	/jobs	Create job	Yes (client_request_id)
GET	/jobs/{id}	Retrieve job	Yes
GET	/jobs?status=	Filter jobs	Yes
POST	/jobs/{id}/retry	Retry dead-letter job	No
GET	/health/live	Liveness check	Yes
GET	/health/ready	Readiness check	Yes
5.2 Request Models

POST /jobs

job_type: string (required)

payload: object (required)

max_attempts: int (required, >=1)

client_request_id: UUID (required for idempotency)

Validation:

job_type non-empty

payload JSON serializable

max_attempts >= 1

5.3 Response Models

Job response:

id

job_type

status

attempt_count

max_attempts

last_error_code

next_run_at

created_at

updated_at

5.4 Error Envelope Contract

All errors:

{
  "error": {
    "code": "machine_identifier",
    "message": "human readable"
  }
}

Error Codes:

JOB_NOT_FOUND

JOB_IDEMPOTENCY_CONFLICT

JOB_ILLEGAL_TRANSITION

JOB_MAX_ATTEMPTS_EXCEEDED

JOB_TIMEOUT

JOB_LEASE_EXPIRED

VALIDATION_ERROR

DB_UNAVAILABLE

INTERNAL_ERROR

6. Failure Matrix
Scenario	Detected At	User Response	HTTP	Log	Retry?	Idempotent?
Invalid input	API validation	error envelope	422	WARN	No	N/A
Missing job	API lookup	error envelope	404	INFO	No	Yes
Duplicate client_request_id	DB unique constraint	error envelope	409	INFO	No	Yes
Concurrency lock conflict	Worker	silent skip	N/A	DEBUG	Yes	Yes
DB unavailable	Startup/API	error envelope	503	ERROR	Yes	Yes
Handler timeout	Worker	state change	N/A	ERROR	Yes	Yes
Attempts exhausted	Worker	dead_letter	N/A	WARN	No	Yes
Partial transaction	DB rollback	none persisted	500	ERROR	Yes	Yes
Worker crash mid-run	Lease recovery	job requeued	N/A	WARN	Yes	Yes
7. Transaction Model

Job creation occurs within with session.begin().

Worker claim occurs within explicit transaction.

State finalization occurs within explicit transaction.

No implicit commits allowed.

Isolation: default PostgreSQL READ COMMITTED.

Row acquisition uses SELECT FOR UPDATE SKIP LOCKED.

Idempotency enforced via DB unique constraint on client_request_id.

Atomic operations:

Claim + status transition

Finalize + retry/backoff decision

8. Concurrency Model

Optimistic locking: Not used.

Versioning: Not required.

Concurrency controlled via row-level locking.

Duplicate job execution avoided by SKIP LOCKED.

Lease TTL: 5 minutes.

Stale running jobs (locked_at older than TTL) are requeued.

Two workers competing:

Only one acquires lock.

Other skips locked row.

No duplicate running state allowed.

9. Observability
9.1 Logging

Structured JSON logs

Levels: DEBUG, INFO, WARN, ERROR

Log state transitions

Log failure once

Never log:

secrets

raw stack traces in API responses

payload contents unless safe

9.2 Health

Liveness:

Returns 200 if process alive.

Readiness:

Returns 200 if:

DB reachable

Migrations current

9.3 Metrics

Not implemented (explicit non-goal).

10. Constraints

Python 3.12

FastAPI

Pydantic v2

SQLAlchemy 2.x

PostgreSQL

Alembic

pytest

ruff

black

mypy

GitHub Actions CI

Docker (pinned image)

New dependencies require ADR.

11. Complexity Budget

Max endpoints: 6

Max entities: 1

Max background processes: 1 worker loop

Target LOC: 2.5k–3.2k

Max abstraction layers: 3 (API / Domain / Worker)

Exceeding requires spec revision.

12. Testing Strategy

Unit:

State transitions

Backoff function

Illegal transitions

Integration:

Job lifecycle

Idempotency

Retry escalation

Concurrency:

2 workers, single ownership

Lease recovery

Migration:

Upgrade + downgrade tested

Coverage:

80–85%

All illegal transitions explicitly tested.

13. Security Considerations

No authentication (internal service assumption)

No authorization model

Input validation via Pydantic

No secrets stored in DB

Error messages sanitized

14. Operational Considerations

Environment Variables:

DATABASE_URL

WORKER_ID

POLL_INTERVAL

LEASE_TTL_SECONDS

Startup:

Run migrations

Start API

Start worker

Rollback:

Alembic downgrade supported

Deployment:

Single database assumption

Multiple workers allowed

15. Tradeoffs

Why not Celery/Kafka?

Intentional constraint to demonstrate DB-native queue.

Avoided complexity:

External brokers

Priority queues

Distributed locks

At 10x scale:

Polling becomes inefficient.

DB contention increases.

Requires sharding or broker.

First thing to break:

Lock contention under high worker concurrency.

16. Definition of Done

 Spec Pack complete

 Scope frozen (date stamped)

 FREEZE.md committed

 Constraints frozen

 Failure matrix complete

 State model complete

 Concurrency model defined

 Complexity budget declared

 Tests passing

 CI passing

 No TODO placeholders

 Documentation complete

 Interview Defense doc written

17. Risk Register

Technical risk:

Lease recovery edge cases
Mitigation: Explicit recovery tests

Operational risk:

Worker stuck in loop
Mitigation: Health readiness + logging

Complexity risk:

State explosion over time
Mitigation: Single entity policy

Owner: Repository maintainer
Monitoring: CI + test suite
Trigger: Failed concurrency or state transition test