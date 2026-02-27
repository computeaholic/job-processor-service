CONVENTIONS — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

These conventions are binding for this repository.

They enforce predictability, reduce review overhead, and prevent structural drift.

1. Repository Structure

Backend repository structure must be:

/
  START_HERE.md
  README.md
  SPEC_PACK.md
  CONSTRAINTS.md
  FAILURE_MATRIX.md
  STATE_MODEL.md
  CONCURRENCY_MODEL.md
  TRADEOFFS.md
  INTERVIEW_DEFENSE.md
  OPERATIONS.md
  BACKEND_STACK_PROFILE.md
  CONVENTIONS.md
  FREEZE.md
  /src
    api/
    domain/
    services/        (only if coordination logic required)
    infrastructure/
    config/
    worker/
    main.py
  /tests
  Makefile
  pyproject.toml
  Dockerfile
  docker-compose.yml
  .pre-commit-config.yaml
  .github/workflows/ci.yml

Rules:

No extra top-level folders.

No “misc” or “utils” dumping ground.

No unused folders.

Maximum abstraction layers: 3 (api → services → domain).

Worker is considered coordination layer, not domain.

2. Dependency Direction

Allowed direction:

api → services → domain

worker → services → domain

infrastructure → injected into services

config → may be imported by api/services/infrastructure/worker

domain must not import api/services/infrastructure/config/worker

Rules:

No upward imports.

No circular dependencies.

Domain remains framework-agnostic.

3. Naming Conventions

Files and modules:

snake_case filenames

snake_case module names

No camelCase directories

Classes:

PascalCase

Constants:

UPPER_SNAKE_CASE

Identifiers:

Prefer explicit names.

No cryptic abbreviations.

No single-letter identifiers outside small scopes.

Consistency required across entire project.

4. API Conventions

Error envelope (mandatory):

{
  "error": {
    "code": "machine_identifier",
    "message": "human readable"
  }
}

Rules:

No raw exceptions returned.

No stack traces exposed.

Error codes must match FAILURE_MATRIX.md.

Error mapping occurs only at API boundary layer.

5. Database & Migration Discipline

All schema changes require Alembic revision.

Downgrade paths required.

No schema drift.

Models must match DB state.

Transaction discipline:

All mutations use explicit with session.begin():

No implicit commits.

No hidden multi-step writes.

6. Idempotency & Conflict Handling

Create operations must define idempotency behavior.

Unique DB constraints preferred for dedupe.

IntegrityError mapped deterministically to 409.

Behavior documented in FAILURE_MATRIX.md.

7. Logging Discipline

Structured JSON logging only.

No print statements.

No logging secrets.

Errors logged exactly once at boundary.

Include IDs and state transitions for debugging.

Do not log payload bodies unless explicitly safe.

8. Testing Discipline

Requirements:

pytest required.

Tests derive from:

FAILURE_MATRIX.md

STATE_MODEL.md

CONCURRENCY_MODEL.md

Illegal state transitions must be tested.

Concurrency tests mandatory.

Lease recovery must be tested.

Coverage target: 80–85%.

Rules:

Avoid excessive mocking.

Prefer integration tests for DB behavior.

No flaky timing-based tests.

Concurrency tests must use real DB.

9. Tooling & Quality Gates

Required tools:

ruff

black

mypy

pytest

pre-commit

GitHub Actions

Rules:

No direct push to main.

PR required.

CI must pass lint/type/test.

No bypass of required checks.

No TODO placeholders allowed in final state.

10. Makefile Targets

Required targets:

make fmt

make lint

make typecheck

make test

make test-cov

make up

make down

make run

make migrate

make rollback

Rules:

Must work from clean checkout.

Must be documented in README or OPERATIONS.md.

Must not require manual local setup beyond Docker and Python.

11. Version Pinning

All Python dependencies pinned in pyproject.toml.

Docker base image must be version-pinned (no latest).

Tool versions reproducible.

No floating major versions.

Conventions are binding.

Deviation requires:

Update to TRADEOFFS.md

Update to SPEC_PACK.md (if scope affected)

FREEZE.md revision

New commit hash recorded