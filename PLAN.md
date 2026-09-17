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
- [ ] Установить flow_check + flow.yml в ekotov-wiki при старте QA
- [ ] requirements.md для wiki (БА-ассистент + Заказчик)
- [ ] OpenSpec-пакет + sdd.md для wiki (СА-агент)
- [ ] Инструкции: разработчик, код-ревьюер, release-инженер
- [ ] Разработка wiki (API + веб-интерфейс)
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
