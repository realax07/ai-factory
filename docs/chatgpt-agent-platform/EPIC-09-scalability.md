# EPIC-09 --- Scalability & Reliability Foundation

## Цель

Рост от пилота до большого числа параллельных Runs без смены
архитектуры.

## Model

Stateless API replicas + durable queue + horizontally scalable workers +
persistent stores.

API и worker не используют sticky in-memory state для корректности Run.

## Queue Requirements

Durable jobs, bounded retry, lease/visibility semantics, dead-letter
handling, priority foundation, backpressure.

## Reliability

Graceful worker shutdown, recovery stuck jobs, idempotent boundaries,
circuit breaker/provider protection, health/readiness endpoints.

## Future

Worker pools по runtime/model/security zone, team quotas, priority
queues, canary versions, percentage rollout. Multi-region --- не MVP.

## Acceptance Criteria

-   Worker replica увеличивает capacity без изменения API.
-   Worker restart не теряет durable job.
-   Poison job не зацикливается.
-   Queue depth/lag наблюдаемы.
-   API масштабируется независимо от workers.
