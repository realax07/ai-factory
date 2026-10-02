# tasks.md — add-deterministic-flow (срез 1)

- [x] 0.1 План среза + каркас change-пакета (proposal, спека strict-valid) — cc6bb57, d3304c3
- [x] 0.2 Ветка deterministic-flow от main, правило «в main не вливать без решения Заказчика» — принято Заказчиком 2026-10-02
- [ ] 1.1 [S] Поставка 01: contracts/flow_control_contract.md — интерфейсы, scope, граф действий, коды причин, лестница источников, матрица ответственности — 744ab95
- [ ] 1.2 [S] Ревью контракта (независимый ревьюер, Флоу 4 — без обхода review)
- [x] 2.1 [M] Поставка 02: scripts/flow_state.py (inspect, FlowSnapshot, digest, symlink-защита, реестр unknown≠пусто) — c2e65fa
- [x] 2.2 [M] Тесты поставки 02: tests/test_flow_state.py, 24 TC, fixture-репозитории — c2e65fa
- [ ] 2.3 [S] Shadow-прогон flow_state на ekotov-wiki (Флоу 1) и ai-factory (Флоу 4) — выполнен при приемке 2026-10-02 (digest стабилен, read-only, FLOW_ID_INVALID пойман)
- [ ] 3.1 [S] Документы change-пакета: requirements.md (этот), design.md (СД будет по упрощенной схеме Флоу 4 — design.md = настоящий файл-раздел)
- [ ] 3.2 [M] Поставка 03: scripts/flow_transition.py — check_action(snapshot, action) -> Decision, правила Флоу 1–5, [P]-параллель, HUMAN_APPROVAL_REQUIRED, UNKNOWN для provenance-переходов (компат-режим до поставки 05)
- [ ] 3.3 [M] Тесты поставки 03: табличные тесты всех флоу (разрешенный путь / пропущенный этап / чужая роль / нет решения Заказчика / устаревшее evidence)
- [ ] 3.4 [S] CLI check/next + exit 0/1/2, --json стабилен
- [ ] 4.1 [S] Ревью поставки 03 (независимый ревьюер)
- [ ] 4.2 [S] Shadow-прогон check/next на истории Р6 (ekotov-wiki): сверка решений машины с фактически принятыми решениями ПМ; расхождения — в отчет
- [ ] 4.3 [S] Финал: openspec validate strict, flow_check green (после 3.1), pytest green, CI ветки green
- [ ] 4.4 [S] Отчет Заказчику: shadow-сверка, расхождения, предложение по срезу 2 (поставка 04)

## Порядок

1.1 → 1.2 ∥ 2.1 → 2.2 → 2.3 → 3.1 → 3.2 → 3.3 → 3.4 → 4.1 → 4.2 → 4.3 → 4.4.
Ворота: openspec validate --strict green на каждом шаге; flow_check green после 3.1.

## Примечания

- По ОВ-2 (дефолт принят): маркер флоу — строка «Флоу: N» в файле плана задачи (docs/plan-*.md); для Флоу 4 достаточно.
- Поставка 03 НЕ реализует admit_session/run_gates (это поставки 04/05) — контракт описывает их, код не пишет.
