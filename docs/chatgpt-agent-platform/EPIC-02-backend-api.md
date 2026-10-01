# EPIC-02 --- Backend API & Run Lifecycle

## Цель

Стабильный API для WebUI и продуктовых систем, независимый от
LLM/runtime implementation.

## API

Agents: `POST/GET /api/v1/agents`, `GET/PATCH /api/v1/agents/{id}`.

Versions: `POST/GET /api/v1/agents/{id}/versions`,
`GET /api/v1/agent-versions/{id}`,
`POST /api/v1/agent-versions/{id}/promote`.

Runs: - `POST /api/v1/agents/{agent}/runs` -
`GET /api/v1/runs/{run_id}` - `POST /api/v1/runs/{run_id}/cancel` -
`GET /api/v1/runs/{run_id}/steps` - `GET /api/v1/runs/{run_id}/events`

Streaming MVP: SSE.

## Requirements

Поддержать `Idempotency-Key`, `Correlation-Id`, `Trace-Id`, API
versioning, pagination/filtering и structured errors.

`POST /runs` валидирует input, создает Run, кладет job в очередь и сразу
возвращает `run_id`. Выполнение не зависит от HTTP connection.

## Acceptance Criteria

-   OpenAPI опубликован.
-   Idempotency не допускает duplicate Run.
-   Потеря connection не отменяет Run.
-   Run можно cancel.
-   Status доступен polling-ом, events --- SSE.
-   Ошибки имеют стабильные machine-readable codes.
