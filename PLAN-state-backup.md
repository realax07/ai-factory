# PLAN-state-backup: бэкап и восстановление state движка (J64.6)

**Флоу: 4** — обслуживание фабрики.

## Решение Заказчика (2026-11-10)

«Давай все что можно сделать до 66»; развилка J64.6 — «Бэкап +
восстановление».

## Состав

- `scripts/state_backup.py` — backup / list / restore;
- `factory_paths.backup_dir()` (`AF_BACKUP_DIR`, дефолт `~/ai-factory-backups`);
- крон `state-backup`: обертка (`factory_init.WATCHDOG_SCRIPTS`) и строка
  таблицы рекомендуемых кронов;
- RUNBOOK `docs/runbook-factory-move.md`; README, реестр скриптов, бэклог;
- тесты TC-J64-SB-001…005.

## Вне объема

Реконструкция state из git (`rebuild-state`) — не выбрана Заказчиком.
Вывоз архива вне VPS — процедура в RUNBOOK, исполняет Заказчик.

## Критерий закрытия

Сьют зеленый, ревью approve, CI зеленый.
