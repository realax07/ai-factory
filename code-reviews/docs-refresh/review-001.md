Вердикт: Вернуть

# Ревью docs-refresh — итерация 001

- Объект: ветка `docs/refresh-2026-11`, коммит `86dfb70fcaafd658e3bb7402bd4afb7ecdaea3e0` (17 файлов, +258/−53), план `PLAN-docs-refresh.md`.
- Ревьюер: независимый сабагент (роль code_reviewer, дифф — документация). Автор диффа — ПМ-сессия; ревьюер его не писал.
- Метод: каждое новое или измененное фактическое утверждение сверено с исходниками, CI, `gh pr list` и (для проектов) GitHub API. Для `factory_init` поведение проверено запуском во временном git-репо (scratchpad, HOME подменен, `--skip-plugin --skip-crons`).

## Замечания

| # | Серьезность | Файл:строка | Что неверно | Как на самом деле | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | AGENTS.md:122 (новый текст); README.md:118 (старый текст, план объявил README актуализированным) | «проектный `flow.yml` при повторной установке не перезаписывается»; в README — «НЕ перезаписывается (включая --force)». В AGENTS.md это стоит сразу после «`--force` — синхронизация», и читается как исключение для flow.yml при `--force`. | `scripts/factory_init.py:310`: `.github/workflows/flow.yml` входит в `COPY_FILES`. Цикл копирования (`factory_init.py:496–504`) пропускает существующий файл только без `--force`, отдельного случая для flow.yml нет. Запуск: ставлю, пишу в `flow.yml` свой текст, запускаю с `--force`, и файл заменяется эталоном (первая строка снова `name: flow`). Без `--force` не перезаписывается никакой файл, так что flow.yml ничем не выделен. | Исправить оба места. Например: «без `--force` существующие файлы, включая `flow.yml`, не трогаются; `--force` перезаписывает и `flow.yml`, required-checks и триггеры проекта после него сверить вручную (J52-mirror-guard)». Есть и другой путь: сделать исключение в коде, но это отдельная задача, не docs. |
| 2 | major | PLAN.md:22–24; README.md:114 (список `FLOW_CONTROL_FILES`); README.md:220; AGENTS.md:147; docs/guarantees.md (строка «scope маркера и движка — одна грамматика») | BUG-026 (#225) записан в «Сделано»; `flow_ids` перечислен в `FLOW_CONTROL_FILES`; AGENTS.md пишет, что `factory_init` кладет копии ядра «и их зависимости flow_ids…» в проект. | PR #225 «[BUG-026] factory_init: flow_ids.py в FLOW_CONTROL_FILES» сейчас в состоянии **OPEN** (`gh pr list`). На этой ветке `FLOW_CONTROL_FILES` (`factory_init.py:315–325`) не содержит `flow_ids.py`. Проверка установкой: `scripts/flow_ids.py` в проект не попадает, а скопированный `flow_state.py:41` делает `import flow_ids`, так что копии ядра в проекте сломаны, пока #225 не влит. | Варианты: (а) влить этот PR строго после #225 и указать это условие в описании PR; (б) до влития #225 перенести BUG-026 в «Открыто / в PR #225», а в README и AGENTS.md пометить flow_ids «(с BUG-026, #225)». |
| 3 | minor | AGENTS.md:147; README.md:114 | AGENTS.md: «…и их зависимости flow_ids, role_zone_policy, factory_paths — `factory_init` кладет их копии… (`FLOW_CONTROL_FILES`)». | `factory_paths.py` лежит в `COPY_FILES` (`factory_init.py:290`), а не в `FLOW_CONTROL_FILES`. README здесь прав: factory_paths у него в `COPY_FILES`. | Писать «(`COPY_FILES` + `FLOW_CONTROL_FILES`)» или убрать factory_paths из перечня зависимостей ядра. |
| 4 | minor | AGENTS.md:99 | «Хук перехватывает только `delegate_task` Hermes». | `enforcer.py:1367–1372`: кроме `delegate_task` хук перехватывает `bash` (`PUSH_TOOLS`) ради `push_gate` (J42 L4). На это ссылается и правило 4 того же AGENTS.md («L4 enforcer push_gate»), так что внутри файла получается противоречие. | «Делегации хук валидирует только для `delegate_task` Hermes (плюс push_gate на bash `git push`, J42)». |
| 5 | minor | README.md:381 | ekotov-wiki: «монорепо `services/{app,frontend,search,backup,images,auth}`». | В `realax07/ekotov-wiki@main` каталоги `services/`: app, backup, frontend, images, search, **video**, **weather**; каталога `auth` нет. В `deploy/compose.yaml` сервисы app, search, images, video, weather, backup, netdata, nginx. «20 change-пакетов в архиве» подтверждено (20 каталогов). | Поправить состав на фактический (без auth, плюс video и weather) или написать без перечня. «7 контейнеров» прода сверить с VPS: compose дает 8 сервисов. |
| 6 | minor | README.md:232 | «ретроспективный артефакт… обязателен к закрытию `express_close` — без него `FLOW5_RETRO_MISSING`». | `FLOW5_RETRO_MISSING` выставляет снимок `flow_state.check_flow_identifier` (`flow_state.py:833–846`) на любом prepare Флоу 5, где нет `requirements.md`, а не только на закрытии. Сам `check_express_close` (`flow_transition.py:1852`) отдает `MISSING_INPUT` и требует три вещи: утвержденные requirements, spec-дельту и кейсы. | Например: «до закрытия `express_close` обязательны ретро-requirements (утверждены), spec-дельта и кейсы (`MISSING_INPUT`); пока нет `requirements.md`, снимок помечает scope `FLOW5_RETRO_MISSING`». |
| 7 | minor | AGENTS.md:38 (не правилось) против AGENTS.md:113 (правилось) | После правки п. 1 «Как гарантируется детерминизм» («чеклист упразднен, J23», кейсы трассируются к спеке) правило 6 по-прежнему требует «CHK-N → Requirement; TC-N → CHK-N». | `flow_check.py:568–620`: этап чеклиста упразднен, TC трассируется к `### Requirement:`/`#### Scenario:`. | Правило 6 по решению Заказчика («только фактические правки, без смены правил») правке, видимо, не подлежит. Тогда стоит внести расхождение в `PLAN-docs-refresh.md` (раздел расхождений) или в J64.15/J65.11, чтобы противоречие было учтено, а не забыто. |

Nit (на усмотрение автора, на вердикт не влияет):
- `docs/README-flow-control.md`, раздел «Пакетный раннер»: в «роль без этапа во флоу (ba, regress-runner, devops)» в коде стоит оговорка «devops **вне Ф3**» (`package_runner.py:796–797`).
- `agents/README.md`, вводная: «остальные — glm-5.3-flash» не упоминает аудитора (Kimi K3.1). Аудитор вне конвейера, поэтому допустимо.
- `AGENTS.md:122`: `check_mirrors.py` по умолчанию сверяет 4 файла (flow_check, pr_validate, impact_rules.json, factory_paths; `DEFAULT_FILES`), а не все копии. Формулировка «сверка копий с фабрикой» шире фактического поведения.

## Проверено (утверждения подтверждены кодом)

- Python ≥ 3.10: `factory_bootstrap.py:12,67` (проверка `< 3.10`). CI — `python-version: "3.12"` (`flow.yml:20,66`). Все `scripts/*.py` и `plugins/flow-enforcer/*.py` разбираются `ast.parse(feature_version=(3,10))`, синтаксиса только из 3.11+ (tomllib, `datetime.UTC`, `except*`) нет.
- OpenSpec: `npm install -g @fission-ai/openspec@1.14.0` (`flow.yml:58`). pytest ставится в CI, его наличие проверяет bootstrap.
- Bootstrap: кроны `*/2` (session_watchdog) и `*/5` (delegate_watchdog), полный `pytest tests/` (`factory_bootstrap.py:102,114,126`).
- Пакет Pi `@earendil-works/pi-coding-agent` и pi.dev совпадают с `role-packs/README.md:3`. Паков 15: 14 ролей и auditor. Модели: sa/architect/dev/ba — glm-5.3, остальные — glm-5.3-flash, auditor — kimi k3.1-pro. Ключи лежат в `~/.pi/agent/models.json`.
- Коды STOP раннера: DENY/UNKNOWN из prepare, `ZONE_OUTSIDE_POLICY` (`package_runner.py:995`), `ZONE_CONFLICT` из reserve, `OUT_OF_ZONE` из finish/session_check, повторная сверка зоны перед коммитом (`zone_recheck`, учитывает committed и uncommitted, то есть и запись через bash), ненулевой gate. `ROLE_WITHOUT_STAGE` — это WARNING, не STOP, и в доках он описан верно, как резервация по политике. Вызов `package_runner.py <PLAN-файл> [--dry-run]` (`:115`). State/resume (`<план>.runner-state.json`), коммит стадии `commit_stage`, закрытие `gate_close`. Вердикт проверяется подстрокой `contains` (`:556`).
- MODEL_ENFORCE (`enforcer.py:747–830`): `[hermes:<5.3-роль>]` на боевом этапе дает block с подсказкой про pi роль-пак, `[pi:…]` пропускается, без маркера пишется WARN, guard `flow=[245]` гасит правило. `FLOW_MODEL_ENFORCE` по умолчанию включен, выключается значениями 0/false/no/off. Дата реализации 2026-11-01 (`38e9bf4`, PR #205).
- Грамматика scope (`flow_ids.py`), проверена CLI: Ф1 `nodash` отклоняется, `S1-x` и легаси `BUG-001` для Ф3 движок принимает, энфорсер требует severity (legacy=False). Ф4 `chore`/`my-pkg`, Ф5 `slug`, Ф2 `BUG-AF-RECHECK-001`/`BUG-001-slug` проходят. Fallback-копия и источник `flow_ids|fallback` в энфорсере (`enforcer.py:155–182`).
- Флоу 5: этапы `express_task`/`express_close` (`flow_transition.py:1999–2002`), план релиза не обязателен. Формулировка неточна, см. замечание 6.
- `COPY_FILES` в README.md:114 поэлементно совпадает с `factory_init.py:289–311` (скрипты и impact_rules.json). `SKILL_DIRS` — 12. `check_mirrors` работает только на машине фабрики (`factory_init.py:327–329`).
- `flow_check.py` — 751 строка (README: «~750»). Проверки кейсов new/ («1 кейс = 1 файл», трассировка к спеке, без чеклиста) — `flow_check.py:568–620`, AGENTS.md п. 1 им соответствует.
- J42: триггер CI `pipeline/**` и push gate (`flow.yml:5,112–113`), `push_gate` в энфорсере.
- `factory_paths`: env `HERMES_HOME`/`AF_STATE_DIR`/`AI_FACTORY_HOME`/`AF_PROJECTS_ROOT`/`PI_AGENT_DIR`, `--doctor LABEL`/`--compare`. `ci_local`: клон глубины 1, пустой HOME, без `GITHUB_*`/`GIT_*`, openspec не запускается.
- Номера PR в PLAN.md: #214, #216–#219, #220, #221, #222, #223, #224 влиты (даты 2026-11-02…05) и по смыслу совпадают с описанием. #225 открыт (замечание 2).
- Ссылочные цели существуют: `docs/guides/pipeline-manifest.md`, `skills/README.md`, `openspec/changes/archive/2026-10-29-add-deterministic-flow/`, `archive/docs/e12-speckit-spike.md`.
- Таблица зон в `agents/README.md` не тронута: дифф — только +2 строки вводной в начале файла. Отпечаток проверен полным сьютом ПМ.
- PLAN.md: журнал делегаций (`## Журнал делегаций (D1)`, строки 78–152) не изменен. В «Решениях» и «Релизах после Р2» исходный текст сохранен, добавлены только уточнения в скобках и дата. Append-only не нарушен.
- AGENTS.md: структура разделов сохранена, правила не менялись. Добавлены пункт 7 (раннер) и описание MODEL_ENFORCE — это описание существующего кода, не новые правила. Решение «только фактические правки» соблюдено, если не считать неверного факта из замечания 1.
- Промпты `agents/*_agent.md` в диффе отсутствуют («Не трогать промпты» соблюдено).
- Не осталось утверждений из таблицы плана, которые объявлены исправленными: «990», «777», «405», `@openspec/cli`, `docs/e12`, «3.11», «Трехканальный», «кандидат Флоу 4», `incident-id`, `chore-slug` в живых доках не найдены. Исключение — flow.yml в README.md:118 (замечание 1).

## Не проверено

- Полный сьют, `flow_check` и ссылки: данные ПМ (1225 passed, 2 skipped; flow_check OK; битых ссылок нет). Повторно не прогонял, по брифу.
- `openspec validate --all --strict` локально не запускал (дифф не трогает `openspec/`).
- Фактическое состояние проектов child_bot («пакет 1 реализован, 13 настроек») и auto-school: проверено только, что репозитории существуют, в child_bot есть `add-core-diary`, а в auto-school — `incidents.md`. Число контейнеров прода ekotov-wiki-par не проверено (нужен VPS).
- Совместимость с Python 3.10 проверена только на уровне грамматики (интерпретатора 3.10 на машине нет), рантайм-API не проверялся.
- Модели и провайдеры на VPS (`~/.pi/agent/models.json`) и установленная копия энфорсера не проверены.

## Исправления по возврату (ПМ)

- **Major 1** `flow.yml` и `--force`: подтверждено по коду (`factory_init.py:310`, особого случая нет). README и AGENTS.md: без `--force` существующие файлы не трогаются, с `--force` перезаписываются все копируемые, включая `flow.yml`, — после этого сверить required-checks и триггеры. Неверная формулировка README была старше этого пакета.
- **Major 2** BUG-026 / `flow_ids` в списке копирования: в план добавлен раздел «Порядок мержа» — PR документации вливается строго после #225; в PR это указано.
- №3: `factory_paths` — в `COPY_FILES` (AGENTS.md).
- №4: хук смотрит `bash` ради push_gate — оговорено (AGENTS.md).
- №5: сервисы ekotov-wiki — `app, backup, frontend, images, search, video, weather` (по `services/` репозитория); число контейнеров помечено «по README проекта».
- №6: Флоу 5 в README — `FLOW5_RETRO_MISSING` на любом prepare без `requirements.md`, `express_close` требует requirements, спека-дельту и кейсы (`MISSING_INPUT`).
- №7: расхождение правила 6 AGENTS.md (CHK) внесено в список расхождений плана; правило не правилось (решение Заказчика).
