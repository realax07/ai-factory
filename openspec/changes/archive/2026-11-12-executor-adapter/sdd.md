# SDD: executor-adapter

## Интерфейс исполнителя (`scripts/executors/__init__.py`)

Исполнитель — модуль `scripts/executors/<имя>.py` с объектом `EXECUTOR`
(подкласс `Executor`). Реестр находит его по имени из манифеста
(`run: <имя>:<роль>`) — регистрации в раннере нет.

| Метод | Назначение | Соответствие ТЗ J65.5 |
|---|---|---|
| `manual` | ручная стоп-точка ПМ (hermes): раннер не исполняет, ждет ПМ | — |
| `preflight()` | готовность исполнителя до ворот входа (нет guard'а / команды — `ExecutorUnavailable`); provenance (`zone_guard_sha256`) | start: проверка |
| `prepare_workdir(workdir, role_text)` | ролевая инструкция в рабочий каталог; возвращает файлы на уборку | start |
| `command(launch)` | argv + env процесса для `StageLaunch` (роль, workdir, бриф, зоны, провайдер, модель) | start |
| запуск | раннер: `run_pi(argv, workdir, env, timeout)` — общий spawn с таймаутом | start + wait |
| `list_active()` | активные запуски исполнителя (`ActiveRun`: pid, cwd, команда) — для вотчдога | list_active |
| `transcript(ref)` | транскрипт запуска, если исполнитель его хранит | transcript |

Гарантии — в раннере вокруг вызова (J63): prepare/run → `preflight` →
`prepare_workdir` → spawn → дифф ⊆ зона, гейты, finish → коммит → close.

## Исполнители

- `pi` — роль-пак (`role-agents.md` → `AGENTS.md` / `AGENTS.pi.md`),
  `pi --provider --model --no-session --no-extensions -e <zone-guard> -p
  <бриф>`, env `PI_ZONE_WRITE`/`PI_ZONE_ROLE`/`PI_ZONE_GUARD_LOG`;
  `list_active` — процессы `pi` (cwd — `/proc/<pid>/cwd` или `lsof`).
- `hermes` — `manual`; `list_active` — делегации `async_delegations`
  в state running (через delegate_watchdog).
- `stub` — команда `AF_EXECUTOR_STUB_CMD` с той же командной строкой брифа;
  нет env — `ExecutorUnavailable`.

## Модель и провайдер

`roles.json` — `provider`/`model` у ролей с паками (значения — из
settings.example.json паков на момент пакета); стадия манифеста —
`provider`/`model` поверх. Сверка паков с реестром — тест.

## Журнал запусков и вотчдог

Раннер пишет `<state>/executor_runs.jsonl` (start/end: исполнитель,
delegation_id, пакет, стадия, workdir). Вотчдог (`executor_watchdog.scan`,
зовется delegate_watchdog): для каждого исполнителя с `list_active` —
процесс, cwd которого не совпадает с worktree живой резервации реестра
(reserved/running/finished), — BYPASS `proc:<исполнитель>:<pid>`.
