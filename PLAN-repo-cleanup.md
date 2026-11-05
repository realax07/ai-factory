# PLAN-repo-cleanup: чистка неактуального (J64.16 + хвост J64.1)

**Флоу: 4** — обслуживание фабрики: удаление неиспользуемых файлов и
архивация закрытых планов. Код ворот, спеки и контракты не меняются.

## Решения Заказчика (2026-11-05, дословно по выбору в диалоге)

- Скиллы, которые конвейер не использует: «Удалить из репо».
- `codegraph.json`: «Удалить из git».
- Влитые ветки на GitHub: «Удалить влитые».

## Состав изменений

1. **Скиллы (J64.16).** Удаляются группы `skills/creative/`, `skills/office/`,
   `skills/research/` и скиллы без ссылок из `agents/`, паков, скриптов,
   доков и тестов: `engineering/{requesting-code-review, simplify-code,
   sp-verification-before-completion, sp-writing-plans,
   test-driven-development}`, `runtimes/{hermes-agent-skill-authoring,
   inspecting-hermes-desktop-dom}`. `skills/README.md` и строка `skills/` в
   `README.md` приводятся к новому составу. Копии в `~/.hermes/skills/` не
   затрагиваются.
2. **`codegraph.json` (хвост J64.1).** Удаляется из git: в фабрике это граф
   `backend/app` (4 узла, 0 ребер), файл уже в `.gitignore`. Инструмент
   `scripts/codegraph.py` для проектов остается.
3. **Закрытые планы → `archive/plans/`.** `PLAN-{runner-flow-gates,
   flow4-chore-scope, tests-hermetic, zone-policy-pipeline-paths,
   factory-paths}.md` — пакеты влиты (PR #214, #216, #217, #218, #219).
   `PLAN-BUG-025.md` остается: репорт OPEN до прогона на VPS.
4. **Резолюции J64** (append-only): J64.16 и `codegraph.json` из J64.1.
5. **После merge:** удаление влитых в `origin/main` веток на GitHub.

## Вне объема (сознательно оставлено)

- Процессные скиллы без ссылок: `flow/{dev,qa,sa}-artifact-cleanup`,
  `pm-factory/{ai-factory-flow-control, factory-conveyor-audit}` — скиллы
  самой фабрики, их судьба — отдельное решение.
- Вендорские скиллы `roles-tools/{claude-design, design-md, github,
  systematic-debugging}` упоминают удаленные скиллы как related
  (`popular-web-designs`, `test-driven-development`, …). По правилу README
  вендорские скиллы не правятся в фабрике; в Hermes эти скиллы остаются в
  локальной библиотеке.
- `.hermes/skills/openspec-*` (сгенерированы `openspec init`) — не мусор
  без проверки, как их использует Hermes.

## Манифест

```yaml
pipeline:
  package: repo-cleanup
  flow: 4
  stages:
    - id: impl
      run: hermes:pm    # удаление/перенос вне зон ролей (skills/, корень)
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/repo-cleanup/review-001.md]
      verdict:
        file: code-reviews/repo-cleanup/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый, `flow_check` OK, ревью «Одобрить», CI зеленый, PR
влит; влитые ветки на GitHub удалены.

## Исполнение

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code);
ревью — независимый сабагент.
