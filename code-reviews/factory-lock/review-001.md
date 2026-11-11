Commit: e8ebd619c5f72514cd56b30074a5900805afc90e

Ревью J65.7 (часть фабрики): ветка chore/factory-lock, диф `origin/main...e8ebd61`.
Входы: PLAN-factory-lock.md, backlog/J65-* раздел J65.7. Ревьюер — независимый
сабагент (Claude Code), код не правил.

Итог: механика верная и рабочая. Синтаксис Actions корректен. Значения lock не
попадают в shell-интерполяцию `${{ }}`. Ворота фабрики против клонов трех
проектов проходят. Вернуть из-за трех major: тест init зависит от среды и падает
на машине с openspec и неопубликованным HEAD; у lock два разных парсера, и CI не
проверяет repo; «опубликованный HEAD» засчитывает любую remote-ветку, а не main.

## Что проверено фактами

- Сьют: `tests/unit/test_j65_factory_lock.py` + `test_installers.py`: 16 тестов.
  С фейковым `openspec` в PATH результат 1 failed / 15 passed:
  `test_installers.py::test_factory_init_without_hermes`. Тот же тест на
  `origin/main` с тем же PATH: 1 passed (worktree `origin/main`).
- Клоны ekotov-wiki, child_bot, auto-school: в `.factory/` лежит фабрика на
  e8ebd61, `HOME=/nonexistent`, `AI_FACTORY_HOME=.factory`.
  `.factory/scripts/flow_check.py .` во всех трех дает exit 0. Новое по
  сравнению с копиями проекта: FLOW-WARNING «промпты устарели» во всех трех,
  в auto-school еще раскладка J66 для `tests/test_container_contract.py`.
  Копии проекта `scripts/flow_check.py` при наличии `.factory/` дают тот же
  вывод (`.factory` не сканируется). `pr_validate` (`[chore]`/`[docs]`):
  копия проекта и фабрика дают одинаковое OK.
- `pr_changed_files` берет `git diff` только по отслеживаемым файлам,
  неотслеживаемый `.factory/` в дифф не попадает. `impact_rules.json` читается
  из `scripts/` проекта (pr_validate.py:676-687), не из фабрики.
  `AI_FACTORY_HOME` влияет только на сверку промптов flow_check
  (flow_check.py:512-530, WARNING, не ошибка).
- Шаг Factory lock прогнан bash'ем на разных входах (таблица в п.2 ниже).
- `realax07/ai-factory` публичный: checkout с `GITHUB_TOKEN` проекта и из PR
  форка работает (read-only токен достаточен).
- Не проверено: `openspec validate --all --strict` при наличии `.factory/`
  (CLI на машине нет). Риск низкий: CLI берет `./openspec`.

## Замечания

| # | Серьезность | Где | Что не так | Рекомендация |
|---|---|---|---|---|
| 1 | major | scripts/factory_init.py:688-692 (`lock_ok = install_factory_lock(...)`, `ok = lock_ok`); tests/unit/test_installers.py:196 | Init теперь пишет lock из реального git-состояния фабрики. Неопубликованный HEAD (любой worktree с локальным коммитом, как этот e8ebd61) дает `ok=False` и rc 1. `test_factory_init_without_hermes` допускает rc 1 только при «openspec CLI: НЕ найден». Сьют зеленый лишь потому, что openspec нет в PATH venv и CI-job test-flow-control. На машине ПМ с openspec сьют красный до push: воспроизведено, 1 failed. Остальные e2e-тесты init (test_j54_tiers, test_j53_glossary, test_gate_harness) тоже пишут lock из реального `git branch -r` фабрики, то есть зависят от среды. | Изолировать тесты init от состояния git фабрики, например env-переключателем или monkeypatch `published_head` в conftest. Либо не считать «lock не записан» поводом для rc 1 (WARNING без `ok=False`), если это решение. Добавить тест: init при неопубликованном HEAD и при наличии openspec. |
| 2 | major | .github/workflows/flow.yml:60-66 против scripts/factory_lock.py:44-61 | Два парсера lock с разной грамматикой, тест согласованности проверяет только «счастливый путь» (test_j65_factory_lock.py:90). Факты прогона шага bash'ем: `repo=evil;rm` → shell rc 0, `repo=evil;rm` уходит в GITHUB_OUTPUT, python дает LockError. Два `repo=` → shell склеивает `a/bc/d`, python берет последний `c/d`. Строки с отступом или `repo = a/b` → python OK, shell rc 1. Repo в CI проверяется только на непустоту, хотя REPO_RE в python есть. Shell-инъекции нет: значение идет только во `with: repository`, пробелы и переводы строк режет `tr`. Но ворота читают lock не так, как его пишет и проверяет инструмент. Это расходится с принципом одного парсера (J65.4). | В шаге CI: `grep -c '^repo='`/`'^sha='` = 1 и `REPO` по `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`. Лучше вызывать один парсер: `python3 -c` с той же грамматикой до setup-python (python3 на ubuntu-latest есть) либо сузить python до строгой формы `^key=value$`. Тест TC-003: параметризовать спорными входами и сверить решение shell и python. |
| 3 | major | scripts/factory_lock.py:83-89 (`published_head`) | «Опубликован» = `git branch -r --contains HEAD` по любым remote-tracking ссылкам, причем локальным. Проходят: (а) push ветки `pipeline/**` или `chore/**` сабагента или ПМ до ревью и merge (правило 4: сабагенты пушат свои ветки); (б) remote-ветка, удаленная на GitHub, без `fetch --prune`; (в) любой remote, не только origin (форк, upstream), вопреки docstring. Итог: `factory_init` или `update` из worktree фабрики закрепляет в проекте непроверенный код ворот, а PR проекта показывает только SHA. Устаревшие ссылки дают и ложный отказ (HEAD запушен из другого клона, fetch не было). Это безопасно, но непрозрачно. | Проверять достижимость из ревьюеной ветки: `git merge-base --is-ancestor HEAD origin/main` (опционально после `git fetch origin main`). Если HEAD не на main — отказ с подсказкой `--sha`. Сообщение: «HEAD не в origin/main». Тест на ветку, которая есть в remote, но не в main. |
| 4 | minor | .github/workflows/flow.yml:75-81 | Второй checkout оставляет `persist-credentials` по умолчанию (true): `GITHUB_TOKEN` проекта пишется в `.factory/.git/config`, хотя код фабрики токен не использует. | `persist-credentials: false` для checkout фабрики. |
| 5 | minor | .github/workflows/flow.yml:60-81 | `factory.lock` берется из head PR: PR может перенаправить ворота на любой публичный репозиторий (`repo=` форка с «всегда OK»). Привилегий это не добавляет: раньше PR так же мог править `scripts/` или `flow.yml`. Но после снятия копий lock станет единственной точкой доверия ворот, а одна строка `repo=` в PR заметна плохо. | Allow-list в шаге (`REPO` = `realax07/ai-factory`, иное — `::error::`), а также CODEOWNERS или impact-правило на `factory.lock` в проектах. |
| 6 | minor | scripts/flow_check.py:526-528 (следствие `AI_FACTORY_HOME` в CI) | В CI всех трех проектов появится постоянный FLOW-WARNING «промпты устарели относительно ~/ai-factory … factory_init.py --force». Формулировка вводит в заблуждение в CI (сверка идет с закрепленной версией, не с `~/ai-factory`), а `--force` для проектов разрушителен (п.7). | Уточнить текст: «относительно фабрики <AI_FACTORY_HOME>». Это ожидаемый эффект, его стоит отразить в плане перевода. |
| 7 | minor | PLAN-factory-lock.md:23-24; backlog J65.7 резолюция | План перевода предлагает `factory_init --force` в каждом проекте. `flow.yml` всех трех проектов кастомизирован относительно фабрики: в ekotov-wiki переименованы job'ы (`name: test-flow-control`, job `flow`), это ломает имена required checks; в child_bot добавлен `-r requirements.txt`; в auto-school сборка Vue и `branches: [main]`. `--force` затрет это, а заодно CONSTITUTION/glossary/agents. | В плане перевода: вливать шаги Factory lock / checkout / `$FACTORY_SCRIPTS` в `flow.yml` проекта точечно, а lock писать через `factory_lock.py update`, без `--force`. |
| 8 | minor | .github/workflows/flow.yml (test-flow-control); scripts/pr_validate.py:676 | Совместимость: после перевода CI-ворота идут из `.factory/`, а job test-flow-control проекта гоняет pytest проекта против копий `scripts/` (например, `tests/test_flowctl.py` в wiki). До снятия копий тесты проверяют не тот код, что работает в воротах. `impact_rules.json` — проектный конфиг в `scripts/`. | В плане снятия копий: оставить `scripts/impact_rules.json` (или перенести путь), перевести тесты ядра в проектах на `.factory`/удалить. |
| 9 | minor | tests/unit/test_j65_factory_lock.py:77-99 | TC-003 не проверяет `AI_FACTORY_HOME` в GITHUB_ENV. TC-004 не проверяет условие `if: steps.lock.outputs.sha != ''` у checkout. Нет кейса с битым repo, см. п.2. | Добавить ассерты. |
| 10 | minor | scripts/factory_lock.py:109 | `update` не чинит битый lock: `read_lock` бросает LockError, rc 1. Подсказки «удали файл» в CLI нет (в init есть). | Сообщение с подсказкой или `update --sha … --repo …` перезаписывает битый файл. |
| 11 | minor | backlog J65.7 п.2 «локально — через AI_FACTORY_HOME» | Локальный запуск ворот проекта по lock (не по копиям) не описан и не реализован. | Отметить в резолюции как открытое или одной строкой в README. |

## Вердикт: return
