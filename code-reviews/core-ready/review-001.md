# Ревью core-ready (J65.6 «ядро готово») — review-001

- Пакет: PLAN-core-ready.md (Флоу 4), ветка `chore/core-ready`
- Коммит: faf659c, дифф `git diff origin/main...HEAD` (23 файла)
- Ревьюер: code_reviewer (независимый сабагент Claude Code, автор диффа — другая сессия). Только статика и короткие проверки.
  pytest в окружении ревьюера не установлен. Без pytest, вызовом функций, прогнаны
  `test_core_boundary_no_hermes_outside_adapter`, `test_boundary_detector_catches_violation` и все 5 тестов
  `test_j65_gates_changelog.py`: PASS. Плюс пробы обхода (ниже).

## Вердикт: return

## Находки

### B1 (blocker): sidecar внешнего агента засчитывается без проверки и вне CI; решения «Provenance-файл ревью» нет в плане

`scripts/pr_validate.py:489-496`. Ревьюера вида `<агент>:<id>` код засчитывает по форме записи, без реестра и без учета
`in_ci()`. Проба: репозиторий без `state.db` и без state раннера, вне CI (`GITHUB_ACTIONS` и `GITHUB_EVENT_PATH` сняты).
В `code-reviews/add-x/` лежат `review-001.md` с `## Вердикт: approve` и sidecar
`{"author_delegation":"x:a","reviewer_delegation":"x:b", sha=HEAD, diff_digest:"z", ...}`.
Результат: `review_independence_findings(...) == []`, то есть ревью засчитано.
Любой агент, который может написать два файла, проходит проверку независимости во Флоу 1 и Флоу 2. Для этого не нужен
ни реестр, ни ревьюер, а id «автора» и «ревьюера» он выбирает сам. Решение «SKIPPED в CI, DENY локально» и критерий
плана «pr_validate fail-closed вне CI» на этой ветке не выполняются.

Кроме того, поведение обосновано «решением Заказчика 2026-11-16 „Provenance-файл ревью“». Ссылки:
`pr_validate.py:454`, `tests/unit/test_j65_core_ready.py:5`, `docs/guides/external-orchestrator.md:73`, резолюция в
backlog J65. В PLAN-core-ready.md, разделе «Решения Заказчика (дословно)», такого ответа нет: там 4 ответа и решение
от 2026-11-15. В `decisions/` его тоже нет. Это нарушает п.18: решение передается только зафиксированным артефактом
и дословно.

Что сделать:
1. Внести в PLAN-core-ready.md вопрос и ответ дословно. Если такого ответа не было, эскалировать ПМ и Заказчику.
2. Пока ответа нет, применить к ревьюеру `<агент>:<id>` ту же схему, что и к deleg_ без реестров: в CI — `UNVERIFIED`,
   вне CI — отказ. Сценарий внешнего оркестратора это не ломает: его PR проверяет только CI. Структурные проверки
   sidecar (scope, вердикт, автор ≠ ревьюер, SHA, digest) оставить как есть.
3. Тест `test_sidecar_external_agent_accepted` разделить на два: в CI — UNVERIFIED и PASS, вне CI — отказ.

### M1 (major): исключение `session_watchdog.py` из границы обосновано неверно и выходит за ответ Заказчика

`tests/unit/test_j65_core_ready.py:46-52`, `docs/CHANGELOG-gates.md:24-26`, резолюция в backlog J65. Исключение
обосновано так: утилита «лечит роутинг Telegram-гейтвея… не ворота и не проверка». По коду это не так.
`scripts/session_watchdog.py:79-80` читает `async_delegations` и ищет залипшие holds. Строки `:146-158` ищут
dropped-делегации, результат которых не доставлен, и сами печатают SQL к `state.db`. `docs/guarantees.md:54` описывает
его как проверку: «залипшие сессии/ключи, dropped-делегации детектируются». Значит, это проверка работы конвейера по
реестру делегаций, то есть ровно то, что граница «Ворота и проверки» должна убрать из ядра. В вопросе Заказчику
session_watchdog не назывался.

Что сделать (п.5, противоречие не решать самому), один из двух вариантов:
- (а) Перевести чтение `async_delegations` на адаптер. Нужен метод hermes, который отдает поля `routing_key`,
  `delivery_state` и `parent_session_id`. В исключении оставить только роутинг гейтвея (`sessions`, `gateway_routing`)
  и сузить детектор под это.
- (б) Эскалировать Заказчику дословным вопросом «session_watchdog — исключение границы?». Пока ответа нет, в
  CHANGELOG, тесте и backlog описать исключение по факту: он читает и реестр делегаций.

### m1 (minor): детектор границы пропускает часть нарушений

`tests/unit/test_j65_core_ready.py:53, 63-81`. Детектор ловит только вызов с именем `hermes_home` и строки с
`state.db`, `async_delegations`, `HERMES_HOME`. Проба: файл с `H = fp.hermes_home` и `H() / "cache" / "delegation" / "live"`
плюс `Path("~/.hermes/logs/errors.log")` дает `hits == []`. План (п.6) и резолюция включают в запрет «кеш делегаций»,
транскрипты и лог ошибок, но детектор их не видит. Сейчас нарушений нет: grep по `scripts/*.py` чистый. Но новый
код с такими обращениями тест пропустит.

Что сделать: ловить любое упоминание атрибута или имени `hermes_home`, а не только вызов. Добавить в запрет пути
`"live"` в связке с `"delegation"`, `"task-0.log"` и `"errors.log"`. В пробу детектора добавить алиас и путь кеша.

### m2 (minor): итог «PR-VALIDATE OK» скрывает UNVERIFIED

`scripts/pr_validate.py:527, 1386`. Пометка UNVERIFIED уходит в stderr, а итоговая строка остается
`PR-VALIDATE OK … обязательные артефакты на месте`. gate_runner и человек, который смотрит итог, видят PASS. Это
противоречит п.9 «Не сглаживай». Заказчик выбрал вариант «SKIPPED в CI», а код и доки пишут UNVERIFIED. Сам термин
допустим, но в плане стоит сказать, что это одно и то же.

Что сделать: при непустом `unverified` печатать в итоге `PR-VALIDATE OK (UNVERIFIED: N — независимость ревью не
проверена)`. Для этого вернуть `unverified` наверх, например через модульный счетчик.

### m3 (minor): тест CHANGELOG проверяет не все коды

`tests/unit/test_j65_gates_changelog.py:51-53, 30-39`.
- `TOKEN_RE` требует хотя бы один `_`. Однословные коды сканер не видит: `BYPASS` из `executor_watchdog.py:170` и
  `delegate_watchdog.py:278`, который есть в ядре, но не в CHANGELOG, а также новый `UNVERIFIED` этой версии.
- Коды, собранные f-строкой, тоже не видны.
- `documented()` засчитывает любой токен в обратных кавычках в любом месте файла, а не только в таблице кодов.
- Набор файлов сверяется только с `FLOW_CONTROL_FILES`, без `.py` из `COPY_FILES` (flow_preflight, stand_reaper,
  session_archive и др.).

Смыслы кодов выборочно сверены с кодом: STALE_SNAPSHOT, ARCH_REVIEW_MISSING, PLAN_FLOW_UNDECLARED,
DUPLICATE_PAYLOAD, CID_REQUIRED, BASE_MISSING, WORKTREE_MISSING, MODEL_ENFORCE, EXECUTOR_UNAVAILABLE,
UNKNOWN_ANCESTRY, REGRESS_FINAL_STALE, FLOW5_RETRO_MISSING. Все верны.

Что сделать: внести `BYPASS` и `UNVERIFIED` в CHANGELOG и явно задать для сканера список однословных кодов. Сверять
`documented()` только по строкам таблиц `| \`CODE\` |`.

### m4 (minor): `session_archive.finished_runs()` без защиты импорта

`scripts/session_archive.py:66`. `import executors` стоит без try. Если в копии ядра нет пакета, будет traceback.
`delegate_watchdog` в том же пакете это обрабатывает (WARN и `None`). Стоит сделать единообразно: WARN и пустой
список.

### m5 (minor): порядок review-файлов во Флоу 2 держится на сортировке имен

`scripts/pr_validate.py:93-100`. Имя `review-001.md` не подходит ни под `REVIEW_FILE_REV_FIRST`, ни под
`REVIEW_FILE_TASK_FIRST`. Номер получается 0, и последний файл выбирается по имени. Для стандартных имен результат
верный, но при смеси форм решает не номер: `review-fix-001.md` (1) обгонит `review-002.md` (0).

Что сделать: добавить разбор `^review-(\d{3})\.md$` и тест на смесь форм.

### m6 (minor): сверка scope во Флоу 2 различается по регистру и slug

`scripts/pr_validate.py:337-340`, `:385`. `runner_review_ok` сравнивает `scope.change == change_id` точно, с учетом
регистра. `dev_delegations` сравнивает в нижнем регистре. Грамматика `flow_ids` допускает scope Флоу 2 со slug
(`BUG-042-search-card`), а pr_validate строит `scope_id = BUG-042`. Ревью стадии раннера с таким scope не засчитается:
вне CI получится ложный отказ. Dev-делегации с таким scope не попадут в набор SELF_REVIEW.

Что сделать: сравнивать scope одной функцией, без учета регистра и с префиксом `BUG-NNN(-slug)`.

### m7 (minor): доки обещают «проверит pre_merge ПМ», но это не гарантировано

`docs/ci-gates.md:52-54`, `docs/CHANGELOG-gates.md:37`, `docs/guarantees.md:43`, skill executor-swap. `gate_runner`
запускает pr_validate в pre_merge только с `--pr-id` (`scripts/gate_runner.py:431-444`). Без него шаг SKIPPED, и
независимость ревью не проверяет никто. Стоит дописать: «pre_merge с `--pr-id`».

## Проверено, замечаний нет

- **Определение CI.** `in_ci()` смотрит `GITHUB_ACTIONS=true` и `GITHUB_EVENT_PATH`. Подделка env что-то дает только
  на машине без реестров. На VPS реестр доступен, поэтому ветки UNVERIFIED там нет, и pre_merge с `--pr-id` работает
  fail-closed. В шаге pytest CI `GITHUB_ACTIONS` остается (`env -u` снимает только `GITHUB_EVENT_PATH`). Фикстура
  `env` в `test_j65_core_ready` снимает обе переменные. Остальные тесты ревью (`test_j65_pi_review_j10`) создают
  `state.db` и от CI не зависят.
- **Независимость в delegation_findings.** Порядок проверок: dev → раннер → Hermes. Состояние не completed и
  отсутствующая делегация дают отказ. Битая база дает «недоступен», а не PASS. `dev_delegations` исключает стадию
  code_reviewer per_task. Эталон `test_j65_reference_run` (подпроцесс pr_validate с state раннера) проходит раньше
  реестра Hermes.
- **Правки тестов.**
  - `test_audit_fix_gates`: фильтр `code-reviews/` оставляет сверку контракта баг-репорта (ревью проверяется
    отдельно), проверка не ослаблена.
  - `test_gate_harness`: `GITHUB_ACTIONS=true` в `ci_env` соответствует шагу Actions. Страж чистоты env сужен
    ровно на эту переменную.
  - `test_factory_paths`: проверка стала строже (`not hasattr(alt, "hermes_home")`).
- **Ядро в проектах.** `scripts/executors/*` входят в `FLOW_CONTROL_FILES` и ставятся вместе с pr_validate.
  Запасной блок путей без `hermes_home` согласован с тестом TC-FP-009. После удаления запасного SQL
  `delegate_watchdog` без пакета executors пишет WARN и пропускает прогон: это покрыто тестом.
  `chat_degrade_watchdog` в проекты не копируется.
- **Доки и история.** backlog J65 и MAP только дописаны. Четыре цитаты из PLAN-core-ready.md совпадают дословно.
  Пятая не прослеживается, см. B1. Флоу 2 и UNVERIFIED описаны в ci-gates, guarantees, rules-enforcement,
  README-flow-control, гайде и скилле согласованно с кодом, кроме m7.
