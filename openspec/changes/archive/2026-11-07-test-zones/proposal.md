# Proposal: test-zones (J66)

## Why

Зоны записи тестов не разделены: dev и qa_automation обе пишут в весь
`tests/**`, unit-тесты dev не описаны, автор кода может править приемочные
тесты. Заказчик (2026-11-06): «надо чтобы в папке tests зоны были unit/ web/
api/; api — requests python, web — playwright».

## What Changes

- qa-pipeline: раскладка автотестов tests/unit (dev), tests/api (requests),
  tests/web (playwright, сьют стенда — tests/web/e2e), tests/integration
  (без HTTP и браузера), tests/smoke_cross, tests/archive; проверка раскладки
  с режимом проекта warn|strict; TC-ID — только приемочные уровни; стек
  unit/integration — без сети и браузера.

Решения Заказчика 2026-11-07 и состав работ — PLAN-test-zones.md;
бэклог — backlog/J66-тестовые-зоны-unit-api-web-2026-11-06.md.

## Impact

- Specs: qa-pipeline (2 ADDED, 2 MODIFIED).
- Контракт 6, agents/roles.json, промпты и паки dev/qa_automation,
  flow_check, factory_init, flow_transition (этап qa_automation во Флоу 2–5).
