# План релиза: J48 — инцидент-протокол Флоу 3

- **Флоу: 1** (полный — change-пакет меняет спеку конвейера и STAGE_TABLE)
- **Change:** add-incident-protocol
- **Дата:** 2026-10-14
- **Автор:** ПМ (план), детализация — СА
- **Санкция Заказчика:** «48 давай» (2026-10-14, диалог)

## Кто что делает, этапы

| Этап | Роль | Что | Артефакт |
|---|---|---|---|
| 1 | БА | Формализовать требования из backlog/J48 (одобрены Заказчиком 2026-10-13, санкция 2026-10-14): severity S1–S3, initial response 0–15 мин, post-mortem S1/S2 | requirements.md пакета |
| 2 | СА | Спека конвейера (дельта: Флоу 3), design (STAGE_TABLE+flow_check изменения), research (по потребности) | openspec/changes/add-incident-protocol/ |
| 3 | Архитектор | Ревью (арх-дельты нет — продуктовых файлов нет; формально N/A) | review-NNN-architecture (если применимо) |
| 4 | dev | flow_transition: severity в incident-маркере, post-mortem-ворота архивации Флоу 3; flow_check: S1/S2 без post-mortem = нарушение; тесты | код + тесты |
| 5 | QA | Кейсы ← спека, автоматизация | test-model/new → approved, тесты |
| 6 | code_reviewer | Ревью | review-файл |
| 7 | dev_lead/ПМ | Merge, зеркало в ekotov-wiki (flow_check/pr_validate/спеки) | PR ×2 |

## Границы

- Затрагивается ТОЛЬКО Флоу 3 (хотфикс); Флоу 1/2/4/5 не меняются
- incident_ref в маркере уже существует — дополняется severity-полем
- Post-mortem хранится в test-model/incidents/ (append-only)

## Критерии готовности

- Спека пакета валидна (openspec validate --strict)
- flow_check: архивация Флоу 3 S1/S2 без post-mortem = нарушение (тест)
- Полный регресс green, зеркало в проекте
