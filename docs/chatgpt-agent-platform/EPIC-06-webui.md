# EPIC-06 --- WebUI

## Цель

UI оператора/разработчика для управления агентами и диагностики.

## Agents

Таблица: Agent, active version, model, status, runs 24h, success rate,
P95, error rate. Search/filter/create/open.

## Agent Page

`Overview`, `Configuration`, `Prompt`, `Tools`, `Versions`, `Runs`,
`Metrics`, `Logs`, `Evaluations`.

Изменение опубликованной конфигурации создает новую version.

## Run Console

Выбрать AgentVersion, задать input/context, запустить Run, наблюдать
events, открыть result.

## Run Inspector

Показывает execution tree/timeline: context -\> LLM -\> tool -\> LLM -\>
completed.

Для step: timestamp, duration, type, status, masked input/output,
model/tool, tokens, retries, error.

## Acceptance Criteria

-   Agent/Draft создаются через UI.
-   Prompt/model/tools настраиваются.
-   Test Run запускается.
-   Streaming events видны.
-   Run Inspector показывает последовательность действий.
-   Runs фильтруются по status/version/time.
