# EPIC-10 --- Pilot Agents

## Цель

Проверить платформу на трех разных сценариях.

## Theory Tutor

Ответы по учебному материалу, объяснение ошибок, рекомендации. Проверяет
conversational flow, context и knowledge tools.

## Lesson Analyzer

Принимает результаты занятия/телеметрии, выделяет наблюдаемые ошибки,
формирует structured разбор. Проверяет большой structured input, data
tools и structured output.

Важно: конкретная схема телеметрии должна определяться контрактом
фактического источника данных. Продуктовая концепция задает
необходимость анализа, но не технический формат телеметрии.

## Progress Coach

Собирает историю занятий и результаты, формирует следующий фокус
обучения. Проверяет несколько tool calls и aggregation; позже может
стать multi-agent workflow.

## Общие требования

Для каждого: JSON Schema input/output, owner, prompt version, allowed
tools, test dataset, positive/negative cases, latency target, error
budget, минимальный evaluation set.

## Acceptance Criteria

-   Все агенты работают через общий Registry/Runtime.
-   Нет отдельного execution framework на агента.
-   Runs видны в общем Inspector.
-   Tool permissions различаются.
-   Версии независимы.
-   Есть automated regression/evaluation набор.
