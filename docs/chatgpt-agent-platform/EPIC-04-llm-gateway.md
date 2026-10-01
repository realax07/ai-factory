# EPIC-04 --- LLM Gateway

## Цель

Отвязать runtime от конкретной модели/provider.

## Contract

`generate`, `stream`, `structured_output`; future: `embed`.

Первая реализация --- adapter целевой корпоративной модели/GigaChat.
Другие providers добавляются без изменения runtime.

## Telemetry

Provider, model, latency, tokens in/out, retries, error category,
correlation identifiers.

## Security

Secrets не хранятся в AgentVersion.

## Acceptance Criteria

-   Runtime использует только Gateway interface.
-   Provider меняется конфигурацией.
-   Provider errors нормализуются.
-   Token usage/latency попадают в metrics.
-   Credentials отсутствуют в agent config DB.
