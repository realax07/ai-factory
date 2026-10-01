# Agent Platform --- Backlog Pack

## Цель

Разработать внутреннюю платформу для создания, версионирования, запуска,
наблюдения и последующего оркестрирования AI-агентов.

Первый consumer --- цифровая автошкола. Архитектура не должна быть
жестко связана с доменом автошколы, конкретной LLM или единственным
способом исполнения агента.

## Принципы

1.  `Agent` --- логическая сущность; исполняется immutable
    `AgentVersion`.
2.  Каждый запуск фиксируется как `Run` и имеет полный trace.
3.  Выполнение асинхронное; HTTP request не является единицей
    исполнения.
4.  LLM скрыты за `LLM Gateway`.
5.  Внешние системы скрыты за `Tool Gateway / Tool Registry`.
6.  Runtime отделен от конфигурации агента.
7.  Все действия наблюдаемы и аудируемы.
8.  Worker-ы горизонтально масштабируются.
9.  Multi-agent orchestration не входит в первый MVP, но модель данных
    не должна блокировать ее.
10. Security/RBAC/permissions закладываются сразу.

## MVP

-   Agent Registry и Versioning;
-   Run API и async execution;
-   Agent Runtime;
-   LLM Gateway;
-   Tool Registry / Gateway;
-   WebUI и Run Inspector;
-   logs, metrics, traces;
-   authentication/RBAC;
-   2--3 пилотных агента: `theory-tutor`, `lesson-analyzer`,
    `progress-coach`.

## Не входит в MVP

-   drag-and-drop workflow builder;
-   автономный multi-agent planner;
-   marketplace;
-   automatic prompt optimization;
-   собственная vector DB;
-   универсальный memory framework;
-   low-code конструктор.

## Порядок

1.  `EPIC-01-foundation.md`
2.  `EPIC-02-backend-api.md`
3.  `EPIC-03-agent-runtime.md`
4.  `EPIC-04-llm-gateway.md`
5.  `EPIC-05-tool-platform.md`
6.  `EPIC-06-webui.md`
7.  `EPIC-07-observability-evaluation.md`
8.  `EPIC-08-security.md`
9.  `EPIC-09-scalability.md`
10. `EPIC-10-pilot-agents.md`

## Definition of Done MVP

Оператор через WebUI может создать Agent и новую версию, назначить
model/prompt/tools, запустить агента, получить async результат, открыть
полный execution trace, увидеть ошибки/latency/token usage и определить
точную версию, сформировавшую результат. Backend поддерживает несколько
API/worker replicas без изменения контрактов.
