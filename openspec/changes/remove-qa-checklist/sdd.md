# SDD: remove-qa-checklist

**Флоу: 1**

Кратко (полный дизайн — design.md): этап qa_checklist (роль, чеклист CHK-N,
контракт 3/4-требования «кейсы без чеклиста») удален из машинного графа и
промптов фабрики и проекта. Точки изменения:

| Точка | Было | Стало |
|---|---|---|
| flow_transition STAGE_TABLE | Stage qa_checklist (контракт 3) | удален; qa_cases — вход от спеки (`change.spec_deltas`/`specs.present`) |
| flow_check контракт 3 | валидация CHK-чеклистов | удалена (чеклисты — append-only история) |
| flow_check контракт 4 | «кейсы без чеклиста» + CHK-трассировка | трассировка кейса к `### Requirement:`/`#### Scenario:` master-spec/дельт |
| pr_validate | чеклист обязателен для change-PR | не требуется |
| role_zone_policy / agents/README | роль qa_checklist | удалена; промпт в agents/archive/ |
| проект ekotov-wiki | flow_check + промпты | тонкий клиент синхронизирован; чеклисты в test-model/checklists/archive/ |

Трассировка: FR-1–FR-6 requirements.md → задачи 1.1–2.2 tasks.md → дельты
specs/qa-pipeline (Последовательность QA-этапов), specs/artifacts (Трассировка
требований, Директории QA-артефактов).
