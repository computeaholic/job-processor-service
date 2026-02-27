TRADEOFFS — job-processor-service

Scope Frozen: 2026-02-27
Spec Version: v1.0

1. Decision Log
Decision	Alternatives Considered	Why Rejected	Cost of This Choice	Where Enforced
Use PostgreSQL row-level locking (FOR UPDATE SKIP LOCKED)	Redis queue, Celery, Kafka	Adds broker complexity; expands scope beyond single-DB service	Polling inefficiency under scale; DB contention	CONCURRENCY_MODEL.md
Single Job entity only	Separate job_effects table, job_type registry	Adds additional entity complexity not required for core goal	Less extensible for external side-effect tracking	SPEC_PACK.md
Explicit transaction boundaries (with session.begin())	Implicit session commits	Hidden side effects; unclear atomicity	Slight verbosity in code	CONSTRAINTS.md
Deterministic backoff without jitter	Exponential backoff with jitter	Non-determinism complicates testing and interview defense	Possible synchronized retry spikes	FAILURE_MATRIX.md
Lease TTL recovery model	Distributed heartbeats or fencing tokens	Adds distributed coordination complexity	Duplicate execution possible after TTL expiry	STATE_MODEL.md
Unique constraint for idempotent job creation	In-memory dedupe, cache-based dedupe	Not durable; race-prone	Requires DB index and constraint management	FAILURE_MATRIX.md
No optimistic locking	Version columns	Not needed with row-level locking	Reduced concurrency flexibility	CONCURRENCY_MODEL.md
No priority queues	Multi-queue design	Out of scope; adds scheduling complexity	No fine-grained job prioritization	SPEC_PACK.md
No authentication	API key, JWT	Internal service assumption; not core objective	Not production-exposed safe	SPEC_PACK.md
2. Scope Exclusions (Intentional Non-Build)
Excluded Feature	Why Not Built	Risk / Cost of Exclusion	When It Would Be Added
External broker (Redis/Kafka)	Demonstrate DB-native queue	DB load increases with scale	At sustained high throughput
Distributed coordination	Single DB design	Not horizontally scalable across regions	Multi-region deployment requirement
Metrics/Tracing stack	Avoid observability framework creep	Reduced production visibility	Production deployment
Auth/RBAC	Internal service assumption	Not safe for public exposure	External API exposure
Priority scheduling	Not required for lifecycle modeling	FIFO only	SLA-tiered job processing
3. Complexity Avoidance

No external queue — avoids broker operations, network partitions, delivery semantics.

No distributed locks — avoids coordination complexity.

No caching layer — avoids invalidation logic; correctness prioritized.

No version columns — row locks sufficient.

No DAG orchestration — single-step job lifecycle only.

No multi-entity model — maintain minimal invariant surface.

4. 10x Scale Notes

Bottleneck: Database contention during high worker concurrency.

Mitigation: Increase poll interval, batch size tuning, add partial index optimization.

First extraction boundary: Replace polling with broker-backed queue while preserving state model.

No claims of automatic horizontal scale.

5. Freeze Rule

Any change to a major decision requires:

Update SPEC_PACK.md

Update this TRADEOFFS.md

Update FREEZE.md

Record new commit hash

Tradeoffs are binding.