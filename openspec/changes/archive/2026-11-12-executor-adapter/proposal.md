# Proposal: executor-adapter (J65.5 + J64.7)

## Why

Исполнитель агентных стадий прошит в ядре: раннер вызывает только `pi`,
модели берутся из настроек паков, вотчдог обхода видит только делегации
Hermes (`async_delegations`). При смене исполнителя охрана выпадает — урок
перехода на Pi (J59/J63). ТЗ: backlog/J65 (J65.5), backlog/J64 (J64.7).

## What Changes

- deterministic-flow: сменный исполнитель агентных стадий (интерфейс,
  гарантии в раннере); модель и провайдер роли — из реестра ролей и
  манифеста; обход любого исполнителя виден вотчдогу.

Решения Заказчика 2026-11-12 и состав работ — PLAN-executor-adapter.md.

## Impact

- Specs: deterministic-flow (3 ADDED).
- scripts/executors/ (новый), package_runner, delegate_watchdog,
  agents/roles.json, gen_role_docs, гайд манифеста, README flow-control.
