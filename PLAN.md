# План: Конвейер Агентов (AI Factory)

> Источник правды по проекту. Дополняется по мере прогресса. Не зависит от сессий агента.

## Ключевое правило

**ai-factory — это конвейер** (инструкции агентов, артефакты, процессы).
**ekotov-wiki — пилотный проект** (личная wiki), первый заказ конвейера.
Конвейер после пилота будет использоваться для других проектов.

## Решения

- Каждая роль = отдельный сабагент с валидацией результата (нет «одного QA-агента»).
- Бизнес-анализ: двухступенчатый БА-конвейер избыточен; один БА-агент — ассистент Заказчика по формулированию ТЗ (основа: IEEE 830/29148).
- Системный анализ: OpenSpec (Fission-AI) как формат спек + SDD; specs — поведение, design/tasks — реализация.
- QA: конвейер из 4 сабагентов (чеклисты → кейсы → ревью → автотесты) с итерационным циклом «автор ↔ ревьюер»; стек автотестов: Python, pytest, requests (API), playwright (web).
- Артефакты процесса: Markdown, передача между агентами только через репозиторий.
- Автотесты пишутся только по одобренным ревью кейсам; красный тест на корректном коде = баг-репорт, не правка теста.
- Правила конвейера формализованы как спеки OpenSpec в самом ai-factory (openspec/specs/{pipeline,artifacts,qa-pipeline}); agents/*.md и contracts/*.md подчинены спекам. CLI: openspec validate --all --strict.
- Детерминизм флоу: AGENTS.md (входной файл агента) + scripts/flow_check.py (state-machine проверка порядка артефактов, exit 1 при нарушении) + CI (.github/workflows/flow.yml: openspec strict + flow_check на каждый push). Скиллы установлены в ~/.hermes/skills/ai-factory, роли собираются бандлами /af-*.

## Статус

- [x] Репозитории созданы и настроены (ai-factory, ekotov-wiki)
- [x] SSH-доступ, .gitignore, базовый README
- [x] Инструкция БА-агента
- [x] Инструкция СА-агента + внедрение OpenSpec и SDD
- [x] QA-контур: 4 инструкции + контракты 3–6
- [x] Контракты передачи артефактов (contracts/artifact_contract.md)
- [x] AGENTS.md + исполняемые ворота флоу (scripts/flow_check.py + CI flow.yml)
- [x] BA-этап wiki: requirements.md r3 «ГОТОВ К УТВЕРЖДЕНИЮ» (3 раунда, ОВ-1…ОВ-18 закрыты)
- [x] Утверждение r3 Заказчиком
- [x] OpenSpec-пакет add-kanban-core + sdd.md для wiki (СА-агент, 29 Req/57 сценариев, 7 доменов)
- [x] Роли dev + code_reviewer: промпты, скиллы implementation/code-review, бандлы af-dev/af-review
- [x] Цикл 1.1 (каркас): dev a49944a → review approve a0cfa48
- [x] Цикл 1.2 (схема БД): dev a5614e2 → review approve 5e859cc
- [x] Цикл 1.3 (seed): dev 6243224 → review approve 72abed2
- [x] Цикл 1.4 (deploy): dev 24b02d3 → return → fix ff95f22 → approve 75b315c (первый return, отработан)
- [x] Блок 1 «Каркас и инфраструктура» закрыт (4/4)
- [ ] Эскалация СА: health-эндпоинт в sdd §3 + exempt-список — ЗАКРЫТА (35d19e2, sdd r4)
- [x] Блок 2 «Авторизация» закрыт (3/3): 2.1 login (baa459d→b1c6fbf), 2.2 middleware (d4f3a10→49f481a), 2.3 login page (e466217→dcc2ea0)
- [x] Блок 3 «Каркас UI» закрыт (2/2): 3.1 сайдбар (b446385→b8e9500), 3.2 защита страниц — верификация 18 путей, дыр нет (8c81d14)
- [x] Блок 4 «Задачи и доска» закрыт (5/5): 4.1 CRUD (ad3e2bb→6992975), 4.2 комментарии (0220b9c→36f58d5), 4.3 доска (28f1ece→93bebd2), 4.4 move (b0aaa50→008716a), 4.5 UI (d4b380f→return→7ca9284→5e5b8ed)
- [x] Блок 5 «Fast line» закрыт (2/2): 5.1 инвариант + 409 + unarchive (c391eab→b483e11), 5.2 UI подсветка (50fafb5→fcc151c)
- [x] Блок 6 «Архив» закрыт: 6.1 done_at + ленивая автоархивация МСК (1451aaf→return→9fdbb86→72bfe89), 6.2 признак в карточке (194d3fa→7d29d09); поисковая часть 6.2 отложена в 7.x
- [x] Блок 7 «Поиск» закрыт (3/3): 7.1 API фильтров (fc68e34→a5af921), 7.2 advanced (618a8d8→return→ff78461→587eb00), 7.3 UI вкладка (5341274→e2e69a3)
- [x] Блок 8 «Полировка» закрыт (2/2): 8.1 NFR-3 рестарт (558a202→71b9d83), 8.2 NFR-1/2 производительность 1100+ задач (запас ≥12×) — все approved
- [ ] Блок 9 «Финализация»: 9.1 прогон всех сценариев спек → 9.2 README deploy (seed, nginx+TLS, бэкап)
- [x] Блок 9 «Финализация» закрыт (2/2): 9.1 чеклист 64/64 сценариев PASS (12b9763), 9.2 deploy README + раздел Бэкап
- [x] РАЗРАБОТКА add-kanban-core ЗАВЕРШЕНА: 25/25 задач, все approved
- [x] QA-цикл закрыт: чеклист 81 CHK (80 кейсов + CHK-35 отложен DS-1) → ревью 3 итерации → автотесты 60 passed/22 skipped, 0 багов продукта
- [x] Архивация пакета (контракт 7): add-kanban-core → 8 master-specs (32 Requirement, Purpose заполнены), regression-домен создан; пакет в changes/archive/2026-09-18-add-kanban-core
- [x] Внедрение выполнено (2026-09-19): текущая машина 194.58.34.122, nginx TLS :10443 (self-signed CN=IP, нестандартный порт), uvicorn 127.0.0.1:8377 под systemd (user wiki), БД /var/lib/ekotov-wiki/wiki.db, seed owner+wife, health 200 снаружи, auth-флоу 401/302 проверены

## Журнал делегаций (D1)

Одна строка на делегацию; append-only. Назначение — восстановление контекста ПМ после компакции/в новой сессии. Шаблон сборки goal: templates/task_delegation.md.

| ID | Роль | Задача | Статус | Результат |
|---|---|---|---|---|
| (пилот, до введения журнала) | ba/sa/dev/reviewer/qa-* | add-kanban-core: полный цикл | закрыто | см. чеклист выше; детали в git-истории |
| (пилот) dev+reviewer | dev, code_reviewer | фикс 2 UI-багов доски (модалки hidden, integer-guard) | закрыто | 79ceb7b, фиксы на проде проверены |
| e2e-checklist-002 | qa_checklist | чеклист E2E критического пути (G1) | закрыто | 483c753, 18 CHK-E |
| e2e-cases-001 | qa_case_author | 18 TC-UI кейсов | закрыто | 41e64f0 + fix 8b3c3e3 (review-001 return) |
| e2e-review-002 | qa_case_reviewer | ревью кейсов 002 | закрыто | e442947 approve |
| e2e-automation-001 | qa_automation | Playwright-сьют 18 тестов | закрыто | cb0da6e: 17 passed / 1 failed = BUG-001 (поиск→карточка), API-регресс 77/5 чист |
| r1-bug001-dev | dev | R1.1 фикс BUG-001 (первый G6 PR-цикл) | закрыто | f6baa75 → merge f3248d9, прод обновлен |
| r1-bug001-review | code_reviewer | ревью PR BUG-001 | закрыто | approve, 0 findings |
| r1-p6-dev | dev | R1.2 P6 board.js -> ES modules (7 модулей) | закрыто | 63a205b+fc4d9ff, 18/18 web (подтверждено ПМ), origin/main обновлен |
| r1-p4-dev | dev | R1.3 P4: GET /api/suggestions + datalist (по уточнению Заказчика set(tags∪categories)) | закрыто | 1f11011, прод обновлен |
| r13-ba | ba | Ретро-ТЗ R1.3: requirements-p4.md (FR-15..18, УТВЕРЖДЕН пост-фактум) | закрыто | f973e4a |
| r13-ba-sa-impact-checklist-cases-review-automation | ba/sa/impact/checklist/cases/reviewer/automation | Ретро-Флоу 1 для R1.3 (requirements-p4, дельта, impact keep 12/0/0, чеклист 13 CHK, 4 кейса дыры, ревью approve, тесты+метки G5) | закрыто | f973e4a, b1efbca, 600537f, 8301bb1, 95dadac, 944346c, 3a4b890; архивация 23ae489 |
| r1-cleanup-dev | dev | R1.6 G9 чистка: 13 смоков удалено (+3 DOM-варианта поймано ПМ), final_check в archive | закрыто | ed36d42+19344df, merge 578f6ec, регресс 21+85/5 зеленый |
| deploy-R1 | ПМ | Деплой Релиза 1 на прод (после ребута машины) | закрыто | health ok, ES-модули на проде, suggestions 401, /board 302 — все проверки impact GO выполнены. РЕЛИЗ 1 ЗАКРЫТ |
| r2-ba | ba | ТЗ Релиза 2 requirements-r2.md (FR-19..30, решения Заказчика дословно, 0 открытых вопросов) | закрыто | requirements-r2.md закоммичен ПМ |
| r2-sa | sa | Change-пакет Релиза 2: openspec/changes/add-r2-categories-settings/ (proposal/design/7 дельт/tasks 2.1-2.6/sdd) | закрыто | a8caab5, ворота зеленые (openspec 9/9 strict, flow_check OK), трассировка 12/12 FR+NFR-8, 14 чекбоксов чисты; приемка ПМ пост-фактум (отчет СА сверен с фактами) |
| r2-dev-1 | dev | R2 задача 2.1: backend — categories + CRUD + валидация 422 + миграция (tasks 1.1-1.3) | закрыто | aa81df9 в origin/feature/...-1, диф в зоне (backend+чекбоксы 3/3), смоук 41/41, регресс tests/api 85 passed/5 skipped (заявления сверены ПМ: ветка, диф, PR-текст /tmp/pr_body.md); gh на машине нет — PR создаст ПМ; эскалация: design §1.4 «автообновление задач» при хранении по значению неточно — на ревью |
| r2-review-1 | code_reviewer | Ревью PR задачи 2.1 (deleg_3c3bf29f) | закрыто | APPROVE (review-001.md), ворота зеленые, миграция идемпотентна (2 прогона), смоки 20/20, 3 minor findings; эскалации: design §1.4 правка текста (при архивации), сьют Р1 несовместим с FR-21 → план QA 6.x; зона соблюдена |
| r2-fix1-dev | dev | Задача 2.1 фикс 3 minor findings ревью (IN_USE_BODY, BEGIN IMMEDIATE rename, fast-транзакция) | закрыто | 27de791 в origin, диф 2 файла 25+/10− в границе, ворота зеленые, смоук PASS, идемпотентность миграции подтверждена (заявления сверены ПМ) |
| r2-review-1b | code_reviewer | Повторное ревью фикса 27de791 (deleg_00bf2c70) | закрыто | APPROVE (review-002.md): 3/3 findings устранены, граница соблюдена, атомарность доказана экспериментально (сбой-симуляция), смоки 13/13; задача 2.1 влита ПМ |
| merge-2.1 | ПМ | Merge задачи 2.1 в main (PR-обход: gh нет, E4) | закрыто | 909478d merge в main, push origin/main; ворота после merge зеленые (flow_check OK) |
| r2-dev-2.2 | dev | R2 задача 2.2: страница /settings + сайдбар (ветка ...-2) | закрыто | 176eeaa в origin, диф в зоне +эскалация 14 строк pages.py (роут страницы, API не дублирован — принять), смоук 24/24, навигация на всех страницах; регресс-падения на пустой БД = известная R1-фикстуры vs FR-21 |
| r2-dev-2.3 | dev | R2 задача 2.3: селект категории в форме/фильтре + подсветка 422 (ветка ...-3) | закрыто | 4bf1326+ae9edca+f0bd37c в origin, диф в зоне, регресс 85/5 на сеяной БД, eslint чист; эскалация: QA-контуру — seed категорий перед прогоном |
| r2-designer | ui_designer | Д-5: 2-3 варианта стиля формы, design/ (новая роль, промпт ui_designer_agent.md) | закрыто | design/form-style-v1/v2/v3.html + README (сравнение+токены), 0 внешних зависимостей, AA-контраст, выбор за Заказчиком; коммит за ПМ |
| d5-decision | Заказчик | Выбор стиля формы (Д-5) | закрыто | РЕШЕНО 2026-09-22: V3 «Бумага», распространить на ВСЮ доску (карточки+колонки+форма), 2.5 — стандартно по FR-28/29 + токены V3 |
| r2-review-2a | code_reviewer | Ревью ветки -2 (settings) deleg_6a283b0a | закрыто | APPROVE (review-003.md): Playwright-смоук CRUD, XSS-проверка, FR-23/24/25 подтверждены, 3 minor; 13 падений регресса = известная FR-21-фикстуры (вход 6.1); worktree-изоляция сработала |
| r2-review-2b | code_reviewer | Ревью ветки -3 (селекты) deleg_6a283b0a | закрыто | APPROVE (review-004.md): целостность дерева подтверждена, смоук селектов/422/aria, обратная совместимость api.js, регресс 68/0/22 на сеяной БД, 5 minor; TC-UI-SUGG-001 устарел (вход 6.1) |
| merge-2.2-2.3 | ПМ | Merge задач 2.2+2.3 в main + коммит design/ | закрыто | 30d5b4f (reviews+design V3), ab537b1 (2.2), c67c60a (2.3); push origin/main; ворота после merge зеленые |
| r2-dev-2.4 | dev | R2 задача 2.4: автодополнение тегов + priority-lock (worktree, ветка ...-4) | закрыто | dcc1ee0 в origin, диф 4 файла +105/−4 в зоне, смоук 22/22, найден и закрыт обход PATCH priority=null на fast; регресс-дельта 0 vs main (8+1 предсуществующие); worktree-изоляция подтверждена |
| r2-dev-2.5 | dev | R2 задача 2.5: V3 «Бумага» на всю доску (Д-5), крестик, приоритеты цвет+SVG (ветка ...-5) | закрыто | d7475db в origin, диф 11 файлов +722/−217 в зоне (CSS+priority-icons.js новый), скриншоты /tmp/ekotov-wiki-25/, web-регресс = базлайн main (моих регрессий нет); эскалация: подписи «Низкий/Средний/Высокий» vs сырые значения в TC-UI-009 — на ревью/QA |
| r2-review-3a | code_reviewer | Ревью ветки -4 (4.1+4.2) deleg_db7e7c32 | закрыто | APPROVE (review-005.md): смок 17/17, 422 дословно на 5 путях, NULL-обход закрыт подтвержден, регресс-дельта 0, 2 minor |
| r2-review-3b | code_reviewer | Ревью ветки -5 (визуал V3) deleg_db7e7c32 | закрыто | APPROVE (review-006.md): крестик 40px/subpixel, SVG=эталон, V3-токены совпадают мокапу, a11y+ОГР-8 подтверждены, web-регресс=baseline побайтно, 2 minor; эскалация: TC-UI-009 синхронизировать в 6.1 |
| merge-2.4-2.5 | ПМ | Merge задач 2.4+2.5 в main | закрыто | 8bd6ad9 reviews, de769f4 (2.4), db89106 (2.5); push origin/main; ворота зеленые; worktree /tmp прибраны (wt-r24, rv-24, rv-25) |

### План задачи: change-пакет Релиза 2 (план от 2026-09-22)

- **Флоу:** 1 (полный: СА → циклы задач 2.1-2.5 с dev→ревью, 2.6 QA-контур).
- **Состав:** СА-сессия создает change-пакет из requirements-r2.md; далее по tasks.md — циклы dev→code_reviewer; QA-контур в конце; архивация по контракту 7.
- **Ворота входа СА:** requirements-r2.md утвержден (проверено ПМ пост-фактум: flow_check OK, openspec 8/8).
- **Особенности:** FR-27 меняет спеку fastline (дельта MODIFIED); дельта категорий ADDED; Д-1..Д-5 — дефолты с правом возражения Заказчика.

## Роли и скиллы

Системные промпты (роль, режим запуска, скиллы, вход-выход, границы, эскалация): [agents/README.md](agents/README.md)

| Промпт | Роль | Режим | Скилл |
|---|---|---|---|
| agents/ba_agent.md | Бизнес-аналитик | plan | requirements-elaboration |
| agents/sa_agent.md | Системный аналитик | auto-edit | openspec-authoring |
| agents/qa_checklist_agent.md | QA: аналитик чеклистов | auto-edit | test-case-design |
| agents/qa_case_author_agent.md | QA: автор тест-кейсов | auto-edit | test-case-design |
| agents/qa_case_reviewer_agent.md | QA: ревьюер тест-кейсов | auto-edit | case-review |
| agents/qa_automation_agent.md | QA: автоматизатор | auto-edit | test-automation |

Скиллы (процедуры по best practices, гайд Anthropic): [skills/](skills/).
Контракты передачи артефактов: [contracts/artifact_contract.md](contracts/artifact_contract.md) (контракты 1–7).
Спеки конвейера (источник правды): [openspec/specs/](openspec/specs/).
Бэклог тюнинга конвейера (уроки пилота): [BACKLOG.md](BACKLOG.md)
