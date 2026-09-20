job-processor-service

A PostgreSQL-backed background job processing service focused on durable job lifecycle management and worker coordination.

What it demonstrates

- durable job persistence in PostgreSQL
- worker/API separation
- contention-safe claiming with `FOR UPDATE SKIP LOCKED`
- lease recovery for stranded in-flight jobs
- bounded failure counting with `DEAD` terminal escalation
- durable create replay safety with `client_request_id`
- optimistic concurrency checks via `version`

Architecture

Client API:

- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/retry`
- `GET /health/live`
- `GET /health/ready`

Internal worker operations:

- claim next pending job
- mark processing success
- record processing failure
- reclaim expired leases

Shape:

`client -> FastAPI -> JobService -> PostgreSQL`

`worker -> JobService -> PostgreSQL`

Job lifecycle

`PENDING -> PROCESSING -> SUCCEEDED`

`PENDING -> PROCESSING -> FAILED -> PENDING`

`PENDING -> PROCESSING -> FAILED/DEAD`

`DEAD` and `SUCCEEDED` are terminal.

Failure model

- `retry_count` increments only when processing fails.
- `POST /jobs/{id}/retry` is a manual requeue from `FAILED` back to `PENDING`.
- `max_retries` is a failure budget. When the next processing failure would exhaust that budget, the job becomes `DEAD`.
- Lease recovery requeues expired `PROCESSING` jobs without incrementing `retry_count`.
- Worker execution is at-least-once. If an external side effect succeeds but the completion write does not commit, the effect may happen again on replay. Handlers must be idempotent.

Run

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
make up
make wait-db
make migrate
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/job_processor
.venv/bin/uvicorn job_processor_service.main:app --app-dir src
```

Test

```bash
make lint
make typecheck
make test
make test-cov
make security
```

Demo

Create a job:

```bash
curl -s http://127.0.0.1:8000/jobs \
	-H 'content-type: application/json' \
	-d '{"client_request_id":"11111111-1111-1111-1111-111111111111","max_retries":2}'
```

Fetch it:

```bash
curl -s http://127.0.0.1:8000/jobs/<job-id>
```

The worker lifecycle, retry path, dead escalation, reclaim behavior, and concurrency guarantees are exercised in the test suite.

Status

Engineering sample focused on durable job lifecycle and worker coordination.