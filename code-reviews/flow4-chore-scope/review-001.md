Вердикт: Одобрить
Ревьюер: code_reviewer (сабагент Claude Code)
Коммит: e5ec1976bd37af2804d300e71276472e1fefc4e1

Предмет: `git diff origin/main...HEAD` ветки `chore/flow4-chore-scope` (1 коммит, J64.3) — `CHORE_RE` принимает `chore` или kebab-slug; подсказка flowctl; снятие Ф4-костыля постфильтра энфорсера; `--pm-mode sessions --pm-registry` в `flowctl finish` раннера; тесты.

## Замечания

| # | Серьезность | Файл:строка | Проблема | Сценарий отказа | Рекомендация |
|---|---|---|---|---|---|
| 1 | minor | scripts/flow_state.py:49; scripts/flow_transition.py:331, 374 | Пространство scope Флоу 4 теперь включает id Флоу 1 (`add-widget`) и, из-за IGNORECASE, BUG-id (`BUG-001`). `_plan_release` проверяет только наличие строки «Флоу: N», но не сверяет N с выбранным флоу. | `flowctl prepare --flow 4 --scope add-widget` при существующем `PLAN-add-widget.md` с «Флоу: 1» проходит план-ворота Флоу 4 → `chore_task` без ворот requirements/SA. Раньше в реальном prepare это было невозможно, а в dry-run энфорсера проходило через постфильтр, так что выросла только поверхность. Смягчено: `PROTECTED_PATHS` (openspec/, contracts/, AGENTS.md) и `pr_validate check_chore` на мердже (блок продуктового кода и спек). | Пункт в бэклог: в `_plan_release` требовать, чтобы объявленный N совпадал с `scope.flow` (DENY `PLAN_FLOW_MISMATCH`). При желании — убрать IGNORECASE из `CHORE_RE` (имена пакетов в нижнем регистре). |
| 2 | minor | scripts/flow_state.py:49 | Из-за IGNORECASE проходит `Chore-X`, а поиск `PLAN-Chore-X.md` на Linux/CI чувствителен к регистру. | Расхождение macOS/Linux; срабатывает fail-closed (`PLAN_RELEASE_MISSING`), вреда нет. | Закрывается вместе с п.1 (убрать IGNORECASE). |
| 3 | minor | scripts/flow_state.py:58; scripts/delegate_gate.py:214 | Устаревшие тексты: `FLOW_EXPECTATIONS[4] = "[chore] …"` и комментарий `# Флоу 4: ровно "chore"`. | Диагностика и документация вводят в заблуждение о допустимом формате. | Обновить на «chore или kebab-slug» (следующим chore). |
| 4 | minor | plugins/flow-enforcer/enforcer.py:247-252 | Список паттернов общий для Ф2/4/5. Удаление паттерна ужесточает Ф2/Ф5: раньше `FLOW_ID_INVALID` с существующим scope-файлом гасился постфильтром, например Ф5 с однословным slug `cleanup` плюс `PLAN-cleanup.md` или Ф2 со scope не в формате BUG-NNN. Теперь — block. | Регрессии безопасности нет: это ужесточение в сторону fail-closed и корректное поведение (неверный формат id = отказ по существу). Но изменение не задокументировано, и тест его не закрепляет. | Отметить в PR/бэклоге. Добавить тест: Ф5 со slug не в формате change-id и существующим файлом → block. |

Замечаний blocker/major нет.

## Проверенные аспекты

- Все места использования `CHORE_RE`: `flow_state.check_flow_identifier` (единственный путь к `FLOW_ID_INVALID` → `AMBIGUOUS_STATE` в flow_transition:2137) и `flowctl.ambiguous_field_hints`. Других потребителей нет: `pr_validate check_chore` работает с маркером PR `[chore]`, а не со scope; `flow_scope_check.GENERIC` не связан с `CHORE_RE`.
- Поиск плана Флоу 4 (`plan_release_paths` → `PLAN-<slug>.md`) и `scope_file_candidates` энфорсера согласованы со slug.
- Ворота `check_chore_task`: защищенные пути и `rules_change` остаются в силе независимо от scope.
- Постфильтр `no_change_scope_ok`: оставшийся паттерн «change-пакет openspec/changes/» покрывает класс «нет change-пакета». Удаленный паттерн давал ALLOW на ошибку формата id. Его снятие — fail-closed (п.4).
- `--pm-mode sessions --pm-registry` в `package_runner.gate_end`: `pm_mode`/`pm_registry` использует только `adapter_pm_bounds` (gate_runner:395-428). Для стадий без `pm_bounds_check` аргументы инертны. Для Флоу 4 это убирает ERROR «режим не задан». `gate["registry"]` — тот же реестр резервации стадии, режим выбран корректно.
- Честность тестов: в `test_flow_state` негативы расширены (пробел, слэш, `_`, ведущий дефис), позитивы — `chore`/`add-widget`/`cleanup`. В `test_j431` проверка ужесточена до `status == "ALLOW"` и отсутствия `AMBIGUOUS_STATE`. В `test_j43` проверка перевернута честно: лог постфильтра не появляется, ALLOW сохранен. В `test_audit_ergonomics` вход заменен на действительно невалидный `my_small_fix`, подсказка проверяется. `test_substantive_error_not_filtered` по-прежнему валиден. Новый `test_m19` проверяет реальные ворота раннера. Тесты не ослаблены.
- Прогон: tests/test_flow_state.py, test_j431_flow_aware.py, test_j43_flow_enforcer.py, test_audit_ergonomics.py — 110 passed; test_package_runner.py -k m19 — 1 passed.

## Что не проверено

- Полный сьют не перезапускался (по данным оркестратора: 1105 passed, 2 skipped).
- Живой путь энфорсера в Hermes (pre_tool_call) и CI flow.yml на PR не проверялись.
- Режим `pm_bounds_check --sessions` разобран только статически по адаптеру, сам pm_bounds_check.py не читался. Работоспособность подтверждена тестом m19.
- Изменения в PLAN-flow4-chore-scope.md и в файле бэклога J64 не ревьюились: это артефакты ПМ, а не код.

## Повторная проверка (de8fee3fbb8ea08cdfa6e43efa3bccf49ac94fdc)

Вердикт: Одобрить

Предмет: `git diff e5ec197..HEAD`. Исправлены п.1 (`_plan_release` сверяет «Флоу: N» с флоу запроса), п.2 (`CHORE_RE` без IGNORECASE) и п.3 (тексты в flow_state/delegate_gate). Замечания 1–3 закрыты. Замечание 4 (тест на ужесточение Ф5 без постфильтра) остается minor и переносится в бэклог.

### Находки

| # | Серьезность | Файл:строка | Проблема | Сценарий отказа | Рекомендация |
|---|---|---|---|---|---|
| R1 | minor | scripts/flow_transition.py:369-391 | Цикл по кандидатам возвращает результат по первому существующему файлу. Если в корне лежит `PLAN-<id>.md` чужого флоу, он перекрывает легитимный `openspec/changes/<id>/PLAN.md` с «Флоу: 1». Для Ф2 так же: `PLAN-BUG-NNN.md` чужого флоу перекрывает общий `test-model/bugs/PLAN.md`. | Редкая коллизия имен (slug Ф4 = change-id Ф1) дает ложный DENY `PLAN_FLOW_UNDECLARED`. Это fail-closed, обхода нет. До правки этот файл тоже выигрывал, только без сверки N. | Перебирать все кандидаты: ALLOW, если хотя бы один объявляет нужный флоу; DENY с перечнем, если ни один. В бэклог. |
| R2 | minor | scripts/flow_transition.py:375 | Если в плане несколько строк «Флоу: N», учитывается их множество: план с «Флоу: 1» и «Флоу: 4» открывает ворота обоих флоу. Regex привязан к началу строки, поэтому упоминание в середине прозы не считается. | Двусмысленный план закрывает ворота двух флоу. Риск низкий: план пишет ПМ. | Допустимо. При желании — требовать ровно одно объявление. |

Блокеров и major нет.

### Проверено

- Ф1, план в `openspec/changes/<id>/PLAN.md` с «Флоу: 1» (корневого файла нет): кандидат найден, `1 ∈ declared` — проходит.
- Ф2, общий `test-model/bugs/PLAN.md` с «Флоу: 2» — проходит. Ф3 и Ф5 `_plan_release` не вызывают (таблица стадий: проверки строк 950/970 — Ф1, 1606 — Ф2, 1812 — Ф4), поэтому правка их не затрагивает.
- Несколько строк «Флоу:»: `PLAN_FLOW_RE` содержит одну группу, `findall` дает строки `1–5`, `int()` безопасен; семантика множества — см. R2.
- conftest-фикстура `PLAN-add-widget.md` («Флоу: 1») в тестах других флоу:
  - test_flow_transition (Ф2, scope `add-widget`): проверка ослаблена до `UNKNOWN|DENY`, но наличие `AMBIGUOUS_STATE` по-прежнему проверяется, то есть суть теста (неверный scope) сохранена. Ослабление честное.
  - test_j41: заголовки заменены на «Флоу: 1» под `create_change`, проверка жирного и обычного формата сохранена.
  - test_j431: новый тест проверяет, что план чужого флоу не открывает ворота Ф4.
- `CHORE_RE` без IGNORECASE: `Chore-X` и `BUG-001` для Ф4 дают FLOW_ID_INVALID (новый тест).
- Прогон: test_j41_plan_release, test_j431_flow_aware, test_flow_transition, test_flow_state — 156 passed.

### Не проверено

- Полный сьют не перезапускался (по данным оркестратора: 1107 passed).
- Реальные PLAN-файлы проектов (ekotov-wiki) не проверялись на расхождение «Флоу: N» с фактическим флоу. После правки такие планы начнут получать DENY: стоит прогнать по активным пакетам.
