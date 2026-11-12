# Code review 002: executor-adapter (J65.5 + J64.7)

Commit: 902ac35af40835d678a854381196f8d8a970cbb4 (исправления по review-001; база ревью — `git diff origin/main...HEAD`, точечно `git diff 80f44a2..902ac35`)
Ветка: chore/executor-adapter (worktree /Users/ekotov/AI/ai-factory-x)
Ревьюер: code_reviewer (независимая сессия, автор диффа — не я)
Прогоны:
- `pytest tests/unit/test_j65_executor_adapter.py tests/unit/test_package_runner.py tests/unit/test_j64_dev_per_task.py tests/unit/test_j64_zone_guard.py tests/unit/test_j65_reference_run.py tests/unit/test_j65_review_verdict.py tests/unit/test_j65_pi_review_j10.py tests/unit/test_bug026_init_imports.py -q -p no:cacheprovider` (AF_STATE_DIR/HERMES_HOME — временные каталоги): **171 passed**;
- `python scripts/flow_check.py .`: **FAIL** — `FLOW-ERROR: tests/unit/test_j65_executor_adapter.py: time.sleep запрещен (спека qa-pipeline)`, 1 ошибка (см. B1);
- `python scripts/gen_role_docs.py --check`: таблицы актуальны;
- `openspec validate --all --strict`: не проверено — CLI на машине ревьюера нет (за CI/ПМ);
- смок `executors.runs_binary(cmd, "pi")` на 20 командных строках (ниже).

Итог: M1 закрыт по существу — Pi под node (`node …/bin/pi`, `env node …/pi`) и stub под python теперь видны, тест на настоящем процессе проходит; minor m1–m7 закрыты. Но новый тест красит ворота flow_check (time.sleep в тестах запрещен) → артефакт не принимается (AGENTS.md, правило 3) → return.

## Закрытие замечаний review-001

| # | Статус | Проверка |
|---|---|---|
| M1 | закрыт | `runs_binary`: `node /opt/homebrew/bin/pi -p x` → True, `/usr/bin/env node /opt/homebrew/bin/pi` → True, полный путь Python.app + `./psbin/pi` → True; test_real_interpreted_process_is_visible — настоящий shebang-процесс виден через ps + cwd, BYPASS при released-резервации, тишина при running |
| m1 | закрыт (с оговоркой m-new-2) | managed_roots: repo/worktree записей любого статуса + `<repo>-worktrees/`; чужой каталог — не инцидент (тест, pid 14) |
| m2 | частично (m-new-3) | default_paths читает PIPELINE_FLOW_REGISTRY/STATE; тест сверяет с pr.flow_paths при обеих env |
| m3 | закрыт | executor_bypasses: исключение скана → WARN + []; тест boom |
| m4 | закрыт | отчет/журнал/state — run_label/executor; excludes stash — `AGENTS.<имя>.md` по executors.names() |
| m5 | закрыт | auditor `k3.1-pro`; README паков перегенерирован, `--check` зеленый |
| m6 | закрыт | StageLaunch.zone_globs = зоны манифеста как есть |
| m7 | закрыт | `ps -eo pid=,args=` |
| m8 | открыт по плану | 6.1 закрывается после approve |

## Ложные срабатывания runs_binary (смок)

- Не срабатывает (верно): `bash -c "vim pi"`, `node --inspect pi.js`, `vim pi`, `python3 notpi.py`.
- Ложные «да»: `python3 -m pi` (модуль с именем pi), `python3 -c pi`, `node -e pi` — флаг с аргументом-значением пропускается, значение принимается за бинарь.
- Ложные «нет»: флаги с отдельным значением перед скриптом — `node --require ./r.js …/pi`, `node --max-old-space-size 4096 /bin/pi`, `python3.12 -X dev /x/pi`, `env -u FOO pi`; `sh -c "pi -p x"` (строка в кавычках, ps не сохраняет границы аргументов).
- Реальные запуски Pi (`node <bin>/pi …`, shebang через env) и stub распознаются. Ложные «да» требуют каталога проекта конвейера без живой резервации — шум возможен, но редкий → minor (m-new-1).

## Замечания

| # | Уровень | Место | Сценарий / суть | Рекомендация |
|---|---|---|---|---|
| B1 | **blocker** | tests/unit/test_j65_executor_adapter.py:285 (`time.sleep(0.1)` в цикле ожидания), :271 (строка скрипта `time.sleep(60)`) | `flow_check.py` (scripts/flow_check.py:820) запрещает `time.sleep` в тестах — ворота красные, CI (flow.yml) PR не пропустит. | Ожидание без sleep: в цикле опрашивать до появления процесса с ограничением по попыткам/`time.monotonic()` дедлайну без паузы, либо `proc.wait(timeout=…)`-подобный примитив (`threading.Event().wait(0.1)`, `select`); ребенку — блокирующее ожидание без sleep (`sys.stdin.read()` с `stdin=PIPE`, `signal.pause()`), завершение — kill в finally. Прогнать flow_check. |
| m-new-1 | minor | scripts/executors/__init__.py:177-191 (`runs_binary`) | Флаги интерпретатора с аргументом-значением: `-m pi`/`-c pi`/`-e pi` дают ложный BYPASS, `--require x`/`-X dev`/`env -u FOO` — пропуск настоящего запуска. | Для `-m/-c/-e/--eval/-p` (python/node) — False; для известных флагов со значением (`-X`, `-W`, `--require`, `-r`, `--max-old-space-size`, `env -u/-C/-S`) — пропускать и значение. Тест-таблица с этими случаями. |
| m-new-2 | minor | scripts/executor_watchdog.py:58-71 (`managed_roots`) | Раннер резервирует с `repo = worktree` (package_runner `_zone_begin`, flowctl prepare `--repo <worktree>`), поэтому для записей раннера `<repo>-worktrees` вычисляется от worktree (`…/pkg-worktrees`, бесполезно), а основной клон и новые worktree под `<repo>-worktrees/` покрыты, только если в реестре есть запись с repo = основной клон (делегации Hermes). На машине «только раннер» ручной pi в основном клоне/в свежем worktree не виден. | Корень репо брать через `git rev-parse --git-common-dir` (как `session_check.git_main_root`) от repo/worktree записи; от него — сам клон и `<root>-worktrees/`. |
| m-new-3 | minor | scripts/executor_watchdog.py:75-80 (`default_paths`) | При заданном только PIPELINE_FLOW_REGISTRY раннер кладет журнал в `registry.parent` (fc.default_state_path), вотчдог — в `fp.flowctl_state_path()` (AF_STATE_DIR): журнал расходится, пометка `runner_start` теряется. | Без PIPELINE_FLOW_STATE: `registry.parent / "flowctl_state.json"`, как flowctl.default_state_path. Тест на случай одной env. |
| m-new-4 | minor | scripts/package_runner.py:1636 (`executors.names()` в shelve_attempt) | `names()` импортирует все модули исполнителей: сломанный посторонний модуль роняет откладывание optional-попытки исключением мимо RunnerStop. | Брать имена из `cleanup` текущей попытки (или ловить исключение в names()). |

Не проверено: `openspec validate --all --strict` (нет CLI), реальный Pi CLI (нет на машине), Linux-ветка /proc, полный сьют (за ПМ).

## Вердикт: return
