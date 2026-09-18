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
- [ ] Блоки 6–8: архив (6.1 уход в архив, 6.2 признак в поиске/карточке), поиск, полировка
- [ ] QA-цикл на wiki: чеклисты → кейсы → ревью → автотесты
- [ ] Внедрение

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
