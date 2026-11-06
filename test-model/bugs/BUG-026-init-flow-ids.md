# BUG-026: factory_init не копирует flow_ids.py — копии движка в проекте не импортируются

## Суть

J65.3 (PR #223) вынес грамматику scope в `scripts/flow_ids.py`; на него
перешли `flow_state`, `flow_transition` и `flowctl`. `factory_init` копирует
эти три скрипта в проект (`FLOW_CONTROL_FILES`), а `flow_ids.py` в списки
копирования не попал. Проект после `factory_init --force` получает
`ModuleNotFoundError: No module named 'flow_ids'` в копиях движка.

Уже установленные копии в ekotov-wiki/child_bot/auto-school не задеты —
они старые и `flow_ids` не импортируют. Дефект проявился бы при следующей
синхронизации ворот.

Найден 2026-11-06 при сверке документации со списками `factory_init`
(внешний агент Claude Code). Класс дефекта — тот же, что в J64.5
(`factory_paths`): копируемый скрипт импортирует фабричный модуль, которого
нет в списке копирования.

## Фикс

`scripts/flow_ids.py` добавлен в `FLOW_CONTROL_FILES`.

## Тесты

`tests/test_bug026_init_imports.py`: TC-BUG-026-001 (AST-проверка класса:
каждый фабричный импорт копируемого скрипта, включая try/except, сам
копируется), TC-BUG-026-002 (копии из списков factory_init импортируются в
каталоге без остальной фабрики, `python -I`). Оба красные до фикса.

## Статус

- 2026-11-06: исправлено (ветка fix/bug-026-init-flow-ids). OPEN — до merge.
