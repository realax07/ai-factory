# Backlog Summary

  Priority   Epic                    Result
  ---------- ----------------------- --------------------------------------
  P0         EPIC-01 Foundation      Доменная модель, БД, версии, Runs
  P0         EPIC-02 Backend API     Stable API + async run lifecycle
  P0         EPIC-03 Agent Runtime   Исполнение AgentVersion worker-ами
  P0         EPIC-04 LLM Gateway     Независимость от model provider
  P0         EPIC-05 Tool Platform   Безопасные versioned tools
  P0         EPIC-08 Security        Auth/RBAC/permissions/audit
  P1         EPIC-06 WebUI           Управление агентами + Run Inspector
  P1         EPIC-07 Observability   Metrics/traces/evaluation foundation
  P1         EPIC-09 Scalability     Queue/reliability/horizontal scaling
  P1         EPIC-10 Pilot Agents    Проверка на трех сценариях

## Milestones

### M1 --- Execution Core

EPIC-01 + EPIC-02 + EPIC-03 + минимальный EPIC-04. Агент регистрируется
и запускается асинхронно через API.

### M2 --- Controlled Platform

EPIC-05 + EPIC-08 + observability core. Агент безопасно вызывает tools,
выполнение трассируется.

### M3 --- Operator Experience

EPIC-06 + оставшийся EPIC-07. Управление и диагностика доступны через
WebUI.

### M4 --- Pilot

EPIC-10 + нагрузочные сценарии EPIC-09. Три прикладных агента работают
на общей платформе.
