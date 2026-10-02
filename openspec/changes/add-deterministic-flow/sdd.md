# SDD — add-deterministic-flow (срез 1)

> Примечание Флоу 4:change-пакет обслуживает фабрику; полный SDD-цикл не требуется,
> но для целостности контракта 2 здесь зафиксированы трассировка и границы решения.

## Трассировка

| Артефакт | Реализация | Тесты |
|---|---|---|
| FR-1/FR-2/NFR-2/3 (снимок) | scripts/flow_state.py (c2e65fa) | tests/test_flow_state.py TC-FST-001…014 (24) |
| FR-3/FR-4/FR-5/FR-6/FR-7/FR-8 (решение) | scripts/flow_transition.py (поставка 03) | tests/test_flow_transition.py (табличные, 3.3) |
| Спека deterministic-flow (8 Req / 16 сценариев) | contracts/flow_control_contract.md (744ab95) + два скрипта | те же |
| Этапные ворота (FR-6) | approval_ref + файл плана «Флоу: N» (ОВ-2) | сценарий «Решение другой фазы» |

## Границы среза 1 (не делаем)

- admit_session / run_gates — контракт описан (744ab95), исполнение в поставках 04/05.
- provenance-инфраструктура review — поставка 05; срез 1 дает честный UNKNOWN.
- Enforcement, HTTP/WebUI, авто-adapter Hermes — вне MVP по ТЗ 06.

## DoD среза 1

openspec strict valid; flow_check green (после добора документов пакета и фактических
ревью 1.2/4.1); pytest green (flow_state 24 + flow_transition табличные); shadow-прогон
check/next на истории Р6 с отчетом о расхождениях машине/ПМ (4.2) — Заказчику.
