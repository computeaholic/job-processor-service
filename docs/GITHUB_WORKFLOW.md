GITHUB WORKFLOW — job-processor-service

Scope Frozen: 2026-09-20
Spec Version: v1.1

This document defines repository workflow discipline.

Workflow rules are enforceable.

1. Branching Model

Default branch: main

No direct pushes to main

All changes require Pull Request

Required checks must pass before merge

Branch naming conventions:

feature/<short-description>

fix/<short-description>

refactor/<short-description>

chore/<short-description>

docs/<short-description>

Rules:

No long-lived branches.

No branching directly from outdated commits.

Keep branches short-lived and scoped.

2. Commit Format

Commits must be atomic and structured.

Format:

type: concise description

Examples:

feat: implement worker claim transaction

fix: correct lease expiration comparison

refactor: isolate domain transition logic

docs: update failure matrix

chore: pin dependency versions

test: add concurrency ownership test

Rules:

One logical change per commit.

No “misc changes”.

No mixing refactor and feature in one commit.

Freeze commit must be separate and clearly identifiable.

3. Pull Request Rules

Each PR must:

Reference the relevant spec document (SPEC_PACK, STATE_MODEL, etc.).

Explain what changed.

Explain why.

Confirm tests were added or updated.

Confirm no scope expansion (or explicitly document expansion + spec update).

PR description must answer:

What changed?

Why was this necessary?

Which failure modes are affected?

Does this impact complexity budget?

Does this modify transaction or concurrency guarantees?

No PR without explanation.

4. CI Requirements

CI must enforce:

black formatting

ruff linting

mypy type checking

pytest test execution

Coverage threshold (90%)

CI must fail on:

Formatting violations

Lint errors

Type errors

Failing tests

Coverage below defined threshold

No bypass of required checks.

Required checks must be marked as required in GitHub branch protection rules.

5. Freeze Commit Protocol

When specification is frozen:

Commit message must be:

freeze: specification v1.0 locked

FREEZE.md must include commit hash.

No implementation commits may precede freeze commit.

If spec changes later:

Commit message must be:

refreeze: specification vX.Y updated

Freeze is enforceable and auditable.

6. Reproducibility

A clean clone must allow execution of:

make up
make migrate
make test

Without undocumented steps.

Local environment setup must be deterministic.

No hidden prerequisites beyond documented dependencies (Docker, Python).