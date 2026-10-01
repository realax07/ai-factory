# EPIC-07 --- Observability & Evaluation

## Цель

Сделать поведение и качество агентов измеримыми.

## Correlation

`request -> run -> step -> provider/tool call`.

## Metrics

Runs: count, success/failure/timeout/cancel, queue/execution time,
P50/P95/P99. LLM: requests, latency, tokens, retries, provider errors.
Tools: calls, latency, failures, denied. Infra: queue depth, worker
utilization/failures, storage errors.

Предпочтительный instrumentation standard: OpenTelemetry.

## Evaluation

Сущность: `run_id`, `evaluator`, `metric`, `score`, `reason`,
`metadata`, `created_at`.

Примеры: correctness, relevance, safety, instruction_following,
domain-specific metrics.

## Acceptance Criteria

-   Run находится по Trace ID.
-   UI связывает Run и steps.
-   Есть базовые dashboards.
-   Можно сравнить метрики AgentVersion.
-   Evaluation записывается/читается API.
