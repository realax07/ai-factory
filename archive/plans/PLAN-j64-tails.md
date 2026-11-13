# PLAN-j64-tails: хвосты J64 — зона debug, CI по SHA, аварийный merge

**Флоу: 4** — обслуживание фабрики.

## Решения Заказчика (2026-11-10)

«Давай все что можно сделать до 66»; развилки: J64.11 — «Зона только
pitfalls»; J64.9 — «Опиши, отрепетирую сам».

## Состав

- J64.11: debug — зона `docs/project-pitfalls.md` в `agents/roles.json`, пак debug.
- J64.17: actions по SHA, pytest с версией в `flow.yml`.
- J64.9: `docs/runbook-emergency-merge.md`, `scripts/ruleset_check.py`.
- Тесты TC-J64-T-001…003; README, реестр скриптов, бэклог.

## Внимание при выкатке

`flow.yml` копируется в проекты (`factory_init --force`) — закрепленные SHA
придут туда при синхронизации.

## Критерий закрытия

Сьют зеленый, ревью approve, CI зеленый; J64.9 закрывается после репетиции
Заказчиком.
