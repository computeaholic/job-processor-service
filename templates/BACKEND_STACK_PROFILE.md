# Backend Stack Profile v1.0

This document defines the canonical backend stack for hireable portfolio projects.

All backend repositories derived from this template must inherit this profile
unless explicitly overridden with documented justification.

This stack is intentionally boring, stable, and production-oriented.

Scope Binding: job-processor-service
Inherited Version: Backend Stack Profile v1.0
Inheritance Date: 2026-02-27

This repository inherits Backend Stack Profile v1.0 without modification.

Any deviation requires:
- Explicit justification in TRADEOFFS.md
- Update to SPEC_PACK.md
- FREEZE.md revision
---

## 1. Language

Python 3.12

Rationale:
- Current LTS-quality version
- Mature ecosystem
- Widely adopted
- Hiring-safe

Rules:
- Version pinning required in `pyproject.toml`. No floating major versions.

---

## 2. Framework

FastAPI

Rationale:
- Clear request/response modeling
- Strong typing integration
- OpenAPI generation
- Minimal magic
- Industry adoption

---

## 3. Data Validation

Pydantic v2

Rationale:
- Explicit data contracts
- Clean schema enforcement
- Tight FastAPI integration

---

## 4. ORM

SQLAlchemy 2.x (Declarative style only)

Rules:
- No legacy query style
- Explicit session handling
- No global sessions
- No implicit commits

Rationale:
- Industry standard
- Mature and predictable
- Demonstrates transactional discipline

---

## 5. Database

PostgreSQL (via Docker for local development)

Rules:
- No SQLite for main portfolio repos
- Constraints must be used intentionally
- Unique indexes required for idempotency scenarios

Rationale:
- Production-realistic
- Concurrency-safe
- Hiring-safe

---

## 6. Migrations

Alembic

Rules:
- All schema changes require migrations
- Downgrade paths must exist
- No schema drift

Rationale:
- Demonstrates operational maturity
- Shows versioned database thinking

---

## 7. Testing

pytest

Optional:
- pytest-asyncio (only if async used)

Coverage target:
80–85%

Rules:
- Unit tests for domain logic
- Integration tests for API behavior
- Concurrency tests where applicable
- Illegal state transitions must be tested

Rationale:
- Balanced realism
- Not academic over-testing
- Not sloppy

---

## 8. Formatting & Linting

- ruff
- black
- mypy

Rules:
- No direct commits to main
- Pre-commit required
- CI enforces lint + type + tests

Rationale:
- Mechanical discipline
- Predictable formatting
- Reduced cognitive load

---

## 9. CI

GitHub Actions

Pipeline must run:
- Lint
- Typecheck
- Tests
- Coverage threshold enforcement
 
Rules:
- Workflow must fail on lint, type, or test failure.
- No manual bypass of required checks.

---

## 10. Docker

Each project must include:

- Dockerfile
- docker-compose.yml
- App container
- Postgres container

Standard Make targets required:

make up
make down
make fmt
make lint
make typecheck
make test
make migrate
make rollback
make run

Rules:
- Base image must be pinned by version tag (no `latest`).

---

## 11. Error Envelope Contract

All error responses must follow this structure:

{
  "error": {
    "code": "string_identifier",
    "message": "Human readable message"
  }
}

Rules:
- No raw stack traces in responses
- No inconsistent error shapes
- Domain errors mapped explicitly

---

## 12. Transaction Discipline

All database mutations must use:

with session.begin():

Rules:
- No implicit commits
- No hidden side effects
- No multi-step mutations outside transaction boundaries

---

## 13. Idempotency Policy

Create operations must define:

- Duplicate behavior
- Constraint enforcement
- IntegrityError mapping to 409
- Explicit documentation in FAILURE_MODES.md

---

## 14. State Discipline

If entities contain state:

- State transitions must be defined in domain layer
- Illegal transitions must raise explicit domain exceptions
- Illegal transitions must be tested

---

## 15. Logging

- Structured logging only
- No print statements
- No logging secrets
- Errors logged once at correct level

---

## 16. Definition of Done

A backend project is complete only if:

- Spec Pack complete
- Scope frozen
- Constraints frozen
- Failure matrix complete
- State model complete
- Migrations working
- Tests passing
- CI green
- No TODO placeholders
- Documentation complete
- Interview Defense doc written

---

This stack profile is frozen for portfolio projects.
Variation requires documented justification.