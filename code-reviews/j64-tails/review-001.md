Вердикт: Вернуть

## Вердикт: return

Ревью ветки chore/j64-tails (worktree /Users/ekotov/AI/ai-factory-t), задачи
J64.9, J64.11, J64.17 (PLAN-j64-tails.md, Флоу 4).
Commit: 4393e03a748806e6e0206d9f6e03e4f0434ee623 (поверх origin/main d0d8e5e).
Ревьюер — независимый сабагент (Claude Code), код не писал, файлы не правил,
ruleset репозитория не менял (только GET).

Итог: CI-часть и ruleset_check по существу верны, тесты зеленые. Вернуть из-за
одного major: шаблон запуска пака debug по-прежнему велит писать лог в
`test-model/regress/`. Это вне новой зоны, и стадия `pi:debug` на finish
упадет OUT_OF_ZONE. Остальное — minor.

## Что проверено фактами

- `gh api repos/actions/checkout/commits/v4` → `11d5960a…7262`,
  `setup-python/commits/v5` → `a26af69b…7065`, `setup-node/commits/v4` →
  `49933ea5…0020`. Все три совпадают с SHA в flow.yml.
- flow.yml разбирается YAML-парсером (ruby YAML.load_file): OK.
- pytest 9.2.0 есть на PyPI: `requires_python >=3.10`, есть классификатор
  3.12. Локальный venv работает на том же 9.2.0, полный сьют зеленый (по
  данным ПМ: 1329 passed).
- В проекты flow.yml ставит пакет `pytest==9.2.0` и больше ничего. Новых
  зависимостей нет: проектный `pytest tests/` раньше брал последний pytest,
  теперь берет закрепленный.
- `ruleset_check.py --repo realax07/ai-factory` и вариант без `--repo`
  вернули exit 0. Реальный ruleset 24385697 «main»: active,
  bypass_actors=[], rules non_fast_forward/pull_request/required_status_checks,
  include refs/heads/main.
- `gen_role_docs.py --check`: таблицы актуальны. agents/README.md (строка 39)
  согласован с roles.json.
- Последствия зоны debug. debug не входит ни в один этап STAGE_TABLE, поэтому
  стадия `pi:debug` идет по ветке `_zone_begin` (scripts/package_runner.py:1093-1124).
  Там делается `narrow_zones` → reserve `docs/project-pitfalls.md` →
  `session_check.check` на finish (`git status --porcelain -uall`,
  session_check.py:449). Неотслеживаемые файлы вне зоны тоже ловятся. Раньше
  при `zones: []` стадия debug сразу давала STOP ZONE_OUTSIDE_POLICY, теперь
  она исполнима. В EMPTY_POLICY_ROLES debug не входил и не входит: флага
  `empty_policy` у него нет. POLICY_VERSION меняется, но finish сверяет
  role_zone_digest (J65.2), так что чужие активные сессии не задеты.
- Пак debug работает только с tools `read/bash`, без `write/edit`. Значит,
  zone-guard механически не участвует: база граблей пополняется через bash
  (`>>`), и запись вне зоны ловит только сверка диффа на finish. Для этой роли
  такая граница приемлема, но в доках пака она не названа (см. #3).
- Флоу 3 и incident-лог: flow_check и pr_validate каталог
  `test-model/incidents/` не сканируют, поэтому имя
  `<YYYY-MM-DD>-S2-emergency-merge.md` им ничего не ломает. Имя проходит
  грамматику incident_ref (`S2-emergency-merge`) и правило именования D4
  (flow_transition.py:1708-1713).
- Документация GitHub REST («Update a repository ruleset», `PUT
  /repos/{owner}/{repo}/rulesets/{ruleset_id}`): все поля тела необязательные,
  `enforcement` принимает disabled|active|evaluate. О сохранении опущенных
  полей там ничего не сказано. На практике GitHub трактует PUT с одним
  `enforcement` как частичное обновление, остальные поля не теряются. Но
  документацией это не гарантировано, поэтому нужен снимок и восстановление
  по нему (см. #5). Для «Get a repository ruleset» в документации есть
  оговорка: bypass_actors возвращается только пользователю с правом записи в
  ruleset (см. #2).

## Замечания

| # | Серьезность | Где | Что не так | Как на самом деле | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | skills/pm-factory/pi/role-packs/debug/README.md:58 | Бриф в шаблоне запуска заканчивается словами «Лог диагностики: test-model/regress/». | Новая зона — только `docs/project-pitfalls.md`. role-agents.md:33 говорит «Отчет диагностики — ответом, не файлом», бэклог (J64, запись 2026-11-10) — «лог диагностики в test-model/regress/ снят». Пак работает через bash, guard такую запись не остановит. ПМ, скопировавший шаблон, получит запись в `test-model/regress/`, и `session_check.check` уронит стадию (OUT_OF_ZONE → STOP). | Убрать «Лог диагностики: test-model/regress/» из брифа. Вместо этого написать «отчет — ответом; грабли — append в docs/project-pitfalls.md». |
| 2 | minor | scripts/ruleset_check.py:294-295 | Проверка bypass пропускает ответ без поля: если `bypass_actors` нет, скрипт печатает «bypass никому». | GitHub отдает bypass_actors только пользователю с правом записи в ruleset. При чтении токеном без этого права скрипт выдаст ложный OK, хотя в README-flow-control.md пользователем назван «Заказчик/ПМ». Для реального репозитория с токеном админа результат верный. | Если ключа `bypass_actors` нет, ставить exit 2 (UNKNOWN) или проверять `current_user_can_bypass` и отдельно требовать наличие ключа. Добавить тест «поле отсутствует». |
| 3 | minor | skills/pm-factory/pi/role-packs/debug/settings.example.json:3; debug/README.md:13; role-agents.md:28 | В комментарии settings осталось «у debug это только лог диагностики test-model/regress/**». В README сказано «tools read/bash (read-only — без edit/write)», хотя у роли теперь есть зона записи. Заголовок «Зоны (механически охраняет zone-guard)» при этом неверен. | Без `write/edit` guard ничего не охраняет: append в pitfalls идет через bash, и границу держит только finish (сверка диффа). | Исправить комментарий settings. Явно написать: «pitfalls пополняется через bash (append); запись вне зоны ловит сверка диффа на finish, guard — только для write/edit». Либо добавить в tools `edit`, чтобы guard работал. |
| 4 | minor | agents/debug_agent.md:25-27 против :34-35 и role-agents.md | Фабричный промпт требует пополнять базу граблей «одним коммитом в своей зоне» и тут же запрещает «никаких коммитов». | Расхождение было и раньше, но теперь у роли есть реальная зона, и оно стало заметным. В раннере коммит стадии делает сам раннер. | Одна формулировка: «правка docs/project-pitfalls.md (коммит — раннер/ПМ), других коммитов нет». |
| 5 | minor | docs/runbook-emergency-merge.md:154, 181-183 | Снимок пишется в `/tmp/ruleset-main-before.json`, а восстанавливать его предлагается руками через UI. | /tmp переживает не всё (перезагрузку, другую машину). Восстановление через UI легко упустит поле, например required checks. Документация PUT не гарантирует сохранение опущенных полей. | Снимок хранить рядом с incident-записью или в `~/`. Для восстановления дать команду: `jq '{name,target,enforcement,conditions,rules,bypass_actors}' snapshot \| gh api -X PUT repos/$R/rulesets/$ID --input -`. |
| 6 | minor | docs/runbook-emergency-merge.md:185-189 | Сказано «тот же формат, что post-mortem Флоу 3, J48», но перечислены другие разделы: таймлайн, причина, PR/SHA, исполнитель. | Ворота post-mortem требуют заголовки `## Таймлайн`, `## Root cause`, `## Action items` (flow_transition.py:1716, 1773-1784). Если эпизод будет оформлен как Флоу 3 S2, запись без этих заголовков не пройдет. Кроме того, ref `S2-emergency-merge` одинаков для всех эпизодов, и матч по границам возьмет последний файл. | Перечислить обязательные заголовки дословно. Имя делать уникальным, например `<date>-S2-emergency-merge-<N>.md`. Указать маркер PR записи ([docs]/[ops]). |
| 7 | minor | scripts/ruleset_check.py:296-305 | Не проверяется, на что нацелен ruleset: `target`, `conditions.ref_name.include`. | Ruleset с именем «main», но нацеленный не на refs/heads/main или ~DEFAULT_BRANCH, пройдет проверку. | Проверять `target == "branch"` и наличие `refs/heads/main` или `~DEFAULT_BRANCH` в include. |
| 8 | minor | tests/unit/test_j64_tails.py:489-494 | Расхождения покрыты для enforcement, bypass, pull_request и flow. | Не покрыты: отсутствие non_fast_forward, отсутствие ключа bypass_actors (#2), ветка `fetch_ruleset` (мок `_gh`: ruleset не найден → exit 2). | Добавить эти три кейса. |

Наблюдение вне диффа: Hermes-делегация роли debug через `flowctl prepare`
по-прежнему невозможна. debug не входит ни в один этап STAGE_TABLE, поэтому
prepare вернет WRONG_ROLE (flow_transition.py:2202), и рабочим остается только
путь раннера (ROLE_WITHOUT_STAGE). Это не регрессия, но в
agents/debug_agent.md сказано «ПМ диспатчит debug-агента», а путь вызова не
назван. Кандидат в бэклог.

## Вердикт: return
