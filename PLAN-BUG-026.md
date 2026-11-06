# PLAN-BUG-026: factory_init не копирует flow_ids.py (дефект J65.3)

**Флоу: 2** — багфикс: дефект влитого J65.3 (PR #223). Репорт —
`test-model/bugs/BUG-026-init-flow-ids.md`. Правка — одна строка в списке
копирования `factory_init` + тест класса дефекта.

## Этапы

| Этап | Роль | Что | Артефакт |
|---|---|---|---|
| 1 | ПМ | репорт, воспроизведение (AST + standalone-импорт копий) | BUG-026 |
| 2 | dev | `flow_ids.py` в `FLOW_CONTROL_FILES` | `scripts/factory_init.py` |
| 3 | dev | TC-BUG-026-001..002 | `tests/test_bug026_init_imports.py` |
| 4 | ПМ | `ci_local` (полный сьют), flow_check | числа в PR |
| 5 | code_reviewer | ревью диффа | `code-reviews/bug-026/review-001.md` |
| 6 | ПМ | PR, merge после CI | PR |

## Критерий закрытия

Тесты красные до фикса и зеленые после; `ci_local` PASS; ревью «Одобрить»;
CI зеленый.

## Исполнение

pi на машине исполнителя нет — стадии исполняет внешний агент (Claude Code);
ревью — независимый сабагент.
