# EPIC-03 --- Agent Runtime

## Цель

Независимый execution layer для исполнения AgentVersion без доменной
логики.

## Responsibilities

Prompt assembly, context, LLM invocation, structured output, tool calls,
retries, timeout, token limits, cancellation, guardrail hooks, tracing,
RunStep persistence, error normalization.

## Constraints

Runtime не знает бизнес-логику автошколы, не вызывает provider SDK вне
LLM Gateway, не обращается к внешним системам вне Tool Gateway и не
полагается на in-memory state.

## Extensibility

Интерфейс должен допускать `SimpleAgentRuntime`, `ReActRuntime`,
`WorkflowRuntime`, `MultiAgentRuntime`. MVP реализует только минимально
необходимый runtime.

## Failure model

Provider/tool timeout, malformed output, tool denied, rate limit,
cancellation, max steps/tokens exceeded, internal error.

## Acceptance Criteria

-   Worker запускает runtime независимо от API.
-   Restart worker не оставляет Run навсегда `RUNNING`.
-   LLM/tool действия создают RunStep.
-   Timeout/cancellation дают предсказуемый terminal status.
-   Retry ограничен policy и виден в trace.
