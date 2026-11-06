# PLAN-flow-ids: единая грамматика scope флоу (J65.3)

**Флоу: 4** — обслуживание фабрики: внутренняя переработка разбора scope в
движке и энфорсере. Спеки и контракты не меняются; поведение ворот меняется
только в местах расхождения, по решениям Заказчика ниже.

## Найденное расхождение (до правки)

| Флоу | Энфорсер (маркер) | Движок (flow_state) |
|---|---|---|
| Ф2 | имя репорта: BUG-001, BUG-AF-RECHECK-001, BUG-001-slug | только BUG-NNN, регистр не важен |
| Ф3 | только S1-/S2-/S3-…, передается как `--change` | только BUG-NNN → **делегация Ф3 через энфорсер не проходит движок** |
| Ф5 | любая непустая строка | change-id с дефисом |
| Ф1 | любая непустая строка | change-id с дефисом |

## Решения Заказчика (2026-11-05, выбор в диалоге)

- Ф2: «Как имена репортов» — паттерн `BUG_ID_PATTERN` (flow_check).
- Ф3: «S<1-3>-<slug> + легаси BUG» — канон incident-ref; движок принимает и
  BUG-…; энфорсер, как и раньше, требует severity.
- Ф1/Ф5: «Ф1 change-id, Ф5 slug» — Ф1 kebab change-id с дефисом (энфорсер
  отказывает уже на спавне); Ф5 kebab-slug без обязательного дефиса.

## Состав изменений

- `scripts/flow_ids.py` — паттерны, `valid_scope(flow, scope, legacy=True)`,
  `SCOPE_HINTS`, severity-allowlist и `incident_severity`.
- `flow_state` (`check_flow_identifier`, `FLOW_EXPECTATIONS`), `flowctl`
  (`ambiguous_field_hints`), `flow_transition` (severity) — через модуль;
  прежние имена (`CHANGE_ID_RE`, `BUG_ID_RE`, `CHORE_RE`,
  `SEVERITY_PREFIXES`, `SEVERITY_PREFIX_RE`) сохранены как ссылки.
- Энфорсер: один загрузчик `flow_ids` с fallback-копией паттернов;
  `marker_scope_valid` (legacy=False) в `validate_scope_for_flow` для всех
  флоу.
- `flow_check.BUG_ID_PATTERN` остается литералом (копия в проектах
  автономна); совпадение — тестом.
- Шаблон `templates/task_delegation.md`, `docs/README-flow-control.md`,
  `plugins/README.md` — форматы scope и абзац про bypass (замечание ревью).
- Тесты `tests/test_j65_flow_ids.py` (TC-J65-FID-001..007);
  `test_audit_ergonomics` TC-AUD-011 — `[test-adapted]` (подсказка Ф3).

## Вне объема (сознательно)

- Разбор заголовка `flow: …` — только в энфорсере, второго разборщика нет;
  перенос в модуль ничего не дедуплицирует.
- Функция «scope → флоу» из ТЗ: slug неоднозначен (Ф1/Ф4/Ф5), вывести флоу
  из scope нельзя; флоу задается маркером.
- `CHANGE_ID_RE` в `session_check`/`flow_scope_check` — проверка безопасности
  пути (не грамматика флоу).

## Манифест

```yaml
pipeline:
  package: flow-ids
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, plugins/**, tests/**]
      inputs: [backlog/J65-ТЗ-единый-источник-правды-2026-11-03.md]
      task: J65.3 flow_ids.py + перевод вызывающих + копия в энфорсере
      gate: python3 -m pytest tests/ -q
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/flow-ids/review-001.md]
      verdict:
        file: code-reviews/flow-ids/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

## Внимание при выкатке

- Энфорсер на VPS — копия в `~/.hermes/plugins/flow-enforcer/`; после merge
  переустановить плагин (иначе маркер проверяется старой грамматикой).
- Ф1/Ф4/Ф5 маркеры с невалидным scope теперь отказываются на спавне
  (`FLOW_MARKER_INVALID`), а не позже в prepare.

## Критерий закрытия

Полный сьют зеленый, мутации ловятся, `flow_check` OK, ревью «Одобрить»,
CI зеленый; резолюция J65.3 в бэклоге.

## Исполнение

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code);
ревью — независимый сабагент.
