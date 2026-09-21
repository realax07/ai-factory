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
| r13-ba-sa-impact-checklist-cases-review-automation | ba/sa/impact/checklist/cases/reviewer/automation | Ретро-Флоу 1 для R1.3 (requirements-p4, дельта, impact keep 12/0/0, чеклист 13 CHK, 4 кейса дыры, ревью approve, тесты+метки G5) | закрыто | f973e4a, b1efbca, 600537f, 8301bb1, 95dadac, 944346c, 3a4b890; архивация 23ae489 |
| r1-cleanup-dev | dev | R1.6 G9 чистка: 13 смоков удалено (+3 DOM-варианта поймано ПМ), final_check в archive | закрыто | ed36d42+19344df, merge 578f6ec, регресс 21+85/5 зеленый |

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
