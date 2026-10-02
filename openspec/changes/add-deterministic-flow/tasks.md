# tasks.md — add-deterministic-flow (срез 1)

- [x] 0.1 План среза + каркас change-пакета (proposal, спека strict-valid) — cc6bb57, d3304c3
- [x] 0.2 Ветка deterministic-flow от main, правило «в main не вливать без решения Заказчика» — принято Заказчиком 2026-10-02
- [x] 1.1 [S] Поставка 01: contracts/flow_control_contract.md — интерфейсы, scope, граф действий, коды причин, лестница источников, матрица ответственности — 744ab95
- [x] 1.2 [S] Ревью контракта (независимый ревьюер, Флоу 4 — без обхода review) — review-001 RETURN + review-002 APPROVE (R1–R3 перенесены как docs-долг)
- [x] 2.1 [M] Поставка 02: scripts/flow_state.py (inspect, FlowSnapshot, digest, symlink-защита, реестр unknown≠пусто) — c2e65fa
- [x] 2.2 [M] Тесты поставки 02: tests/test_flow_state.py, 24 TC, fixture-репозитории — c2e65fa
- [x] 2.3 [S] Shadow-прогон flow_state на ekotov-wiki (Флоу 1) и ai-factory (Флоу 4) — выполнен при приемке 2026-10-02 (digest стабилен, read-only, FLOW_ID_INVALID пойман)
- [x] 3.1 [S] Документы change-пакета: requirements.md, design.md (D1–D6), sdd.md — b44b6c7
- [x] 3.2 [M] Поставка 03: scripts/flow_transition.py — check_action, правила Флоу 1–5, [P], HUMAN_APPROVAL_REQUIRED, provenance-compat UNKNOWN — 77d2978
- [x] 3.3 [M] Тесты поставки 03: 66 табличных тестов + 14 негативных на фиксы review-001 (104 green) — 77d2978, 72aae6e
- [x] 3.4 [S] CLI check/next + exit 0/1/2, --json стабилен — подтверждено ревьюером живыми пробами
- [x] 4.1 [S] Ревью поставки 03 (независимый ревьюер) — review-001 RETURN (3 major) → fix 72aae6e → review-002 APPROVE (53c13a0)
- [x] 4.2 [S] Shadow-прогон check/next на истории Р6 (ekotov-wiki): 5/8 совпало, 1 ложное разрешение (S5 QA-порядок), 2 ложных запрета (S6 release-до-archive, S7 роль sa) — 8315f9d
- [x] 4.3 [S] Финал: openspec validate strict valid; pytest 104 green; flow_check — 2 остаточных ошибки (J10 по задачам самого change + контракт 6: approved-кейсы — закрываются архивацией пакета, см. примечание)
- [x] 4.4 [S] Отчет Заказчику — см. финальный доклад в чате (2026-10-02)

## Примечание к 4.3

Оставшиеся 2 ошибки flow_check — самоссылочные: ворота J10 требуют code-review
задач 0.1–2.2 (выполнены review-001/002), а контракт 6 — approved-кейсы QA на
тесты срез 1 (тесты писались параллельно циклу по правилам срез 1; QA-контур
на срез 1 Заказчиком не запускался — Флоу 4, экспресс-дисциплина). Обе снимаются
архивацией пакета по решению Заказчика.

## Порядок

1.1 → 1.2 ∥ 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 3.3 → 3.4 → 4.1 → 4.2 → 4.3 → 4.4.
Ворота: openspec validate --strict green на каждом шаге; flow_check green после 3.1.

## Примечания

- По ОВ-2 (дефолт принят): маркер флоу — строка «Флоу: N» в файле плана задачи (docs/plan-*.md); для Флоу 4 достаточно.
- Поставка 03 НЕ реализует admit_session/run_gates (это поставки 04/05) — контракт описывает их, код не пишет.
