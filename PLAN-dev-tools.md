# PLAN-dev-tools: прогон как в CI и сверка путей (J65.12)

**Флоу: 4** — обслуживание фабрики: два инструмента отладки; ворота,
спеки и контракты не меняются.

## Цель

Убрать два ручных шага, которые в J64 регулярно стоили итераций:

1. «Локально зеленое, в CI красное» (J64.18: тест digest проходил с полной
   историей и падал в shallow-клоне CI; BUG-025: тесты зависели от
   реального HOME) — `scripts/ci_local.py`.
2. Сверка путей из шелла, крона и Hermes перед мержем правок путей (J64.5:
   «выполните на VPS из трех контекстов и сравните») —
   `factory_paths.py --doctor/--compare`.

## Состав изменений

- `scripts/ci_local.py`: shallow-fetch коммита HEAD (глубина 1, работает и
  из worktree, и при detached HEAD), env с нуля (PATH/LANG/LC_ALL/TMPDIR/
  PYTHONUSERBASE + пустой HOME), `pytest tests/` и `flow_check`; exit 0/1/2.
- `scripts/factory_paths.py`: `--doctor LABEL [--out]` — JSON-снимок
  (label, user, python, env, пути, проверки); `--compare SNAP…` —
  расхождения путей (exit 1). Функции путей не меняются.
- README: разделы «Сверка путей между контекстами» и «Прогон как в CI».
- Тесты `tests/test_j65_dev_tools.py` (TC-J65-DT-001..006).

## Вне объема

- `openspec validate` в `ci_local` (нужен Node + CLI, job `flow`).
- Автоматический сбор снимка из крона/Hermes — команда разовая, запускает
  Заказчик или бот.

## Манифест

```yaml
pipeline:
  package: dev-tools
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**]
      inputs: [backlog/J65-ТЗ-единый-источник-правды-2026-11-03.md]
      task: J65.12 ci_local.py + factory_paths --doctor/--compare
      gate: python3 -m pytest tests/ -q
    - id: docs
      run: hermes:pm    # README — вне зоны dev
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/dev-tools/review-001.md]
      verdict:
        file: code-reviews/dev-tools/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый, `ci_local` на самой фабрике — PASS, мутации ловятся,
ревью «Одобрить», CI зеленый; прогон на VPS — за Заказчиком.

## Исполнение

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code);
ревью — независимый сабагент.
