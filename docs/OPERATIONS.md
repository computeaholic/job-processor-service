OPERATIONS — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

1. Runtime Inputs

Required:

- `DATABASE_URL`

Local defaults used by the repository tooling point at `localhost:5433` to avoid collisions with other PostgreSQL samples on `5432`.

2. Local Startup

```bash
make up
make wait-db
make migrate
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/job_processor
.venv/bin/uvicorn job_processor_service.main:app --app-dir src
```

3. Migration Operations

- `make migrate` runs `alembic upgrade head`
- `make rollback` runs `alembic downgrade -1`

4. Health Behavior

- liveness returns `200` when the API process is running
- readiness returns `200` only when PostgreSQL is reachable and the DB revision matches Alembic head
- readiness returns `503` when the DB is unavailable or migrations are missing/outdated

5. Worker Operation

The worker is a library-level loop, not a separate HTTP surface.

Operationally it:

- claims one eligible job at a time
- executes the callback
- records `SUCCEEDED`, `FAILED`, or `DEAD`
- supports graceful stop through the provided `Event` in `run_forever()`

6. Recovery Procedures

- worker crash after claim: wait for lease expiry, then reclaim to `PENDING`
- DB outage: readiness fails; no false ready signal is emitted
- exhausted failure budget: job becomes `DEAD` and stays terminal

7. Logging

- structured JSON strings on stdout/stderr via the stdlib logger
- no payload logging
- worker identity included on claim, success, and failure events where relevant