AI USAGE POLICY — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

This repository permits AI assistance.

AI operates strictly within frozen architectural boundaries.

AI does not define architecture.

1. AI May

AI may:

Implement modules explicitly defined in SPEC_PACK.md.

Generate domain logic that enforces STATE_MODEL.md.

Generate worker logic consistent with CONCURRENCY_MODEL.md.

Generate tests derived from FAILURE_MATRIX.md.

Suggest refactors that do not alter architecture.

Improve clarity, formatting, and naming.

Generate boilerplate wiring (FastAPI, SQLAlchemy, Alembic).

AI implementation must remain deterministic and spec-aligned.

2. AI May Not

AI may not:

Expand scope beyond SPEC_PACK.md.

Introduce new endpoints.

Introduce new entities.

Modify state transitions.

Modify concurrency model.

Modify lease TTL semantics.

Introduce jitter into backoff.

Introduce implicit transactions.

Add background schedulers.

Add new dependencies without updating CONSTRAINTS.md.

Modify error envelope contract.

Introduce caching, brokers, or distributed locks.

AI must not invent architecture.

3. AI Guardrails

Before accepting AI-generated code:

Verify alignment with SPEC_PACK.md.

Verify state transitions match STATE_MODEL.md.

Verify concurrency logic matches CONCURRENCY_MODEL.md.

Verify failure mapping matches FAILURE_MATRIX.md.

Verify transaction boundaries are explicit.

Verify no new dependencies were introduced.

Verify no TODO placeholders remain.

Verify deterministic behavior (no randomness).

If ambiguity arises:

Stop.
Update documentation.
Re-freeze if necessary.

4. Human Responsibility

The engineer remains responsible for:

Architectural integrity

Transaction correctness

Concurrency safety

Idempotency guarantees

Failure modeling completeness

Operational clarity

AI accelerates implementation.

AI does not own correctness.

5. Enforcement

Any AI-generated change that alters:

Scope

State model

Concurrency model

Transaction boundaries

Error contract

requires:

SPEC_PACK.md update

TRADEOFFS.md update

FREEZE.md revision

Commit hash update

No silent architectural mutation permitted.