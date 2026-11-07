# Ревью test-zones (J66) — review-002

Ревьюер: code_reviewer (независимый сабагент, Claude Code)
Commit: 5dca86f9281ade1689f99d9ebd943831de5382b0 (ветка chore/test-zones; поверх 6748965, review-001 — return)
План: PLAN-test-zones.md (Флоу 4, раздел «Развилка из ревью review-001»); ТЗ и резолюция: backlog/J66-тестовые-зоны-unit-api-web-2026-11-06.md

Оба major из review-001 закрыты по факту кода. Сторож дерева J64.1 снова срабатывает при `pytest tests/`, потому что `tests/conftest.py` вернулся в корень. Этап `qa_automation` во Флоу 2–5 реально проходит `flowctl prepare`, это проверено на фикстуре. Новых blocker и major нет. Осталось три minor: одна новая находка и два хвоста review-001, которые записаны неполностью. Они не блокируют приемку.

## Сверка находок review-001

| # | Было | Статус | Факт |
|---|---|---|---|
| 1 | major: сторож дерева молча выключен | закрыт | `tests/unit/conftest.py` → `tests/conftest.py` (rename 99%), `FACTORY_ROOT = parent.parent`. TC-J66-010 проверяет `request.config._factory_tree_before` (хук sessionstart отработал) и отсутствие `tests/unit/conftest.py`. Подпроцесс-теста с утечкой нет, но атрибут, выставленный именно в sessionstart, — достаточный индикатор. Цена (корневой conftest фабрики в зоне qa_automation) явно записана в плане, п.8. |
| 2 | major: нет исполнителя приемочных тестов во Флоу 2–5 | закрыт | Решение Заказчика «Этап qa_automation» есть в плане. `STAGE_TABLE[2..5]`: этап `qa_automation` (роль qa_automation) стоит вторым, `check` — функция первого этапа. В `SEQUENCE_PREREQS` предшественник — первый этап. Практическую проверку см. в разделе «Проверено». |
| 3 | minor: регекс импортов, web без playwright | закрыт | `imported_top_modules` разбирает импорты через `ast`: `import a, b`, `as`, `from`, вложенные импорты, `importorskip`, `import_module`, `__import__`; текст в строках не считается импортом. `SyntaxError` дает находку (fail-closed). Проверку «web без playwright» сняли в плане с обоснованием (фикстура `page`). TC-J66-011. Одна новая мелочь — №1 ниже. |
| 4 | minor: контракт 6 считал unit | закрыт | `acceptance_files` отбрасывает `TEST_LAYOUT_NO_TC`. TC-J66-012 проверяет: только unit — OK, есть api без кейсов — «контракт 6». |
| 5 | minor: archive и TC в спеке | закрыт | qa-pipeline/spec.md «Трассировка автотестов» включает `tests/archive/`, что совпадает с `TEST_LAYOUT_NO_TC = ("unit",)`. |
| 6 | minor: factory_init — strict по расположению, дубль логики, e2e/ | закрыт (а, б), частично (в) | `misplaced_tests` = `flow_check.layout_findings`, то есть одна реализация, и стек тоже учитывается (TC-J66-006 `test_stack_violation_keeps_warn`, `fi._fc is fc`). Пункт (в) — см. №2 ниже. |
| 7 | minor: guard пака qa-automation пропускает test-layout.json | закрыт | `PI_ZONE_WRITE` в README пака: `…:test-model/bugs`, без голого `test-model`. |
| 8 | minor: ничьи пути зон | закрыт частично | `tests/__init__.py` и `tests/fixtures/**` отданы qa_automation (roles.json, agents/README.md, тест J65). `tests/*.md` (кроме README) по-прежнему ничьи, отказ нигде не записан. Зона миграции `e2e/**` не описана — см. №2. TC-J66-013 проверяет поведение `narrow_zones`. |
| 9 | minor: устаревшие тексты | закрыт | Все четыре места обновлены: flow-control SKILL.md (TC — только приемочные, unit освобожден), subagent-delegation.md (`tests/unit/test_smoke.py`), conveyor SKILL.md и qa_case_reviewer_agent.md (unit идут к code_reviewer). |
| 10 | minor: `[chore]` у 6748965 | не закрыт, приемлемо | `check_commit('6748965')` по-прежнему дает J3, `check_commit('5dca86f')` = []. История не переписывается (правило 7 AGENTS.md). Прецедент roles-registry/review-002 признан информационным. `pm_bounds_check` в CI не входит (flow.yml:43). ПМ на pre_merge — merge-коммит с `[pipeline]`/`[флоу 4]`. Бэклог фиксирует маркер для будущего перевода в strict. |
| 11 | minor: тесты по строкам, а не по поведению | закрыт | Добавлены TC-J66-013 (`narrow_zones`), TC-J66-014 (реальный коммит + `pbc.check_commit`: без маркера — нарушение, с `[pipeline]` — []), импорты `as`/`from`/вложенный каталог (`tests/unit/deep/er/`), TC-J66-010, TC-J66-015. |
| 12 | minor: regress не берет tests/unit | не закрыт, приемлемо | Записано в бэклоге как «Известное ограничение» с причиной (дедуп BUG-005 свернул бы прогон в полный `tests/`) и привязкой к J52. Дефект не новый. |

## Замечания

| # | Серьезность | Место | Сценарий | Рекомендация |
|---|---|---|---|---|
| 1 | minor (новое) | scripts/flow_check.py:396-401 (`imported_top_modules`, `ast.parse(text)`) | На Python 3.12+ `ast.parse` выдает `SyntaxWarning` на невалидные escape-последовательности (`"\d"` в обычной строке теста). Проверено: `imported_top_modules('import re\nx = "\\d+"')` печатает в stderr `<unknown>:2: SyntaxWarning: "\d" is an invalid escape sequence`. flow_check проекта начнет шуметь безымянными предупреждениями на каждом таком тесте в unit/integration/api. При `PYTHONWARNINGS=error` или `-W error` предупреждение становится `SyntaxError`, тест получает находку «не разбирается», и в strict это FLOW-ERROR на синтаксически корректном файле. Мелочь того же места: `pytest.importorskip(modname="requests")` (keyword) не ловится. | Оборачивать разбор в `warnings.catch_warnings(); warnings.simplefilter("ignore", SyntaxWarning)` и передавать `filename=str(rel)`. Keyword-форму можно учитывать через `node.keywords`, но это по желанию. |
| 2 | minor (хвост #6в/#8) | backlog/J66-…-2026-11-06.md «Открыто»; scripts/flow_check.py:768 (`tests_dir.rglob`) | Тесты вне `tests/` (корневой `e2e/` ekotov-wiki) не видят ни flow_check, ни factory_init. В бэклоге нет пометки, что `e2e/` вне `tests/` не проверяется даже в strict. После J66 зоны `e2e/**` нет ни у одной роли, поэтому PR миграции `e2e/` → `tests/web/e2e/` (`git mv` = удаление вне зоны) требует явной зоны в брифе ПМ, а это тоже не записано. `tests/*.md` кроме README тоже без владельца и без записи об отказе (ekotov-wiki `REPORT-*.md` упомянут отдельно). | Дописать в «Открыто» бэклога J66 две строки: «`e2e/` вне `tests/` не проверяется раскладкой до миграции» и «PR миграции — зона `e2e/**` + `tests/web/e2e/**` брифом ПМ (Флоу 4, перечень путей)». |
| 3 | minor (новое, документ) | contracts/flow_control_contract.md §«Флоу 2…5» (:148-168) | STAGE_TABLE и docs/README-flow-control.md описывают новый этап `qa_automation` во Флоу 2–5, а контракт о нем молчит. Противоречия нет: контракт Флоу 2 говорит «QA-контур по объему бага (решение ПМ)», спека deterministic-flow этапы флоу 2–5 не перечисляет. Но порядок «спека → контракт → промпты» здесь соблюден только через план и решение Заказчика. Контракт — защищенный путь. | Строкой в бэклог J66 (или ближайшим `[pipeline]`-коммитом): в контракте §7 Флоу 2–5 добавить «этап qa_automation (по необходимости) после первого этапа, вход — вход первого этапа». |

## Проверено

- **Этап qa_automation, практика** (фикстура как в `test_j431_flow_aware.py::TestFlow2PlanGate._bug_repo`: BUG-042 + спека + PLAN-BUG-042.md «Флоу: 2»; `flowctl prepare`, отдельный registry/state в scratchpad):
  - Ф2 `role=qa_automation action=qa_automation --path tests/api/**`, реальный (не dry) prepare: `prepared: True`, резервация создана;
  - Ф2 qa_automation с `--path tests/unit/**`: отказ зоны («вне зоны записи роли qa_automation»), то есть изоляция от unit работает;
  - Ф2 `role=dev action=qa_automation --path tests/api/**`: отказ зоны dev; `role=qa_automation action=bug_fix`: WRONG_ROLE;
  - Ф2 qa_automation без BUG-099 и плана: DENY `PLAN_RELEASE_MISSING` + `MISSING_INPUT` (вход первого этапа унаследован);
  - Ф5 qa_automation без `--small-change`: UNKNOWN; с ним — ALLOW (энфорсер для Ф5 всегда передает `--small-change`, prepare_command:1184);
  - Ф3 `S2-prod-down` с `--incident-ref`: ALLOW, `extra_gates` о последующем PR-цикле унаследованы (безвредно).
- **Переиспользованные check-функции**: `check_bug_fix`, `check_emergency_stabilize`, `check_chore_task`, `check_express_task` не смотрят ни на `actor_role`, ни на `requested_action`. Роль проверяется отдельно, в `check_action` (WRONG_ROLE), до `stage.check`. `check_chore_task` для qa_automation проверяет PROTECTED_PATHS и rules_change, то есть корректно строже. Override `next_candidates` у bug_fix при `spec_delta` для qa срабатывает так же, и это корректно: дельта спеки — эскалация независимо от роли.
- **Энфорсер**: `action_for_role("qa_automation", 2..5)` = `qa_automation` через fallback `ROLE_ACTIONS`. Для Ф3 полная карта ролей (TC-J48-020) не нарушена. `SEQUENCE_PREREQS`: qa_automation требует первый этап; code_review, accept_review и express_close от qa_automation не зависят, поэтому этап опционален и существующие цепочки не ломаются. Синхронизация со STAGE_TABLE — TC-J431-017. MODEL_ENFORCE (J60) qa_automation не касается: роль не из 5.3-набора. `package_runner.stage_action` для qa-automation во Флоу 2–5 теперь возвращает этап, а не None/ROLE_WITHOUT_STAGE, и стадия идет через prepare. Это ужесточение, оно и ожидалось.
- **flowctl**: `required_gates_for` — шлюз «flow_check (раскладка тестов J66)» не входит в `_STAGE_IMPLEMENTS_MACHINE_GATE`, поэтому добавочных машинных ворот нет. Это человеческая формулировка, flow_check и так в DEFAULT_GATES. `phase`/`next` перебирают STAGE_TABLE и лишь показывают qa_automation кандидатом.
- **factory_init → flow_check**: factory_init в проекты не копируется (нет в COPY_FILES и FLOW_CONTROL_FILES) и запускается из `scripts/` фабрики, поэтому sibling `flow_check` резолвится. Побочных эффектов при импорте у flow_check нет (`__main__`-guard на :879; `factory_paths` — try/except fallback). TC-BUG-026-001/002 зеленые: flow_check не получил новых фабричных импортов (только stdlib `ast`, импорт внутри функции).
- **Прогоны**: `pytest tests/unit/{test_j66_test_layout,test_j431_flow_aware,test_bug026_init_imports,test_j48_incident_protocol,test_flowctl,test_j43_flow_enforcer,test_j60_model_enforce,test_package_runner}.py` → 308 passed. `pm_bounds_check.check_commit`: 6748965 — J3 (известно, #10), 5dca86f — [].

## Не проверено

- Полный сьют (по данным ПМ — 1300 passed), CI на GitHub.
- Энфорсер end-to-end через хук Hermes (`pre_tool_call` с заголовком `flow=2 role=qa_automation`); проверены `action_for_role`, `prepare_command` и сам `flowctl prepare`.
- Проекты (child_bot, ekotov-wiki, auto-school) и `factory_init --force` на них.

## Вердикт: approve
