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
