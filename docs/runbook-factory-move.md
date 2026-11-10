# RUNBOOK: бэкап state и перенос фабрики на новую машину (J64.6)

State движка — `AF_STATE_DIR` (по умолчанию `~/.hermes/state/`): реестр сессий
`active_sessions.json`, циклы `flowctl_state.json`, режим `flow_mode.json`,
инциденты и ack вотчдогов, gate-отчеты. Он вне git; без него в enforcing
работа встает (нет режима, резерваций, истории циклов). Код фабрики, планы,
ревью и бэклог — в git, их бэкап — GitHub.

## Ежедневный бэкап

Крон Hermes `state-backup` (`15 3 * * *`, deliver=local; обертку ставит
`factory_bootstrap.py` / `factory_init.py`):

```bash
python3 ~/ai-factory/scripts/state_backup.py backup          # молча; архив в AF_BACKUP_DIR
python3 ~/ai-factory/scripts/state_backup.py list            # что есть
```

Архив — `state-<UTC>.tar.gz` в `AF_BACKUP_DIR` (по умолчанию
`~/ai-factory-backups/`, вне state), хранятся 14 последних. Транскрипты
`session-archive/` — только с `--include-archive` (объемные, для разборов).

**Потеря машины целиком** бэкап на той же VPS не переживает: последний архив
периодически копировать вне VPS (rsync/scp на другую машину или в облачное
хранилище Заказчика). Секретов в архиве нет: ключи — в `~/.hermes/.env` и
`~/.pi/agent/models.json`, они переносятся отдельно и вручную.

## Восстановление state на той же машине

```bash
python3 ~/ai-factory/scripts/state_backup.py restore ~/ai-factory-backups/state-<UTC>.tar.gz
```

- текущий state не удаляется: переименовывается в
  `<state>.before-restore-<UTC>` рядом;
- если в текущем реестре есть активные сессии (reserved/running) — отказ:
  восстановление перепишет их резервации. Сначала закрыть/разобрать
  сессии (`session_check reconcile`), осознанно — `--force`;
- архив проверяется: только файлы и каталоги внутри `state/`, без ссылок
  и путей наружу.

После восстановления: `python3 scripts/flow_mode.py show` (режим тот же, что
был), `python3 scripts/factory_paths.py --doctor shell` (пути).

## Перенос фабрики на новую машину

1. На старой машине (если она жива): `state_backup.py backup --verbose`,
   скопировать архив и ключи (`~/.hermes/.env`, `~/.pi/agent/models.json`)
   на новую.
2. На новой: клон и установка —
   ```bash
   git clone https://github.com/realax07/ai-factory ~/ai-factory && cd ~/ai-factory
   python3 scripts/factory_bootstrap.py --skip-tests
   ```
3. Восстановить state из архива:
   `python3 scripts/state_backup.py restore <архив> --force` (bootstrap уже
   создал пустой state с режимом shadow — его откладывает restore).
4. Положить ключи на место (chmod 600), проверить:
   ```bash
   python3 scripts/factory_bootstrap.py          # с приемочным сьютом
   python3 scripts/flow_mode.py show              # режим как на старой машине
   python3 scripts/factory_paths.py --doctor new
   ```
5. Проекты: склонировать в `AF_PROJECTS_ROOT`; активные сессии из
   восстановленного реестра, чьих worktree на новой машине нет, —
   `session_check reconcile` (ничего не удаляет молча).
6. Hermes: переустановить плагин flow-enforcer (`factory_init.py --target
   <проект>`), включить кроны по таблице `docs/README-flow-control.md`.
