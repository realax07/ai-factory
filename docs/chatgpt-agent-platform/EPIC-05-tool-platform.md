# EPIC-05 --- Tool Registry & Tool Gateway

## Цель

Контролируемое подключение агентов к бизнес-системам.

## Tool Contract

`name`, `version`, `description`, `input_schema`, `output_schema`,
`permissions`, `timeout`, `owner`, `status`.

Примеры: `get_student_profile`, `get_lesson_history`, `get_telemetry`,
`get_available_slots`, `book_lesson`, `get_exam_results`,
`search_knowledge_base`.

AgentVersion содержит allowlist tools.

## Gateway Responsibilities

Schema validation, authorization, timeout, safe retries, masking,
tracing, error normalization, audit.

Tools классифицируются минимум как `READ_ONLY` и `MUTATING`. Mutating
tools требуют idempotency и отдельных permissions.

## Acceptance Criteria

-   Tool имеет versioned contract.
-   Запрещенный вызов возвращает `TOOL_DENIED`.
-   Input/output валидируются.
-   Каждый call есть в trace.
-   Timeout bounded.
-   Mutating tool имеет idempotency contract.
