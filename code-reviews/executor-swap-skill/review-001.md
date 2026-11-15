# Ревью executor-swap-skill — review-001

- Пакет: PLAN-executor-swap-skill.md (Флоу 4), ветка `chore/executor-swap-skill`
- Коммит: d245400 (поверх origin/main 9faa0e0), дифф `git diff origin/main...HEAD`, 12 файлов
- Ревьюер: code_reviewer (независимый сабагент), только статика: ничего не запускалось, кроме `claude --help` и проверки поведения `sqlite3.connect` на несуществующем файле

## Вердикт: return

Почти все утверждения скилла и гайда о раннере и исполнителях подтверждаются кодом.
Одно ключевое утверждение о защите ревью (`pr_validate`) сформулировано шире, чем
работает код, и именно на нем гайд строит гарантию для внешнего оркестратора. Это
нужно уточнить до merge. Правка только текстовая.

## Находки

### M1 (major): «ревью сабагентом оркестратора pr_validate не засчитает» верно только частично

Где: `skills/pm-factory/executor-swap/SKILL.md:128-129`, `:150-152`;
`docs/guides/external-orchestrator.md:27`, `:59-61`.

Что на самом деле в коде:
1. Проверка `Reviewer-Delegation` есть только в `check_change`, то есть только для
   Флоу 1 (`scripts/pr_validate.py:172-206`). В `check_chore`, `check_docs` и
   `check_bug` (`scripts/pr_validate.py:45-64`, `227-267`) ревью-артефакты не
   проверяются. Во Флоу 2–5 `pr_validate` пропустит любое ревью, в том числе
   сабагента оркестратора, и даже PR вообще без ревью. Этот пакет тоже Флоу 4,
   поэтому сам он этой проверкой не покрыт.
2. Проверка открывается при ошибке (fail-open). Если `~/.hermes/state.db` не
   открывается, то `sqlite3.connect(...mode=ro)` бросает `OperationalError`
   (проверено: `unable to open database file`), и ветка `except _sq.Error:`
   ставит `_exists = _ok = True` (`scripts/pr_validate.py:197-198`). Любой файл,
   где есть строка вида `Reviewer-Delegation: deleg_xxx`, засчитается. Это ровно
   сценарий внешнего оркестратора на машине без Hermes, и, скорее всего, так же
   ведет себя CI-клон. Сабагент, который скопировал формат штампа из соседнего
   ревью, пройдет проверку.
3. Формулировка «ревью засчитывается только со стадии раннера» неточна и в
   общем случае. Делегация Hermes (`delegate_task`) со статусом `completed` в
   `async_delegations` тоже засчитывается (`scripts/pr_validate.py:187-188`).

Что исправить: в скилле и гайде написать, что `pr_validate` требует
`Reviewer-Delegation` только во Флоу 1 и не проверяет делегацию, если реестр
Hermes недоступен. Поэтому ревью сабагентом оркестратора запрещено правилом, а
ворота поймают его не всегда. Для Флоу 2–5 и для машины без Hermes надежная
опора — приемка ПМ по provenance (`gate_runner record-review`, раздел
«Оркестрация» AGENTS.md) и ревью стадией раннера. Fail-open и отсутствие
проверки ревью вне Флоу 1 стоит записать открытым пунктом в J65.6 (там уже
открыто «pr_validate обращается к Hermes вне адаптера»). Код в этом пакете не
трогать: это Флоу 4 без изменения ворот.

### m1 (minor): процесс самого пакета противоречит добавляемому гайду

Где: `PLAN-executor-swap-skill.md:41-42` («независимое ревью сабагентом до
approve») против `docs/guides/external-orchestrator.md:59-61` («Не звать свои
сабагенты на роли … ревью pr_validate не засчитает»). Это ревью — сабагент
оркестратора, а не стадия раннера. Нужно либо зафиксировать в плане, что ревью
засчитывается через `gate_runner record-review` (provenance, AGENTS.md
«Оркестрация»), либо оговорить в гайде исключение для Флоу 4 без раннера.
Иначе первый же пакет по новому гайду его нарушает.

### m2 (minor): ссылки на AGENTS.md в уровне 2 скилла неточны

Где: `skills/pm-factory/executor-swap/SKILL.md:86-89`. П.19 касается режимов
ворот, снятия блокировок, flow-enforcer и правки AGENTS.md, а не смены
исполнителя. Подходящие ссылки — п.5 (противоречие решает Заказчик) и п.18
(решение — артефактом). Кроме того, в п.17 есть собственное исключение: общая
делегация Hermes, если Pi недоступен или нужен срочный хотфикс, с обоснованием в
журнале делегаций. Скилл его не упоминает, а вместо него вводит исключение «по
решению Заказчика», которого в п.17 нет. Само ограничение строже правила,
противоречия нет, но ссылки нужно поправить и упомянуть исключение из п.17.

### m3 (minor): у Claude Code / Codex нет явного запрета yolo и рекомендуемого режима

Где: `skills/pm-factory/executor-swap/SKILL.md:102-106`. Флаги верные: по
`claude --help` есть `-p/--print`, `--model`, `--permission-mode`
(`acceptEdits|auto|bypassPermissions|default|dontAsk|plan`), `--disallowedTools`
и `--setting-sources` (`user, project, local`). У Codex `exec -m` и
`--sandbox workspace-write` соответствуют известному CLI. Чего не хватает:
- прямой строки «запрещены `--permission-mode bypassPermissions`,
  `--dangerously-skip-permissions`, `codex --yolo` /
  `--dangerously-bypass-approvals-and-sandbox`» (п.4: yolo запрещен);
- указания, что в `-p` режим `default` молча откажет в правках, поэтому нужен
  `acceptEdits` плюс `--allowedTools` для нужного Bash;
- оговорки, что `--disallowedTools` вариадический (`<tools...>`) и поглотит
  бриф, если бриф стоит после него (порядок argv в примере правильный, но об
  этом стоит сказать);
- упоминания `--strict-mcp-config` (MCP-серверы пользователя не входят в
  `--setting-sources`) и `--bare` как варианта без `CLAUDE.md`, хуков и плагинов
  (тогда роль передается через `--append-system-prompt-file`). Это относится к
  пункту «Чужие настройки исполнителя» (`:153-156`).

Шаблон `Bash(git push*)` не надежен как guard (обходится через `git -C . push`
или `sh -c`). Таблица на `:141` правильно называет основной опорой ruleset
main. Стоит добавить, что deny-список — лишь дополнительная мера.

### m4 (minor): вотчдоги представлены как всегда работающие

Где: `docs/guides/external-orchestrator.md:29` («по крону на VPS» / «работают
так же»), `skills/pm-factory/executor-swap/SKILL.md:147-148` («поднимает
BYPASS»). Согласно `docs/guarantees.md:37`, `:56` крон `delegate-watchdog`
(через него работает `executor_watchdog`) включает ПМ после проверки, и до
этого обход не детектируется. Кроме того, `executor_watchdog.scan` видит только
процессы внутри каталогов проектов из реестра (`scripts/executor_watchdog.py:124-153`).
Нужно добавить оговорку «если включен крон delegate-watchdog».

### m5 (minor): `session_archive.py` объявлен «не применим» вопреки AGENTS.md

Где: `docs/guides/external-orchestrator.md:30`. AGENTS.md («Эскалация и
здоровье сессий») требует заканчивать приемку `python3 scripts/session_archive.py`
без исключений. Гайд снимает требование без решения Заказчика. Лучше написать
«запускать; без делегаций Hermes архив пуст (J65.6)» или эскалировать.

### m6 (minor): тест — расхождения с планом и докстрингом

Где: `tests/unit/test_j65_executor_swap_skill.py:5-8`, `PLAN-executor-swap-skill.md:35`.
- В плане тест называется `tests/unit/test_executor_swap_skill.py`, а
  фактически файл — `test_j65_executor_swap_skill.py`.
- Докстринг обещает красный тест на «битую ссылку на … скилл», но
  `related_skills` (`SKILL.md:11`) не проверяются. Сейчас все три скилла
  существуют (`skills/pm-factory/pi`, `skills/pm-factory/ai-factory-flow-control`,
  `skills/flow/factory-flow`), поэтому это расхождение докстринга, а не ложный
  зеленый.
- Регулярка путей пропускает пути с пробелом внутри бэктиков (например,
  `scripts/session_worktree.sh create …` в гайде, `:40`), поэтому этот файл не
  проверяется. Остальные проверки делают то, что заявлено:
  `test_every_executor_documented` берет `executors.names()` и ищет строку
  таблицы `| \`name\` |`. Ложного зеленого в заявленном объеме нет.

### m7 (minor): сводные статусы с неточной датой и потерянный Qwen

- `PLAN.md:26-30`: закрытие J65.10 от 2026-11-15 вписано в пункт
  «Сделано за 2026-11-02…13».
- `backlog/MAP.md`, строка J65: префикс остался «статус 2026-11-14», хотя
  добавлено событие 2026-11-15.
- `PLAN.md` (раздел «Открыто») и `README.md:15-18`: Qwen Coder (решение
  Заказчика 2026-11-13 «Исполнители могут быть еще и codex и может еще что-то
  добавим») убран без нового решения. Решение 2026-11-15 называет только codex
  и клод. Это сводные разделы, история не переписана, но стоит добавить
  «и другие кодагенты» или ссылку на уровень 3 скилла.

## Что подтверждено по коду

- `--dry-run` ловит неизвестный исполнитель: `parse_manifest` вызывает
  `executors.get(prefix)`, и `KeyError` превращается в `ManifestError` с
  перечнем `names()` и `SHELL_KINDS` (`scripts/package_runner.py:442-451`).
  `cmd_run` парсит манифест до ветки dry-run (`:1665-1681`). Ключи
  `provider`/`model` стадии нормализуются в манифесте и попадают в JSON-вывод.
- `MODEL_UNRESOLVED` срабатывает до ворот входа: `role_model` (`:1057-1070`,
  реестр по `pack`) вызывается на `:1986`, а `gate_new`/`gate_begin` — на
  `:2001-2013`. `preflight()` с `ExecutorUnavailable` тоже идет до ворот
  (`:1980-1985`). Зона не резервируется.
- Provenance `executor: <имя> (<провайдер>/<модель>)` попадает в отчет стадии
  (`:2009-2012`, `write_report` на `:2121`).
- Штамп `Reviewer-Delegation` ставит раннер (`stamp_reviewer_delegation`,
  `:656-694`). Чужая строка с другой делегацией дает RunnerStop.
  `runner_review_ok` проверяет роль `code_reviewer`, change, статус и пометку
  `package_runner` (`scripts/pr_validate.py:323-345`).
- Интерфейс исполнителя (`scripts/executors/__init__.py`): `preflight`,
  `prepare_workdir` (AGENTS.md или рядом `AGENTS.<имя>.md`, BUG-026), `command`,
  `list_active`, `active_by_binary`, `processes()` с `ps -ww`, `names()` —
  совпадают со скиллом. Таблица pi/hermes/stub соответствует `pi.py`
  (zone-guard, `--no-extensions`), `hermes.py` (`manual = True`), `stub.py`
  (`AF_EXECUTOR_STUB_CMD`).
- `executor_watchdog` выдает `proc:<исполнитель>:<pid>` и пропускает
  `manual`-исполнители (`scripts/executor_watchdog.py:132-148`).
- Резервации пишет `session_check` в `active_sessions.json`
  (`scripts/factory_paths.py:59`, `scripts/session_check.py`).
- В flow-enforcer есть MODEL_ENFORCE (`plugins/flow-enforcer/enforcer.py:96-109`).
- Модели в `agents/roles.json`: SA, architect, DEV, BA — `glm-5.3`, остальные —
  `glm-5.3-flash`. Совпадает с process-context, PLAN.md и скиллом.
- Цитаты Заказчика в `PLAN-executor-swap-skill.md`, записи J65 в backlog и
  скилле/гайде совпадают дословно. Запись J65 только дописана. MAP и PLAN.md
  изменены в сводных строках. Ссылки из `agents/pm_agent.md` и `skills/README.md`
  на месте.
- П.21 (внешний агент только через PR, ревью обязательно), п.4, п.11, п.13,
  п.14, п.16 процитированы верно. Раздел «Оркестрация» («Сам роль не
  выполняй») соблюден. Противоречия п.17 нет (см. m2 о ссылках).

prepare: SKIPPED | reserve: SKIPPED | zone-check/gates: SKIPPED | provenance: SKIPPED
