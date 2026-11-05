# PLAN-tests-hermetic: тесты фабрики не пишут в HOME и в дерево (J64.1 + J64.2)

**Флоу: 4** — обслуживание фабрики: тестовая инфраструктура и удаление
тестового мусора из `main`; код ворот, спеки и контракты не меняются.

## Цель

1. **J64.2** — прогон сьюта не пишет в реальный HOME. Замер 2026-11-03
   (`HOME=<пустой каталог> pytest tests/`): появлялись
   `~/.hermes/state/flow-enforcer.log`, `~/.hermes/scripts/{delegate_watchdog,
   session_watchdog,stand_reaper}.py`; на VPS это боевой `~/.hermes` фабрики.
2. **J64.1** — сьют не оставляет файлов в репозитории; тестовый мусор
   `prepared: true/` (коммит 6d4d365, симлинки на /home/openclaw/...)
   удаляется из `main`. Историю не переписываем (правило 7).

## Состав изменений

- `tests/conftest.py`: autouse-фикстура `isolated_home` (HOME, HERMES_HOME
  — временный каталог теста); сторож дерева — `git status --porcelain`
  после сьюта сравнивается с исходным, новые пути → сьют красный с
  перечнем (ловит утечку в CI и на VPS, где она возникла).
- Удаление `prepared: true/` из репозитория.

Причина появления `prepared: true/` на VPS локально не воспроизводится
(на Mac дерево после сьюта чистое); сторож дерева сделает ее видимой при
следующем возникновении. `codegraph.json` (в .gitignore, но отслеживается)
— не трогаем до решения (J64.1: нужен ли артефакт в репо).

## Манифест

```yaml
pipeline:
  package: tests-hermetic
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [tests/**]
      inputs: [backlog/J64-ТЗ-по-итогам-аудита-2026-11-02.md]
      task: J64.2 изоляция HOME в conftest; J64.1 сторож дерева после сьюта
      gate: python3 -m pytest tests/ -q
    - id: cleanup
      run: hermes:pm    # удаление prepared: true/ — путь вне зон всех ролей
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/tests-hermetic/review-001.md]
      verdict:
        file: code-reviews/tests-hermetic/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

## Исполнение в этом прогоне

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code)
по манифесту; ревью — независимый сабагент.

## Проверки и критерий закрытия

- `HOME=<пустой каталог> pytest tests/` — каталог остается пустым
  (проверено: 0 файлов, 1104 passed).
- Пробный тест, пишущий файл в корень репо, валит сьют (rc=1,
  `FACTORY-TREE-LEAK`) — проверено вручную, пробный тест удален.
- CI зеленый; `prepared: true/` нет в `main`.
