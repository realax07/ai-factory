# PLAN-zones-own-role: J65.2 + промпты паков по реестру зон

**Флоу: 4** — обслуживание фабрики: сверка зоны на finish и тексты промптов
паков; правила конвейера не меняются.

## Решение Заказчика (2026-11-09)

На список «что дальше» — «Давай 1 и 3»: (1) промпты роль-паков
`role-agents.md` привести к реестру зон, (3) J65.2 — `ZONE_POLICY_MISMATCH`
по зоне своей роли.

## Состав

1. **Промпты паков** (остаток J64.11): строка `zone (write):` и раздел «Зоны»
   в code-reviewer, architect, devops (шапка добавлена), design-validator,
   qa-case-author, sa, qa-automation — по `agents/roles.json`; тест
   «зона промпта ⊆ политики» (префиксы guard, `normalize_zone`).
   Дефект политики: sa без `impact.md` (J58) — зона дополнена.
2. **J65.2:** `role_zone_policy.role_zone_digest(role)`; поле
   `role_zone_digest` в резервации (flowctl prepare, package_runner);
   `finish` — `ZONE_POLICY_MISMATCH` при расхождении отпечатка своей роли,
   легаси без отпечатка — по покрытию политикой; `policy_version` — аудит.
3. Документы: README («Как связаны части»), докстринги, бэклог J64/J65,
   PLAN.md «Текущее состояние».

## Внимание при выкатке

Этот PR сам правит `agents/roles.json` (зона sa). Сессии, зарезервированные
до мержа, — легаси (без отпечатка): finish сверяет их зону по покрытию
текущей политикой, `policy_version` больше не сравнивается — активные
сессии не падают.

## Манифест

```yaml
pipeline:
  package: zones-own-role
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/unit/**]
      task: J65.2 отпечаток зоны роли в резервации и сверка на finish
      gate: python3 -m pytest tests/ -q
    - id: docs
      run: hermes:pm    # roles.json, промпты паков, README, бэклог — вне зоны dev
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      verdict:
        file: code-reviews/zones-own-role/review-001.md
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый, `gen_role_docs --check` OK, flow_check OK, ревью
approve, CI зеленый; резолюции J65.2 и J64.11 в бэклоге.

## Исполнение

Внешний агент (Claude Code); ревью — независимый сабагент.
