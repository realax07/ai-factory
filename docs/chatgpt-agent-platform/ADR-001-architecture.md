# ADR-001 --- Базовая архитектура Agent Platform

## Status

Proposed

## Context

Несколько AI-сценариев будут расти по количеству агентов, интеграций и
нагрузке. Отдельная LLM-интеграция для каждой функции дублирует
lifecycle, security и observability.

## Decision

Использовать архитектуру:

``` text
Product Systems / WebUI
          |
      API Layer
          |
     Run Manager
          |
      Queue/Broker
          |
   Agent Runtime Workers
      /          \
 LLM Gateway   Tool Gateway
```

Ключевые abstractions: Agent, AgentVersion, Run, RunStep, Runtime, LLM
Gateway, Tool Registry/Gateway, Evaluation.

## Consequences

Плюсы: единый lifecycle, reproducibility, security, observability,
независимое scaling, foundation для orchestration.

Цена: больше platform code в MVP, формализация contracts, эксплуатация
queue/worker layer.

## Guardrail

Не превращать MVP в универсальный low-code AI-конструктор. Реализовывать
только abstractions, необходимые первым 2--3 агентам, сохраняя
расширяемые interfaces.
