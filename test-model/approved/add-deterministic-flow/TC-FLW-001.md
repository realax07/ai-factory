# TC-FLW-001

- **Кейс:** Инфраструктура flow-режима подключена ко всем компонентам
- **Change:** add-deterministic-flow
- **Источник:** code-reviews/add-deterministic-flow/review-007.md (вердикт APPROVE) — §5: полный прогон 327 passed, live-пробы flowctl/flow_mode
- **Статус:** approved (вердикт code-review APPROVE; автотесты green)

## Трассировка

- Источник требования: openspec/changes/add-deterministic-flow/specs/deterministic-flow/spec.md
- Чеклист: test-model/checklists/add-deterministic-flow.md (CHK-строки ниже)
- Реализация: tests/test_flow_mode_integration.py

[CHK-1] Проверка кейса TC-FLW-001 — автотесты в tests/test_flow_mode_integration.py green (прогон ревьюера review-007).

## Сценарий

1. Задать FLOW_MODE_FILE в режимах shadow/enforcing; вызвать flowctl run/prepare/finish, gate_runner run/status, session_check reserve/check/reconcile/status.
2. Ожидание: shadow — решения вычисляются, но не блокируют; enforcing — DENY/UNKNOWN блокируют с кодом причины; mode присутствует в ответах. Подтверждено автотестами (21 тест).
