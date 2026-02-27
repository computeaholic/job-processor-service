job-processor-service

A database-backed background job processing service designed to demonstrate deterministic state modeling, row-level concurrency control, retry escalation, and explicit transaction discipline.

This repository is intentionally constrained and specification-first.

It exists to demonstrate senior-level backend engineering discipline.

Purpose

This service implements:

Explicit job state transitions

Deterministic failure modeling

Row-level locking using FOR UPDATE SKIP LOCKED

Retry with exponential backoff

Escalation to dead-letter state

Idempotent job creation via database constraint

Explicit transaction boundaries

Clean architectural layering

Mechanical CI enforcement

No external brokers.
No distributed coordination claims.
Single-database concurrency model.

Architecture Overview

Core entity:

Job

Worker model:

Polls eligible jobs (status = pending AND next_run_at <= now)

Claims via row-level lock

Transitions to running

Executes handler

Transitions to:

completed

pending (retry with backoff)

failed

dead_letter

All mutations occur within explicit transaction boundaries.

Stack

This project inherits Backend Stack Profile v1.0:

Python 3.12

FastAPI

PostgreSQL

SQLAlchemy 2.x

Alembic

pytest

ruff / black / mypy

GitHub Actions CI

Docker + docker-compose

Dependencies are pinned.
No silent drift allowed.

Repository Structure
/docs
/src
/tests
Makefile
pyproject.toml
Dockerfile
docker-compose.yml

Full specification lives in:

docs/SPEC_PACK.md

docs/FAILURE_MODES.md

docs/STATE_MODEL.md

docs/CONCURRENCY_MODEL.md

docs/CONSTRAINTS.md

docs/TRADEOFFS.md

docs/INTERVIEW_DEFENSE.md

docs/FREEZE.md

Implementation must not contradict these documents.

Local Development

From a clean clone:

make up
make migrate
make run

Testing:

make test
make test-cov

Formatting / linting:

make fmt
make lint
make typecheck

Rollback migration:

make rollback

All commands must work from a clean environment.

Guarantees

No implicit commits

No silent failures

Deterministic error envelope

Explicit state transition enforcement

Retry policy formally modeled

Concurrency safety via database locking

Worker crash recovery via lease expiry

No TODO placeholders in finished implementation

Status

Specification-first project.

Implementation begins only after freeze.

See docs/FREEZE.md for binding freeze declaration.