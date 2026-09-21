SPEC PACK — job-processor-service
1. Mission
1.1 System Purpose

When complete, this system provides a database-backed background job processor with deterministic state transitions, controlled retry semantics, and concurrency-safe execution using PostgreSQL row-level locking. It solves the problem of reliably executing asynchronous tasks without introducing external brokers (e.g., Redis, Kafka, Celery) while maintaining strict transaction discipline and explicit failure modeling. The primary user is a backend system or service that needs durable job processing within a single-database architecture. The invariant that must always hold true is: a job may only transition through explicitly legal states, and no eligible job may be concurrently claimed by more than one worker.

2. Scope Definition
2.1 In Scope

Create job

Retrieve job

List jobs (filter by state, bounded limit)

Manual retry from FAILED

Background worker loop

Row-level lock job acquisition

Retry/backoff escalation

Dead terminal state

Explicit state legality enforcement

Deterministic error envelope

Health endpoints

Structured logging

2.2 Out of Scope

Horizontal distributed coordination across databases

Message brokers (Redis/Kafka/Celery)

Public scheduling features

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

Exactly-once external side effects

Complex job DAG orchestration

Job prioritization queues

Multi-queue routing systems

3. Domain Model
3.1 Entities
Entity	Purpose	Owner	Persistence	Notes
Job	Represents a background task and its lifecycle	System	PostgreSQL	Single authoritative entity

No additional entities are defined in this version.

3.2 Persisted Fields

id

client_request_id

job_type

payload

state

error_code

error_message

claimed_by

lease_expires_at

version

retry_count

max_retries

next_run_at

created_at

updated_at

3.3 Invariants

Job id must be unique (DB constraint).

client_request_id must be unique.

job_type must be non-empty.

payload must be persisted as a PostgreSQL JSONB object.

A job must have exactly one valid state.

Only legal state transitions are permitted.

A job in PROCESSING must have claimed_by and lease_expires_at set.

A job not in PROCESSING must not have claimed_by.

retry_count must never exceed max_retries through silent overflow or double increment.

next_run_at must always be set.

Terminal states (SUCCEEDED, DEAD) cannot transition.

All state transitions must occur inside explicit transaction boundaries.

Only one worker may hold a row lock on an eligible PENDING job at a time.

4. State Model
4.1 States

PENDING

PROCESSING

FAILED

SUCCEEDED (terminal)

DEAD (terminal)

4.2 Legal Transitions
From	To	Condition	Enforced Where
PENDING	PROCESSING	Worker acquires row lock	Worker domain logic
PROCESSING	SUCCEEDED	Handler success	Worker domain logic
PROCESSING	PENDING	Retryable failure with budget remaining	Worker domain logic
PROCESSING	FAILED	Non-retryable failure	Worker domain logic
PROCESSING	DEAD	Retry budget exhausted	Worker domain logic
FAILED	PENDING	Manual retry endpoint	API + domain
4.3 Illegal Transitions
Attempted	Expected Error	Code
SUCCEEDED → PENDING	409	JOB_ILLEGAL_TRANSITION
DEAD → PENDING	409	JOB_ILLEGAL_TRANSITION
PENDING → PENDING (retry)	409	JOB_ILLEGAL_TRANSITION
any undefined transition	409	JOB_ILLEGAL_TRANSITION

All illegal transitions must be tested.

5. Interface / API Contract
5.1 Endpoints
Method	Path	Purpose	Idempotent?
POST	/jobs	Create job	Yes (client_request_id + immutable create contract)
GET	/jobs/{id}	Retrieve job	Yes
GET	/jobs?state=&limit=&offset=	Filter jobs	Yes
POST	/jobs/{id}/retry	Retry FAILED job	No
GET	/health/live	Liveness check	Yes
GET	/health/ready	Readiness check	Yes
5.2 Request Models

POST /jobs

job_type: string (required)

payload: object (required)

max_retries: int (required, >=1)

client_request_id: UUID (required)

Validation:

job_type non-empty

payload JSON serializable object

max_retries >= 1

5.3 Response Models

Job response:

id

client_request_id

job_type

payload

state

error_code

error_message

retry_count

max_retries

next_run_at

claimed_by

lease_expires_at

version

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

JOB_PROCESSING_FAILED

JOB_NON_RETRYABLE_FAILURE

DB_UNAVAILABLE

INTERNAL_ERROR

6. Failure Matrix
Scenario	Detected At	User Response	HTTP	Log	Retry?	Idempotent?
Invalid input	API validation	error envelope	422	WARN	No	N/A
Missing job	API lookup	error envelope	404	INFO	No	Yes
Duplicate client_request_id with changed immutable create field	DB/service	409	INFO	No	Yes
Concurrency lock conflict	Worker	silent skip	N/A	DEBUG/INFO	Yes	Yes
DB unavailable	Startup/API	error envelope	503	ERROR	Yes	Yes
Retryable job failure	Worker	PENDING with backoff or DEAD	N/A	WARN/INFO	Yes	Yes
Non-retryable job failure	Worker	FAILED	N/A	WARN	Manual only	Yes
Worker crash mid-run	Recovery scan	job requeued	N/A	WARN	Yes	Yes

7. Transaction Model

Job creation occurs within with session.begin().

Worker claim occurs within explicit transaction.

State finalization occurs within explicit transaction.

No implicit commits allowed.

Isolation: default PostgreSQL READ COMMITTED.

Row acquisition uses SELECT FOR UPDATE SKIP LOCKED.

Idempotency enforced via DB unique constraint on client_request_id.

Version guards reject stale finalize/retry/reclaim writes.

8. Concurrency Model

Optimistic locking: Used.

Versioning: Required.

Concurrency controlled via row-level locking plus version-guarded updates.

Duplicate eligible claim avoided by SKIP LOCKED.

Lease TTL recovery semantics are part of the runtime model.

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