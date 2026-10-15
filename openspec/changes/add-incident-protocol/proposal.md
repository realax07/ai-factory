# Change: add-incident-protocol (инцидент-протокол Флоу 3)

## Why

Протокол реагирования на прод-инциденты не формализован: нет severity-классификации,
нет «кто/что в первые минуты», нет post-incident review. Прецедент — инцидент
2026-10-05 (J25): разбор ad hoc, артефакта не оставил. Источник требований:
`backlog/J48-инцидент-протокол-Флоу-3-claude-skills-2026-10-13.md`; практики —
incident-commander + incident-response (SRE: severity classification, initial
response 0–15 min, post-incident review). Требования утверждены Заказчиком
2026-10-14 (санкция «48 давай»).

## What Changes

- Новая спека `incident-protocol`: severity-матрица S1/S2/S3, initial response
  0–15 минут, post-mortem S1/S2 с воротами архивации, severity-префикс в
  incident_ref (`incident_ref=S1-<краткий-ид>`).
- `scripts/flow_transition.py`: severity-классификация на этапе emergency_stabilize
  (префикс incident_ref), новые этапы Флоу 3 post_mortem и archive_change, ворота
  архивации: S1/S2 без post-mortem в `test-model/incidents/` = DENY.
- `plugins/flow-enforcer/enforcer.py`: severity-префикс проходит через маркер
  делегации без изменений (scope = incident-id).
- Хранилище post-mortem: `test-model/incidents/`, append-only.

## Impact

- Affected specs: новая `incident-protocol` (pipeline/artifacts/qa-pipeline и
  дельта deterministic-flow не трогаются).
- Affected code: `scripts/flow_transition.py` (STAGE_TABLE[3], check-функции),
  `plugins/flow-enforcer/enforcer.py` (маркер), тесты `tests/`.
- Не меняется: Флоу 1/2/4/5; `flow_check.py` (проверка NFR-3 — регресс зеленый).
- Риски: низкие — изменения локальны в ветках flow==3; на срезе enforcement
  behavior детерминирован (файлы + префикс, без LLM).
