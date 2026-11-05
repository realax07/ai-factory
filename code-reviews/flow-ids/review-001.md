Вердикт: Одобрить

# Ревью 001 — J65.3 flow-ids (единая грамматика scope флоу)

- Пакет: flow-ids (Флоу 4), ветка `chore/flow-ids`
- Коммит: `473afb78e43d36c2f0e7a6308c2e71c7e8ee10b0`
- Ревьюер: code_reviewer (независимое статическое ревью; автор диффа — другой исполнитель)
- Арбитры: PLAN-flow-ids.md (решения Заказчика 2026-11-05), backlog/J65-… задача J65.3, openspec/specs/incident-protocol (формат incident_ref)

Blocker и major нет. Есть пять minor, ни одно не мешает влитию.

## Замечания

| # | Сев. | Файл:строка | Сценарий отказа | Рекомендация |
|---|---|---|---|---|
| 1 | minor | `templates/task_delegation.md:9,11` | Шаблон, по которому ПМ собирает заголовок делегации (AGENTS.md, J43), по-прежнему пишет: «Ф2 — `BUG-NNN`», «Ф3 — incident-id (формат любой)», и в списке «очевидных ошибок» нет Ф1/Ф4/Ф5. После этого коммита энфорсер на спавне блокирует (`FLOW_MARKER_INVALID`) однословный scope Ф1, scope Ф4/Ф5 не в kebab и Ф3 не вида `S<1-3>-<kebab>`. ПМ по шаблону соберет маркер, который отклонят. `docs/README-flow-control.md:46,50` тоже говорит «BUG-NNN». | Это отдельный пункт Флоу 4 (templates/ и docs/ вне зоны этого пакета): привести шаблон к `flow_ids.SCOPE_HINTS`. Риск уже отмечен в PLAN («Внимание при выкатке»), но в документ, который читает ПМ, не попал. |
| 2 | minor | `plugins/flow-enforcer/enforcer.py:1019-1026` | Ф3 стал строже: раньше проходило `S1-что угодно`, теперь только `S1-[a-z0-9]+(-[a-z0-9]+)*`. Отказ для `S1-Prod` или `S1-prod_down` по-прежнему говорит «требует scope формата S<1\|2\|3>-<краткий-ид>», а `S1-Prod` под эту формулировку подходит. Это вводит в заблуждение. В текстах Ф2 (стр. 1016-1018) не сказано, что допустим суффикс-slug. | Брать текст отказа из `SCOPE_HINTS` (или из fallback-копии) и явно писать «slug: строчные латинские буквы, цифры, дефис». Тест TC-J48-013 проверяет только подстроку `S<1\|2\|3>`, поэтому сохранить ее легко. |
| 3 | minor | `plugins/flow-enforcer/enforcer.py:168-177` | Загрузчик молча переходит на fallback при любом исключении: нет фабрики, старая фабрика без `flow_ids.py`, у модуля нет ключа. Работает правильно (решение fail-safe, не fail-open: копия совпадает по тесту), но по логу нельзя понять, по какой грамматике сейчас работает энфорсер на VPS. Это как раз сценарий из PLAN: «переустановить плагин после merge». | Пометить источник (например, `_GRAMMAR_SOURCE = "flow_ids"\|"fallback"`) и писать его в событие `prepare_result` или в однократное WARNING при первом вызове хука (на import-time `log_event` еще не определен). |
| 4 | minor | `scripts/flow_ids.py:32-46` (и копии) | Якорь `$` в Python допускает перевод строки в конце: `valid_scope(1, "add-widget\n")` возвращает True (проверено). Через маркер энфорсера это не пролезет (`[^\s]+`), но через CLI `flowctl --change` или `package` манифеста раннера — да, и scope дальше попадает в пути (`test-model/bugs/{scope}.md`, `PLAN-{scope}.md`). Так было и раньше, не регрессия. | В `valid_scope` перейти на `fullmatch` (или `\Z`) раз и навсегда, раз грамматика теперь в одном месте. Fallback-копию и тест TC-004 обновить синхронно. |
| 5 | minor | `plugins/flow-enforcer/enforcer.py:1002-1035`, `1420` | У `validate_scope_for_flow(flow∉1..5, s)` нет ветки, и функция молча пропускает такой вызов (проверено: flow=7 не бросает). Сейчас недостижимо: `_validate_flow`/`resolve_flow` раньше нормализуют flow. Защита держится на порядке вызовов. Кроме того, проверка scope стоит до обработки bypass, поэтому после этого коммита запись реестра bypass для Ф1/Ф4/Ф5 с не-kebab scope тоже не сработает. Для Ф2/Ф3 так было и раньше, поведение консистентно. | Добавить в конце `else: raise FlowMarkerError(...)` (fail-closed) или заменить ветки одним `if not marker_scope_valid(flow, scope)`. Про bypass: зафиксировать в plugins/README.md, что bypass не снимает грамматику маркера. |

Наблюдения, которые не считаю дефектами:
- `enforcer.SEVERITY_PREFIX_RE` (`^(?:…)-`) больше не используется в логике, остался ради TC-J48-014. Его форма отличается от `flow_ids.SEVERITY_PREFIX_PATTERN` (группа без захвата). Это безвредно.
- ТЗ J65.3 требует перенести в модуль разбор заголовка и функцию «scope → флоу», а также «раннер импортирует». PLAN явно и с обоснованием выводит это из объема: второго разборщика заголовка нет, slug неоднозначен, у `package_runner` нет своей грамматики (он передает `manifest["package"]` в `flowctl prepare --change`, проверяет движок). Резолюция в backlog это отражает. Это отклонение от ТЗ, которое ТЗ разрешает обосновать, а не нарушение решения Заказчика.
- Грамматика маркеров PR в `pr_validate.py:1028,1069` и `flow_scope_check.py:39,47` (`[BUG-\d+]`) не совпадает с `BUG_ID_PATTERN` (`[BUG-AF-RECHECK-001]` маркером PR не распознается). Это другая грамматика, заголовок PR, и в J65.3 она не входила. Кандидат в бэклог.

## Адверсариальная проверка: поведение вне решений Заказчика

Движок (`flow_state.check_flow_identifier`, flow → было → стало):
- Ф1: `CHANGE_ID_RE`, без изменений.
- Ф2: `^BUG-\d{3}$` с IGNORECASE → `BUG_ID_PATTERN`. Стало шире (комплекс, slug), но `bug-042` в нижнем регистре теперь FLOW_ID_INVALID. Это решение Заказчика «как имена репортов»: таблица PLAN явно фиксирует «регистр не важен» как расхождение, и выбран паттерн без IGNORECASE. Других потребителей у `flow_state.BUG_ID_RE` нет (grep по `*.py`). `check_bug_fix` ищет репорт через `flow_check.bug_report_paths`, так что более широкий id корректно находит `BUG-AF-RECHECK-001.md` и `BUG-001-slug.md`.
- Ф3: только `BUG-NNN` → incident-ref или легаси BUG. Ограничений в движке не прибавилось (S1-… раньше было FLOW_ID_INVALID). Проверка severity в `check_emergency_stabilize`/`check_archive_flow3` идет по `SEVERITY_PREFIX_RE` (тот же объект, ссылка из flow_ids, поведение прежнее). Этапы Ф3 не читают `test-model/bugs/<change>`, поэтому scope S1-… ничего не ломает.
- Ф4: `CHORE_RE` = `SLUG_RE`, без изменений (`chore` проходит, TC-PR-060 J64.3 зеленый в полном сьюте по данным ПМ).
- Ф5: `CHANGE_ID_RE` → `SLUG_RE`, только расширение. Это решение «Ф5 slug».
- `flowctl.ambiguous_field_hints`: flow вне 1–5 отсекается раньше обращения к `SCOPE_HINTS[flow]`, KeyError невозможен. Пустой `change` дает подсказку (`valid_scope("")` возвращает False); `inspect` для пустого change и так бросает исключение.

Энфорсер (маркер):
- Ф1/Ф4/Ф5: «любая непустая» → грамматика движка. Новых ложных DENY по сравнению с итоговым вердиктом нет: такой scope раньше доходил до prepare и получал FLOW_ID_INVALID (AMBIGUOUS/UNKNOWN), что означало блок. Post-filter `no_change_scope_ok` срабатывает только на причины «change-пакет openspec/changes/», а не на FLOW_ID_INVALID, так что спасательного пути для таких scope не было. Отличие только в двух вещах: отказ приходит раньше, и bypass из реестра его не снимает (замечание 5).
- Легаси-маркер `change=` без `flow=`: трактуется как Ф1 (или как флоу из env FLOW_ENFORCER_FLOW) и теперь требует kebab change-id с дефисом. Легаси `change=BUG-001` при дефолтном Ф1 раньше тоже получал DENY от движка (FLOW_ID_INVALID), так что поведение по сути то же. Новых обходов нет.
- Ф3: строже, чем `S1-.*`. Сверил с реальными incident-ref в репо (grep `S[1-3]-…` по .md/.py: `S1-prod-down`, `S2-login-degraded`, `S1-login-500`, `S2-cart-500`, `S3-footer-typos`, `S1-prod-down-2`, `S2-inc-1` и др.). Все в нижнем регистре через дефис, проходят. Единственный `S1-Prod` — негативный пример в тесте. `archive/test-model/incidents/` содержит только README. Спека incident-protocol (стр. 95-98) задает `S1-<краткий-ид>` без алфавита, сужение до kebab соответствует решению Заказчика «S<1-3>-<slug>».
- Цепочка Ф3 энфорсер → движок: scope идет и как `--change`, и как `--incident-ref` (`prepare_command`). Расхождение, ради которого затевался J65.3, закрыто (TC-J65-FID-005).

Загрузка `flow_ids` в энфорсере:
- Порядок: `factory_home()/scripts` вставляется в `sys.path[0]` (если его там еще нет), затем `import flow_ids`. В модуле только `import re`, побочных эффектов нет. Это легче прежнего импорта `flow_check`/`flow_transition`.
- Старая фабрика без `flow_ids.py` → ImportError → fallback. У модуля нет ключа → AttributeError → fallback. `factory_home()` бросает → fallback. Любой из этих случаев дает копию, совпадающую с модулем по TC-004. Это fail-safe, обхода нет. Исключение внутри хука по-прежнему ведет в `except Exception` → block (fail-closed не изменился).
- Смешанные версии: старый плагин с новой фабрикой. Старый плагин импортирует `flow_check.BUG_ID_PATTERN` и `flow_transition.SEVERITY_PREFIXES`, оба имени сохранены. Ф3 S1-… начнет проходить движок, остальное как раньше.
- В стенде ПМ (`HOME=vps-home`, фабрики в `~/ai-factory` нет) энфорсер реально работает на fallback, в pytest на модуле (тест сам кладет scripts/ в sys.path). Ветка модуля и ветка fallback обе покрыты тестами на совпадение.

Regex:
- `CHANGE_ID ^[a-z0-9]+(?:-[a-z0-9]+)+$`: ведущий, хвостовой и двойной дефис отклоняются, заглавные тоже.
- `SLUG`: то же, но с `*`.
- `BUG_ID`: без IGNORECASE, `\d{3}` ровно три цифры (`BUG-01` и `BUG-0001` отклоняются). В slug допускаются `.` и `-` в хвосте, но слэша нет, выхода из каталога при подстановке в путь нет.
- `INCIDENT_REF`: severity строго из allowlist, slug kebab.
- `valid_scope` для flow вне 1–5, для `None` и для flow-строки возвращает False.
- Висящий `$`: замечание 4.

## Тесты

- TC-J65-FID-001/002/003 гоняют одну таблицу (24 строки, все флоу, позитивные и негативные, включая легаси Ф3 «движок да, маркер нет») против модуля, энфорсера и движка. Если вернуть прежнее расхождение (например, Ф3 в энфорсере снова `S1-.*` или Ф5 в движке снова change-id), падают строки `S1-Prod`/`typo`. Тесты ловят.
- TC-004 сравнивает fallback-копию, литерал `flow_check.BUG_ID_PATTERN` и `INCIDENT_REF_RE.pattern` с модулем. Мутация в одном месте его ломает, что подтверждают мутационные данные ПМ (SLUG в fallback → 3 падения).
- TC-005 проверяет сквозной Ф3, TC-006 проверяет единый allowlist severity (`is`-идентичность).
- TC-AUD-011 `[test-adapted]`: подсказка Ф3 сменилась с «BUG-NNN» на «incident-ref». Это прямое следствие решения «Ф3 — incident-ref», ослаблением теста не является: проверка «поле названо + формат флоу» сохранена.
- Трассировка: TC-J65-FID-001..006 перечислены в docstring модуля тестов и указаны в коммите и резолюции backlog.

## Проверено

- `git show 473afb7`: полный дифф scripts/, plugins/, tests/, backlog, PLAN.
- Все потребители старых имен (`BUG_ID_RE`, `CHORE_RE`, `CHANGE_ID_RE`, `SEVERITY_PREFIX*`, `FLOW_EXPECTATIONS`, `validate_scope_for_flow`) найдены grep по `*.py`. Ими пользуются только flow_state, flowctl, flow_transition, enforcer и тесты. package_runner, pr_validate, delegate_gate и flow_check собственной грамматики scope флоу не держат (у pr_validate и flow_scope_check грамматика заголовка PR, см. наблюдения).
- Реальные incident-ref в репо и формат в спеке incident-protocol.
- Точечный прогон из worktree: `HOME=…/vps-home python3.14 -m pytest tests/test_j65_flow_ids.py tests/test_j48_incident_protocol.py tests/test_recheck2_fixes.py tests/test_bug_af_recheck_002.py tests/test_audit_ergonomics.py tests/test_j431_flow_aware.py -q -p no:cacheprovider` → `188 passed, 1 skipped`.
- Ручные пробы: `marker_scope_valid(1, "add-widget\n")` → True (замечание 4); `validate_scope_for_flow(7, "x")` не бросает (замечание 5); в стенде без фабрики энфорсер на fallback.
- `python3 scripts/flow_check.py .` → `flow_check: OK`. openspec/ и contracts/ коммит не трогает.

## Не проверено

- Полный сьют не повторял (данные ПМ: 1203 passed, 2 skipped) и мутации тоже (данные ПМ).
- Реальный Hermes на VPS: какой плагин установлен, есть ли env `FLOW_ENFORCER_FLOW`, есть ли записи в `flow-bypass-decisions.json` со scope, который теперь не по грамматике. Локально реестра bypass нет, в `~/.hermes/state/flow-enforcer.log` только тестовые записи `add-widget`.
- Копии `flow_check.py` в проектах-клиентах (ekotov-wiki): литерал `BUG_ID_PATTERN` в них этот коммит не меняет, совпадение с фабрикой проверяется только для копии в фабрике.
- CI на ветке.
- Формат вердикта: строка задана оркестратором (`Вердикт: Одобрить`, совпадает с манифестом пакета). Машинного блока J52 (`## Вердикт: approve` + `Reviewer-Delegation:`) здесь нет, единый формат вводит J65.4.

## Закрытие minor (ПМ, после ревью)

- №1 устаревшие форматы: `templates/task_delegation.md` (scope по флоу, список очевидных ошибок) и `docs/README-flow-control.md` (Ф2, Ф3) приведены к грамматике flow_ids — правка в этом же пакете, а не отдельным Флоу 4: без нее шаблон маркера ведет к блоку.
- №2 текст отказа Ф3: формат `S<1|2|3>-<kebab-slug>` и «строчные буквы/цифры через дефис».
- №3 источник грамматики: `GRAMMAR_SOURCE` (`flow_ids`/`fallback`) — в текстах всех отказов маркера по scope.
- №4 `fullmatch` в `flow_ids.valid_scope` и `marker_scope_valid`; в таблицу тестов добавлены scope с `\n`. Добавленный кейс поймал оставшийся `BUG_ID_RE.match` в ветке Ф2 `validate_scope_for_flow` — заменен на `marker_scope_valid`.
- №5 flow вне 1–5 — финальный отказ в `validate_scope_for_flow`; про bypass и грамматику маркера — абзац в `plugins/README.md`.
- Наблюдение про `[BUG-\d+]` в pr_validate/flow_scope_check — кандидат в бэклог (другая грамматика: маркер PR).

Тест TC-J65-FID-007 (источник грамматики, fail-closed по flow).
