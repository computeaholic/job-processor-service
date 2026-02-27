CONSTRAINTS — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: 1.0

This document defines non-negotiable constraints for this repository.

No silent changes permitted.

1. Stack Freeze

Language: Python 3.12 (pinned)
Framework: FastAPI
Database: PostgreSQL (single-node)
ORM: SQLAlchemy 2.x (declarative only)
Migration Tool: Alembic
Testing Tools: pytest
Formatting Tools: black
Linting Tools: ruff, mypy
CI Provider: GitHub Actions
Containerization Strategy: Docker (pinned base image, no latest)
Local Orchestration: docker-compose

Changes require:

Written justification in TRADEOFFS.md

Alternatives considered

Impact assessment

SPEC_PACK update

FREEZE.md revision

No stack drift.

2. Dependency Rules

No dependency added without written justification.

No dependency added for convenience.

No dependency added that expands scope implicitly.

No broker libraries (Celery, Redis clients, Kafka clients).

No scheduling libraries.

No experimental libraries.

No observability frameworks (Prometheus, OpenTelemetry).

Allowed external libraries must be:

Production-proven

Directly necessary for defined scope

Minimal in footprint

Each added dependency must document:

Why required

Alternative rejected

Complexity introduced

3. Structural Rules
3.1 Dependency Direction

api → service layer → domain
worker → service layer → domain
infrastructure → injected into service layer
domain must not import infrastructure
domain must not import FastAPI

No circular imports.
No upward imports.

3.2 Layer Isolation

Domain enforces state invariants.

Worker coordinates execution but does not define invariants.

API maps HTTP to service operations only.

Infrastructure owns database wiring only.

Business rules exist only in domain layer.

3.3 Folder Discipline

No utils directory.

No catch-all common directory.

No ambiguous naming.

Folder structure must reflect responsibility:

api/

domain/

worker/

infrastructure/

services/ (if needed for coordination)

Every folder must have a single architectural responsibility.

3.4 Naming Conventions

snake_case modules

PascalCase classes

UPPER_SNAKE constants

Explicit, descriptive identifiers

No abbreviations unless domain standard

4. Transaction Discipline

All database mutations must occur inside explicit with session.begin():

No implicit commits.

No autocommit.

No multi-step writes outside atomic context.

Claim and finalize phases must be separate transactions.

Partial state must never persist.

5. Error Handling Discipline

All API errors must use error envelope contract.

No raw exceptions returned.

No stack traces in responses.

Worker logs failures once at finalization.

No duplicate logging across layers.

6. Documentation Discipline

Concise, structured documentation only.

No speculative extensibility sections.

No future roadmap marketing.

No placeholders.

No incomplete sections.

Documentation must reflect implemented behavior only.

7. Scope Discipline

Scope frozen as of 2026-02-27.

No feature expansion without SPEC_PACK revision.

No implicit enhancements during coding.

No additional endpoints.

No additional entities.

No background scheduler features.

8. Determinism Discipline

No randomness in retry backoff (no jitter).

No time-based behavior without explicit TTL.

Lease TTL must be configurable via environment variable.

All retry logic must be deterministic and testable.

Constraints exist to preserve senior-level discipline,
avoid abstraction theater,
and prevent complexity drift.