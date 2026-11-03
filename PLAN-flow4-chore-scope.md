# PLAN-flow4-chore-scope: scope Флоу 4 = chore-slug (J64.3)

**Флоу: 4** — обслуживание фабрики: правка движка (`flow_state`/`flowctl`)
и энфорсера, спеки и контракты не меняются. Решение Заказчика (2026-11-03):
вариант (а) J64.3 — scope Флоу 4 принимает `chore` и kebab-slug.

## Цель

Пакеты обслуживания называются `<slug>` с планом `PLAN-<slug>.md` (J43.1),
а `flow_state.CHORE_RE = ^chore$` признавал только буквальное `chore`:
реальный `flowctl prepare` давал UNKNOWN `AMBIGUOUS_STATE`, энфорсер гасил
это постфильтром только в dry-run, package_runner (J63) останавливался —
пакеты Флоу 4 через раннер не проходили.

## Состав изменений

1. `scripts/flow_state.py`: `CHORE_RE` — `chore` или kebab-slug
   (`^[a-z0-9]+(?:-[a-z0-9]+)*$`); текст `FLOW_ID_INVALID`.
2. `scripts/flowctl.py`: подсказка `field_diagnostics` для Флоу 4.
3. `plugins/flow-enforcer/enforcer.py`: из `NO_CHANGE_DETAIL_PATTERNS`
   удален Ф4-костыль «scope не соответствует выбранному флоу» — отказ
   теперь только по существу.
4. Тесты: `test_flow_state` (slug валиден, мусор — FLOW_ID_INVALID),
   раннер Флоу 4 со slug-пакетом проходит ворота (реальные flowctl).

Зона `plugins/**` не входит в политику зон ни одной роли (agents/README.md)
— стадия правки энфорсера в манифесте — стоп-точка ПМ, а не pi:dev
(пробел политики — J64, решение Заказчика).

## Манифест

```yaml
pipeline:
  package: flow4-chore-scope
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**]
      inputs: [backlog/J64-ТЗ-по-итогам-аудита-2026-11-02.md]
      task: J64.3 — CHORE_RE принимает chore и kebab-slug; flowctl-подсказка; тесты
      gate: python3 -m pytest tests/test_flow_state.py tests/test_package_runner.py -q
    - id: enforcer
      run: hermes:pm    # plugins/** вне политики зон dev — правка ПМ
    - id: check
      run: gate:python3 -m pytest tests/ -q
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/flow4-chore-scope/review-001.md]
      verdict:
        file: code-reviews/flow4-chore-scope/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm    # PR, зеленый CI, merge
```

## Исполнение в этом прогоне

pi на машине исполнителя нет (Mac Заказчика) — стадии исполняет внешний
агент (Claude Code) по манифесту: зоны и гейты те же, ревью — независимый
сабагент, вердикт — в `code-reviews/flow4-chore-scope/review-001.md`.

## Критерий закрытия

`flowctl prepare --flow 4 --change <slug>` → ALLOW при плане
`PLAN-<slug>.md`; пакет Флоу 4 проходит раннером; полный сьют зеленый.
