# Code review 003: executor-adapter (J65.5 + J64.7)

Commit: d930ed93b975ad834e72d6f4a93d38c21dca3f3a (исправления по review-002; база — `git diff origin/main...HEAD`, точечно `git diff 902ac35..d930ed9`)
Ветка: chore/executor-adapter (worktree /Users/ekotov/AI/ai-factory-x)
Ревьюер: code_reviewer (независимая сессия, автор диффа — не я)
Прогоны:
- `pytest tests/unit/test_j65_executor_adapter.py tests/unit/test_package_runner.py tests/unit/test_j64_dev_per_task.py tests/unit/test_j64_zone_guard.py tests/unit/test_j65_reference_run.py tests/unit/test_j65_review_verdict.py tests/unit/test_j65_pi_review_j10.py tests/unit/test_bug026_init_imports.py -q -p no:cacheprovider` (AF_STATE_DIR/HERMES_HOME — временные каталоги): **172 passed**;
- `python3 scripts/flow_check.py .`: **OK**;
- `gen_role_docs.py --check`: таблицы актуальны;
- `openspec validate --all --strict`: не проверено — CLI на машине ревьюера нет (за CI/ПМ);
- смок `executors.runs_binary(cmd, "pi")` на 16 командных строках (ниже).

Итог: blocker B1 и minor m-new-1…m-new-4 закрыты; blocker/major нет. Остались два minor-пропуска в `runs_binary` (флаги, у которых разная семантика в разных интерпретаторах) — не блокируют: реальный Pi (`node …/bin/pi`) и stub без флагов распознаются.

## Закрытие замечаний review-002

| # | Статус | Проверка |
|---|---|---|
| B1 | закрыт | sleep в тесте нет; ребенок ждет на `sys.stdin.read()`, опрос ps до дедлайна; flow_check OK |
| m-new-1 | закрыт | `python3 -m pi`, `python3 -c pi`, `node -e pi` → False; `node --require ./r.js /opt/pi`, `python3.12 -X dev /x/pi`, `env -u FOO pi`, `sh -c "pi -p x"` → True; `bash -c "vim pi"`, `node --inspect pi.js` → False |
| m-new-2 | закрыт | `main_clone` по `git --git-common-dir`, в roots — клон и `<клон>-worktrees`; тест на repo=worktree и процесс в основном клоне |
| m-new-3 | закрыт | без PIPELINE_FLOW_STATE state = `registry.parent/flowctl_state.json` (как flowctl.default_state_path); тест на оба варианта env |
| m-new-4 | закрыт | `names()` пропускает сломанный модуль с WARN — shelve_attempt/scan/сообщение манифеста не падают |
| m8 (review-001) | открыт по плану | 6.1 — после approve |

## Замечания

| # | Уровень | Место | Сценарий / суть | Рекомендация |
|---|---|---|---|---|
| m-3-1 | minor | scripts/executors/__init__.py:189-193 (VALUE_FLAGS / CODE_FLAGS — общие для всех интерпретаторов) | Флаги с разной семантикой: `-u` (у python — unbuffered без значения) берется как флаг со значением → `python3 -u /x/pi` → False; `-e` (у sh/bash — errexit) берется как «код» → `bash -e /x/pi` → False. Это пропуски настоящего запуска; `python -u` для stub/обертки на python — реалистичная форма. Также `-r`/`-p` у bash. | Наборы флагов — по интерпретатору (env: `-u/-C/-S`; python: `-X/-W` значение, `-m/-c` код; node: `-r/--require` значение, `-e/-p` код; sh: только `-c`). Добавить `python3 -u …/pi`, `bash -e …/pi` в тест-таблицу. |
| m-3-2 | minor | scripts/executors/__init__.py:213 (рекурсия `sh -c`) | Проверяется только первая команда строки: `bash -c "cd /x && pi …"` → False. Форма типична для оберток. | Делить строку `-c` по `&&`, `;`, `\|\|`, `\|` и проверять каждую команду (или `shlex.split` + разделители). |
| m-3-3 | minor | scripts/executor_watchdog.py:64-71 (`managed_roots` → `main_clone`) | Вызов `git rev-parse` на каждый repo/worktree реестра всех статусов при каждом прогоне крона (*/5): реестр растет (closed-записи не удаляются) — число git-процессов растет линейно. | Кэшировать по уникальным путям (уже set) и пропускать несуществующие каталоги до вызова git (`os.path.isdir`). |

Не проверено: `openspec validate --all --strict` (нет CLI), реальный Pi CLI (нет на машине), Linux-ветка /proc, полный сьют (за ПМ).

## Вердикт: approve
