# Review 001: docs-refresh

> Ревью пакета chore/docs-refresh (2026-11-14). Ревьюер дописал его к code-reviews/docs-refresh/review-001.md (путь занят ревью #226); до коммита ПМ перенес текст сюда без правок, прежний файл не тронут.

- Commit: `a6e3b62` (ветка `chore/docs-refresh`, база `origin/main` `f52c257`), 11 файлов, +182/−101.
- Ревьюер: независимый сабагент (роль code_reviewer, только статика диффа и чтение кода); автор диффа — ПМ-сессия.
- Метод: каждое новое или измененное утверждение сверено с `scripts/` (package_runner, executors/, executor_watchdog, pr_validate, pm_bounds_check, ruleset_check, flowctl, gates_stats), `skills/pm-factory/pi/zone-guard.ts`, `agents/roles.json`, `.github/workflows/flow.yml`, `tests/`, журналами backlog/J64, J65, J66 и текущим AGENTS.md.

## Прогоны

- `pytest --collect-only -q tests/`: 1433 tests collected. «1400+» верно.
- `pytest tests/unit/test_j65_pack_zone_docs.py test_j65_agents_core.py test_j65_roles_registry.py test_j65_executor_adapter.py`: 29 passed.
- `python3 scripts/gen_role_docs.py --check`: таблицы актуальны.
- `python3 scripts/flow_check.py .`: OK.
- `python3 scripts/ruleset_check.py` (боевой ruleset): OK — active, bypass никому, PR-only, required `test-flow-control`, `flow`.
- `openspec validate --all --strict`: SKIPPED, в среде ревьюера нет openspec CLI. Дифф openspec/ не трогает.
- Битые относительные ссылки в измененных .md: не найдено. Пути в backticks, которых нет в фабрике, — пути проектов (`tests/api`, `docs/glossary.md`…), это ожидаемо.

## Подтверждено кодом

- Коды: `ZONE_GUARD_MISSING` (executors/pi.py:20,38), `EXECUTOR_UNAVAILABLE` (executors/stub.py:29, только у stub), `MODEL_UNRESOLVED` (package_runner.py:169, `role_model` — без дефолтов), `executor_runs.jsonl` (package_runner.py:170, executor_watchdog.py:34), BYPASS `proc:<исполнитель>:<pid>` (executor_watchdog.py:143,170; зовется из delegate_watchdog.py:204), `--no-extensions -e <guard репо>` (executors/pi.py:55).
- zone-guard: `git push` запрещен всем, docker-мутации — только devops (zone-guard.ts:28-29,55,284-290).
- per_task: только агентная стадия dev; с `review:` — пары, чекбокс ставит раннер после approve (package_runner.py:513-531,854-895,2196); без `review:` и с зависимостями — STOP.
- J65.4b: штамп Reviewer-Delegation (package_runner.py:653-680), `runner_review_ok` в pr_validate.py:191-195,323.
- pm_bounds_check: повтор пары только среди незавершенных (`FINISHED_STATUSES`, pm_bounds_check.py:149,169).
- Required checks `flow` и `test-flow-control`: ruleset_check.py:32 и живой ruleset.
- auditor `kimi`/`k3.1-pro` (roles.json; TC-J65-EXE-004 сверяет паки с реестром, кроме auditor). Исполнители pi/stub/hermes (hermes — manual).
- factory.lock в CI проекта: flow.yml:53-90. Скрипты из таблиц README существуют.
- Статусы MAP/PLAN совпадают с резолюциями журналов: J64 — открыты только J64.8 и J64.9 (репетиция); J65 — открыты 6, 7 (проекты), 10 (реальные исполнители), 8 закрыт без реализации; J66 — открыта миграция проектов.
- Номера правил в измененных строках совпадают с ядром: п.10 — параллель, п.11 — worktree, п.17 — раннер, п.13 — флоу в плане, п.4 — push, п.6 — трассировка.

## Замечания

| # | Серьезность | Файл:строка | Что неверно | Как в коде | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | README.md:347, README.md:366 | «Ручной запуск исполнителя мимо раннера… виден вотчдогу как BYPASS» и «…видны за ~5 минут» сказано без оговорок. | executor_watchdog работает только внутри прогона delegate_watchdog. Крон `delegate-watchdog` по docs/README-flow-control.md:280 и guarantees.md:56 «на паузе / включается ПМ после проверки». guarantees.md:37 оговорку дает («действует, когда включен крон delegate-watchdog»), README — нет. Гарантия завышена. | Добавить в обе строки «когда включен крон delegate-watchdog (сейчас на паузе)», как в guarantees.md:37. |
| 2 | major | README.md:375-377 (и формулировки в docs/ci-gates.md, docs/guarantees.md «эталонный прогон Флоу 1») | «фиктивный проект проходит Флоу 1 через раннер… поломка любого звена краснит CI». | Эталон покрывает sa → architect → dev по задачам с парным ревью → gate → merge. QA-контура нет: pr_validate в тесте отказывает ровно на QA (tests/fixtures/reference-run/README.md, test_j65_reference_run.py:55-59; J65 резолюция 2026-11-11, кандидат J65.10b). Поломка QA-стадий, regress или integrate CI не краснит. | «Флоу 1 до QA-контура (sa → architect → dev+ревью → gate)»; «любого звена» заменить на «любого из этих звеньев». |
| 3 | major | docs/guides/pipeline-manifest.md:66-67 (вне диффа, п.5 задачи) | «Провайдер/модель берутся из `settings.example.json` пака (дефолт `zai-glm`/`glm-5.3`)». | package_runner.py:1055-1068 `role_model`: стадия `provider`/`model` → поля roles.json, иначе STOP MODEL_UNRESOLVED; settings.example.json раннер не читает. Строка противоречит тому же гайду (строки 40-43). | Удалить фразу или заменить ссылкой на абзац выше. |
| 4 | minor | README.md:16, docs/process-context.md:21, PLAN.md:33 | «Claude Code и Codex — следующими». | Журналы называют другое: J65 резолюция 2026-11-12 «Открыто: claude-code и qwen — следующим пакетом»; ТЗ J65.5 — `claude-code`, `qwen-coder`; archive/plans/PLAN-executor-adapter.md:10. Решения Заказчика про Codex в decisions/ и backlog/ нет (правило 18). | Привести к журналу («claude-code и qwen») или зафиксировать новое решение в backlog/J65 и сослаться на него. |
| 5 | minor | README.md:53 | «модуль… через который раннер запускает агента стадии (`pi`, `stub`, `hermes`)». | hermes — `manual = True` (executors/hermes.py:27): раннер процесс не запускает, это стоп-точка ПМ. | «(`pi`, `stub`; `hermes` — стоп-точка ПМ)». |
| 6 | minor | README.md:266-267; README-flow-control «`stub:` — заглушка эталонного прогона» | Сказано, что эталонный прогон идет на `stub:`. | Основной эталон идет на `pi:` с подменным `bin/pi` в PATH (fixtures/reference-run/project/PLAN-add-greeting.md:17-34). `stub:` — его повтор в TC-J65-EXE-008. tests/README.md формулирует верно. | «`stub:` — исполнитель-команда из env (повтор эталона, TC-J65-EXE-008)». |
| 7 | minor | docs/guarantees.md:46 (измененная строка) | «см. Слой 4». | В guarantees.md нет «Слоя 4»: есть слои 1, 2, 2a, 3. Ссылка висит, хотя строка правилась. | Указать «Слой 3» или убрать отсылку. |
| 8 | minor | docs/guarantees.md:69 при шапке ревизии «номера правил — по ядру AGENTS.md 2026-11-13» | «Отчет сабагента достоверен… (правило 1 + F3)». | Текущий п.1 — «работай при валидном входе». О достоверности отчета говорят п.9 и раздел «Приемка» (проверка заявленного по файлам). Шапка обещает сверку номеров, а эта строка не сверена. | Сослаться на «Оркестрация (ПМ): приемка — заявленное в отчете проверено по файлам». |
| 9 | minor | docs/guarantees.md:56 (слой 2a, строка delegate-watchdog) | Граница: «до включения обход делегаций не детектируется». | С J65.5 тот же крон ведет executor_watchdog, поэтому до включения не детектируется и ручной запуск исполнителей. | Дописать «и ручной запуск исполнителей (executor_watchdog)». |
| 10 | minor | backlog/MAP.md:88 (J66), PLAN.md:36 | «миграция проектов — Заказчик с агентами фабрики». | Артефакта решения нет: в журнале J66 последняя запись «Открыто: миграция проектов отдельными PR», в decisions/ ничего (правило 18). | Дописать резолюцию в backlog/J66 со ссылкой на решение или писать «открыто». |
| 11 | minor | docs/guides/pipeline-manifest.md:244 (вне диффа) | «Правило 11 и J31: одна задача tasks.md — одна dev-сессия». | В ядре это п.10, а п.11 — worktree. | Заменить на «Правило 10». |
| 12 | minor | agents/README.md:5 (вне диффа, не промпт роли) | «стадии `pi:<роль>`… пак переносит промпт на модель своего яруса». | Стадия — `<исполнитель>:<роль>`, модель берется из roles.json (J65.5). | Синхронизировать с README.md:266-270. |
| 13 | minor | skills/pm-factory/pi/role-packs/{devops,qa-case-reviewer,…}/README.md («zone-guard НЕ входит в пак: используется установленный `~/.pi/agent/extensions/zone-guard.ts`»), вне диффа | Читается как общий механизм. | На стадии раннера `--no-extensions -e <репо>/zone-guard.ts`; копия в `~/.pi` — только для ручных запусков (role-packs/README.md:14 уже говорит это верно). | Уточнить: «для ручного запуска; раннер берет guard из репо фабрики (J64.10)». |
| 14 | minor | docs/guarantees.md (строка ruleset) | «Права на bypass не выданы (проверено 2026-10-09)». | Сегодня ruleset_check: OK, bypass никому. | Обновить дату проверки на 2026-11-14 (ruleset_check). |

Blocker нет. Major 1–2 — завышенные гарантии в измененном тексте. Major 3 — устаревшее описание поведения раннера в гайде, вне диффа, но в объеме п.5 задачи.

## Вердикт: return
