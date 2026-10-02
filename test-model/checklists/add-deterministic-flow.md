# Чеклист QA — change add-deterministic-flow

- **Change:** add-deterministic-flow
- **Статус:** экспресс-дисциплина (Флоу 4) — QA-контур срез 1 не запускался Заказчиком; кейсы утверждены через code-review (review-002/004/006/007, APPROVE), см. test-model/approved/add-deterministic-flow/
- **Источники:** openspec/changes/add-deterministic-flow/specs/deterministic-flow/spec.md, requirements.md (FR-1…FR-8)

| ID | Проверка | Источник | Результат |
|---|---|---|---|
| CHK-001 | flow_mode подключен ко всем компонентам (flowctl/gate_runner/session_check), shadow vs enforcing | FR-1 (Requirement «Честный flow-режим») | TC-FLW-001 |
| CHK-002 | Негативные фиксы review-003: M1–M5, m6–m9 как регрессия | FR-2…FR-6 (Requirement «Честные зоны записи», «Атомарный лок», «Symlink-защита») | TC-FLW-002 |

## Дефекты спеки

Не найдены на момент составления (review-001…007: замечания уровня кода, спека не менялась).
