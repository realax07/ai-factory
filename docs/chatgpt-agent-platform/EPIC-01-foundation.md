# EPIC-01 --- Platform Foundation

## Цель

Создать доменную модель и каркас платформы.

## Сущности

### Agent

`id`, `name`, `description`, `owner`, `status`, `current_version`,
`tags`, timestamps.

### AgentVersion

Immutable после публикации: `id`, `agent_id`, `version`, `model_config`,
`system_prompt`, `parameters`, `tools[]`, `input_schema`,
`output_schema`, `timeout`, `limits`, `status`, `created_by`,
`created_at`.

Lifecycle: `DRAFT -> TEST -> STAGING -> PRODUCTION -> DEPRECATED`.

### Run

`run_id`, `agent_id`, `agent_version_id`, `status`, `input`, `output`,
`context`, `metadata`, timestamps, tokens, latency, error.

Statuses: `CREATED`, `QUEUED`, `RUNNING`, `WAITING_TOOL`, `COMPLETED`,
`FAILED`, `CANCELLED`, `TIMEOUT`.

### RunStep

`step_id`, `run_id`, `parent_step_id`, `type`, `status`, input/output
refs, timestamps, metadata.

Types: `LLM_CALL`, `TOOL_CALL`, `AGENT_CALL`, `SYSTEM`. `AGENT_CALL`
резервируется под future multi-agent.

## Storage

-   PostgreSQL --- metadata/configuration/run index;
-   Redis --- cache, locks, ephemeral state;
-   Object Storage --- большие payload/artifacts/traces;
-   durable queue --- execution jobs.

Не хранить большие traces/телеметрию непосредственно в основных таблицах
PostgreSQL.

## Acceptance Criteria

-   Миграции созданы.
-   CRUD Agent/AgentVersion покрыт тестами.
-   Published AgentVersion нельзя изменить.
-   Run хранит точную AgentVersion.
-   RunStep поддерживает вложенность.
-   Большой payload хранится через object reference.
