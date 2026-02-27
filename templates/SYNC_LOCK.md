SYNC LOCK — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

This document captures the authoritative mission and boundaries of this repository.

It mirrors the ultra-dense sync used to initialize the project.

It exists to prevent context drift.

It is binding.

1. Project Identity

Repository Name:
job-processor-service

Primary Objective:
Build a database-backed background job processor demonstrating deterministic state modeling, row-level concurrency control, retry escalation, and transaction discipline without external brokers.

This repository is intentionally constrained.

It is NOT:

A platform

A startup foundation

A distributed system

A feature playground

A demo scaffold

A technology showcase

It exists to demonstrate senior-level engineering discipline.

2. Core Demonstrations (Non-Negotiable)

This repository must clearly demonstrate:

Explicit job state modeling

Explicit failure modeling (complete failure matrix)

Deterministic error envelope contract

Explicit transaction boundaries (with session.begin():)

Row-level concurrency control (FOR UPDATE SKIP LOCKED)

Lease-based worker recovery

Idempotent job creation via DB constraint

Clean architectural layering (api → services → domain)

Mechanical CI enforcement

Operational clarity (startup, recovery, migration)

These demonstrations define success.

They may not be removed without updating:

SPEC_PACK.md

TRADEOFFS.md

FREEZE.md

3. Stack Lock

This repository inherits:

Backend Stack Profile v1.0

The following are frozen:

Python 3.12

FastAPI

PostgreSQL

SQLAlchemy 2.x

Alembic

pytest

ruff

black

mypy

GitHub Actions

Docker + docker-compose

Stack changes require:

Update to CONSTRAINTS.md

Update to TRADEOFFS.md

Update to SPEC_PACK.md

FREEZE revision

No silent drift.

Dependency direction defined in CONVENTIONS.md is binding.

Layer boundaries are locked upon freeze.

4. Scope Guard

Scope defined in SPEC_PACK.md is binding.

Out-of-scope items are intentional and documented.

No feature may be added without:

SPEC_PACK update

TRADEOFFS update

FREEZE revision

New commit hash recorded

No implicit expansion.
No opportunistic improvements.
No convenience additions.

5. Complexity Budget

Binding limits:

Max endpoints: 6

Max entities: 1 (Job)

Max background processes: 1 worker loop

Max abstraction layers: 3

Target LOC: 2.5k–3.2k

Constraint precedes ambition.

Exceeding budget requires formal revision and re-freeze.

6. Implementation Discipline

No /src implementation may contradict:

STATE_MODEL.md

FAILURE_MATRIX.md

CONCURRENCY_MODEL.md

CONSTRAINTS.md

Error envelope contract

Idempotency policy

If implementation reveals ambiguity:

Stop.
Update spec documents.
Re-freeze before proceeding.

No undocumented behavior allowed.

7. Enforcement

This document functions as a boundary contract.

All engineering decisions must remain consistent with this file.

If drift occurs:

Pause development

Correct documentation

Re-freeze before continuing

This repository is judged on:

Clarity

Correctness

Determinism

Concurrency safety

Transaction integrity

Constraint discipline