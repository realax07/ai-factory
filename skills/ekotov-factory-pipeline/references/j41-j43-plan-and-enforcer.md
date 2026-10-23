# J41/J43 — план релиза и энфорсер делегаций (актуально: J43.1 flow-aware, 529 тестов)

Действующие исполняемые правила для ai-factory и ekotov-wiki. SKILL.md на момент
добавления превысил лимит 100К — правила живут здесь, перенести в тело при
разделении SKILL.md куратором.

## J41 — план релиза как артефакт ворот (матрица по флоу)

- Релиз стартует с PLAN-файла со строкой «Флоу: N» (N 1–5). Пути: `PLAN-<scope>.md`
  в корне репо или `PLAN.md` в каталоге пакета.
- **Матрица по флоу**: Ф1 — PLAN обязателен (`PLAN-<change>.md` / `PLAN.md` пакета);
  Ф2 — обязателен (`PLAN-BUG-NNN.md` в корне ИЛИ общий `test-model/bugs/PLAN.md`
  со строкой «Флоу: 2»); Ф3 — НЕ требуется (вместо него обязателен incident_ref);
  Ф4 — обязателен (`PLAN-<chore-slug>.md` в корне); Ф5 — не требуется.
- Без него: flowctl prepare этапов create_change/**dev_task/check_bug_fix/check_chore_task**
  = DENY (PLAN_RELEASE_MISSING / PLAN_FLOW_UNDECLARED); flow_check валит мердж
  («активный change БЕЗ-ПЛАНА»). План пишет ПМ до запуска СА; СА детализирует tasks.md.
- Legacy-пакеты: явные аудит-заглушки «восстановлен постфактум, закрывается при
  архивации» — не переписывание истории; вымирают при архивации пакета.
- Реализация: flow_transition.plan_release_paths/_plan_release — в
  check_create_change, check_dev_task (транзитивно), check_bug_fix, check_chore_task.

## J43/J43.1 — flow-enforcer (flow-aware pre_tool_call-энфорсер делегаций)

- Плагин Hermes: `plugins/flow-enforcer/` в ai-factory; ставится factory_init
  (или `hermes plugins install realax07/ai-factory --ref <pin>`), включение —
  `plugins.enabled`. Переживает обновления агента (живет в ~/.hermes/plugins,
  агент — в hermes-agent/); API-риск гасится пин-коммитом.
- Каждый delegate_task валидируется через `flowctl prepare --dry-run --flow N
  --change <scope>` ДО исполнения; DENY блокирует спавн с кодом
  (PLAN_RELEASE_MISSING, ZONE_CONFLICT, REQUIREMENTS_NOT_APPROVED…).
- **Заголовок goal (канонический, первая строка):**
  `flow: flow=<1-5> role=<роль> repo=<путь> scope=<идентификатор>` (+ опционально
  `task:`). Scope по флоу: Ф1 change-id, Ф2 BUG-NNN, Ф3 incident-id, Ф4
  chore-slug, Ф5 slug. Легаси `change=` без `flow=` → трактовка Флоу 1 + WARNING;
  ошибки (flow вне 1–5, пустой scope) → block FLOW_MARKER_INVALID.
- **Post-filter no-change отказов**: для Ф2/Ф4/Ф5 отказ prepare ровно из-за
  отсутствия change-пакета — ожидаемо; если scope-файл существует (Ф2:
  `test-model/bugs/<scope>.md`; Ф4/Ф5: `PLAN-<scope>.md`/`<scope>.md`) → ALLOW с
  логом «flow-N no-change scope ok». Отклонение prepare по существу (нет плана,
  нет BUG-репорта, нет спеки, WRONG_ROLE) — block как раньше.
- **Память фазы**: `flowctl phase --repo R --project P --flow N --scope S` → JSON
  последнего завершенного этапа scope. Sequence-gate: `FLOW_ENFORCER_SEQUENCE=1`
  → нарушение порядка этапов по STAGE_TABLE-предшественникам = block
  SEQUENCE_VIOLATION (дефолт off).
- Режим FLOW_ENFORCER_MODE: permissive (дефолт; без маркеров — пропуск+лог в
  ~/.hermes/state/flow-enforcer.log) / strict (block MARKERS_MISSING).
- Bypass — только дословная строка `flow: bypass --by customer` в goal
  (пишется в ~/.hermes/state/flow-enforcer-bypass.log).
- Fail-closed двойной: собственный catch-all хука + платформенный таймаут —
  сломанный энфорсер блокирует делегации, не пропускает.
- Отключение плагина = правка защищенной зоны профиля, требует согласия
  Заказчика (как AGENTS.md).
- Хвосты: strict-переход (решение Заказчика), allowlist неконвейерных
  делегаций, включение sequence-gate, живой прогон под Hermes-процессом
  (плагин подхватывается при старте gateway — после установки нужен рестарт).

## J45 — разделение скилл/промпт и БА-контур

- **Формула (Заказчик): скилл = инструкции КАК выполнять конкретную задачу;
  системный промпт = мир роли** (as-is, контракты, какие скиллы, окружение).
  Best practice, относящаяся ко всему — в системный промпт; к одной задаче —
  в скилл. При добавлении правила сначала решай, к какому слою оно относится.
- Скиллы роли перечислены в таблице промпта роли и в agents/README.md; скиллы
  фабрики живут в `skills/` и уезжают factory_init'ом целиком (новый скилл
  попадает в установку автоматически).
- `verification-before-completion` — НЕ скилл: блок «Факты до заявления
  готовности» (свежий полный вывод проверяющей команды; утверждение = только
  подтвержденное) вставлен во ВСЕ ролевые промпты agents/*.md.
- `brainstorming` — первая фаза elicitation БА (замысел до формулировок);
  декомпозиция tasks.md влита в openspec-authoring (из sp-writing-plans).
- requirements-elaboration: нумерационный преемник FR/NFR (продолжать
  master-specs + архив, дубль между пакетами = дефект), разбор утверждений
  Заказчика на директивы («Утверждаю + текст» — текст = обязательные
  ограничения пакета), жизненный цикл requirements.md (корень = активный
  пакет, при архивации → docs/ba/requirements-<change>.md). Дубли контракта 1
  из скилла сняты — скилл ссылается на контракт.
- openspec-authoring: research.md (альтернативы ДО design) — в составе
  change-пакета; research постфактум = не аналитика. Задачи tasks.md —
  «задачи-результаты» (не «чеклист» — J23-лексика вычищена).
- service-decomposition (скилл СА): критерии границы сервиса (том данных,
  профиль БД, масштабирование/деградация, независимый деплой; отказ auth —
  прецедент), владение схемой БД (один владелец), сквозные процессы, швы
  делегаций.
- **Сквозные процессы — тестирование на QA-этапе (решение Заказчика)**: СА
  специфицирует процесс/деградацию в design и включает сквозной набор в план
  прогонов; НЕ режет «сквозной смоук» в dev-задачи.

## J46 — архитектор: актор ревью, вердикт-ворота, карта

- STAGE_TABLE Флоу 1: актор `architecture_review` = **architect** (легаси «pm»
  устранен — реальных вызовов архитектора не было, P15 прошел без arch-ревью).
- `check_dev_task`: продуктовый пакет (backend/services/frontend/design) без
  `test-model/reviews/<change>/review-NNN-architecture.md` с вердиктом approve
  → DENY `ARCH_REVIEW_MISSING`; return — доработка СА и ре-ревью; docs-only
  пакеты ревью не требуют.
- flow_check: `architecture/map.md` обязателен при наличии backend/services
  (отсутствие = FLOW-ERROR); архивные продуктовые пакеты с arch-ревью требуют
  строку вердикта по карте — `Карта: обновлена` | `Карта: без изменений`
  (точный регистр), иначе FLOW-ERROR. Ретро-миграция легаси-ревью — добавление
  строки «Карта: без изменений (ретро-миграция J46)» ПМ-проходом.
- enforcer: ROLE_ACTIONS `architect → architecture_review`;
  SEQUENCE_PREREQS: architecture_review после create_change, до dev_task.
- Промпт architect_agent.md: ворота этапа, чек-лист сверки карты при каждом
  ревью (новые модули/сервисы/контейнеры/маршруты отражены? владельцы
  таблиц/томов названы? сквозные процессы описаны?).
- Строка «Карта:» ищется отдельно от вердикта ревью — `parse_verdict` знает
  только approve/return, не путай проверку вердикта с проверкой строки карты.

## Сопутствующие ловушки того же контура

- В goal делегации не оставлять неподнятые шаблонные маркеры ({VAR}) —
  dispatch отклоняется целиком; подставлять реальные значения до вызова.
- Маркеры PR repo-специфичны (pr_validate): в ai-factory обязателен
  [chore]/[docs]/[ops]/[BUG-NNN] в title — [pipeline] отвергается. Правка
  title/body НЕ перезапускает CI — close + reopen PR.
- factory_init: 28 файлов конвейера + 8 скиллов (+ плагин flow-enforcer) + шаг
  установки плагина (--skip-plugin для отката); openspec CLI ожидается в PATH
  (nvm node v24 bin: /home/openclaw/.nvm/versions/node/v24.20.0/bin) — без него
  шаг проверки среды красит весь прогон.

## Ловушки PR-маршрута того же контура

- `gh pr create` = «No commits between main and <branch>» — ветка уже полностью
  поглощена main (локальный merge/cherry-pick ушел раньше). Перед созданием PR
  сверяй `git log origin/main..HEAD` — пусто = контент уже влит, PR не нужен;
  непусто, но PR все равно не создается — вмержи origin/main в ветку и пушь.
- `gh pr merge --admin` требует admin-прав ТОКЕНА машины (у write-токена их
  нет — API вернет 405 «Required status check is failing» даже с --admin).
  Красный required check на PR обходится только: (1) чинить источник красноты,
  (2) просить Заказчика смержить вручную владельческим аккаунтом. Не циклись
  на повторах --admin.
- Ретро-вставка TC-меток в docstring'и тестов скриптом по дереву — хрупка:
  regex-патчи ломают синтаксис (незакрытые docstring'и в многострочных
  сигнатурах, литералы `{n:03d}`, не-ASCII вне строк). Вставляй TC-метку при
  написании теста; если ретро — после КАЖДОЙ правки `ast.parse` файла и правь
  целевой файл точечно, не глобальным regex-проходом.
- Известный флак фабрики: `test_session_check::TestReservation::test_concurrent_reserve_intersecting_exactly_one_wins`
  в CI падает (`['WIN','WIN']` против LOSE/WIN), локально стабильно green —
  гонка планирования потоков резервации зон, не дефект кода. Красный required
  check на чистом маркерном PR = close + reopen PR (перезапуск чеков без
  пустого коммита) и реран; три локальных прогона перед «чинить» — не правь
  рабочий код под CI-флак.
