# Решение Заказчика 2026-10-07-code-review-flow2

**Дата:** 2026-10-07
**Источник:** Заказчик, Telegram DM, 2026-10-07: «Давай поправим ядро» — в ответ на
эскалацию ПМ о пробеле графа Флоу 2 (факты DENY: deleg-56264f9c99c6458f INVALID_GATE
по task 0.1 flow1; deleg-05f5d40718134f07 BUG-010 — accept_review MISSING_INPUT
«reviews.approved отсутствует», code_review в графе Флоу 2 отсутствует).

**Смысл:** инцидент BUG-010 (PR #70 ekotov-wiki) влит без независимого ревью —
легального действия «написать ревью» в Флоу 2 нет: accept_review требует уже
существующий approve (замкнутый круг), code_review отсутствует как стадия,
ревью через Флоу 1 запрещено (задача пакета закрыта — история не переписывается).

**Action:** аддитивная стадия `code_review` (роль `code_reviewer`) в граф Флоу 2
между `bug_fix` и `accept_review` в обоих репо (эталон ai-factory + проектная
копия ekotov-wiki), синхронно; зона роли уже покрывает `code-reviews/*/review-*.md`.
Retrospective-ревью BUG-010 (ekotov-wiki PR #70, коммиты 2622979/d718306) провести
после правки ядра по новой стадии.

```decision-record
{
  "schema_version": "decision-record/1",
  "decision_id": "2026-10-07-code-review-flow2",
  "date": "2026-10-07",
  "scope": {
    "project": "wiki",
    "change_id": "BUG-010",
    "phase": 2
  },
  "action": "accept_review",
  "commit": "d8c2553",
  "source": "Заказчик, Telegram DM 2026-10-07: «Давай поправим ядро» — расширение графа Флоу 2 стадией code_review (оба репо) + ретроспективное ревью BUG-010"
}
```
