# Реестр агентов конвейера

Каждый файл в этой папке — **системный промпт** для одного сабагента: подается целиком как системное сообщение при запуске агента на задаче.

## Анатомия системного промпта

| Секция | Содержимое |
|---|---|
| Роль | Кто агент, в чем его ценность, на чем он не специализируется |
| Режим запуска | План/auto-edit/Yolo: какие операции агент вправе делать без подтверждения |
| Скиллы | Какие скиллы из `skills/` загружать и в каком случае |
| Вход / Выход | Артефакты по контрактам из `contracts/artifact_contract.md` |
| Границы | Что агенту запрещено — питфоллы конкретной роли |
| Эскалация | Когда стоп и возврат через проектного менеджера |

## Режимы запуска

- **plan** — только анализ и черновики, запись в целевой репозиторий запрещена (диалоговые роли).
- **auto-edit** — запись рабочих артефактов разрешена; push и операции вне своей зоны — по указанию ПМ (стандарт для фабричных агентов).
- **yolo** — полный доступ, включая push; не используется в конвейере, резервируется для песочниц.

## Принцип изоляции задач

Сабагенты всегда работают в изолированных контекстных окнах (проверено, см. AGENTS.md «Оркестрация»). Особенность этапа разработки: **одна задача tasks.md = один dev-сабагент = одна сессия**; затем отдельный сабагент-ревьюер. Оркестратор никогда не совмещает автора и ревьюера в одном контексте.

## Реестр

| Агент | Системный промпт | Режим | Скилл | Бандл |
|---|---|---|---|---|
| Бизнес-аналитик | [ba_agent.md](ba_agent.md) | plan-write | requirements-elaboration | `/af-ba` |
| Системный аналитик | [sa_agent.md](sa_agent.md) | auto-edit | openspec-authoring, requirements-elaboration | `/af-sa` |
| Разработчик | [dev_agent.md](dev_agent.md) | auto-edit (1 задача/сессия) | implementation | `/af-dev` |
| Код-ревьюер | [code_reviewer_agent.md](code_reviewer_agent.md) | auto-edit (1 задача/сессия) | code-review | `/af-review` |
| QA: аналитик чеклистов | [qa_checklist_agent.md](qa_checklist_agent.md) | auto-edit | test-case-design, openspec-authoring | `/af-qa-checklist` |
| QA: автор тест-кейсов | [qa_case_author_agent.md](qa_case_author_agent.md) | auto-edit | test-case-design | `/af-qa-author` |
| QA: ревьюер тест-кейсов | [qa_case_reviewer_agent.md](qa_case_reviewer_agent.md) | auto-edit | case-review, test-case-design | `/af-qa-reviewer` |
| QA: автоматизатор | [qa_automation_agent.md](qa_automation_agent.md) | auto-edit | test-automation, test-case-design | `/af-qa-automation` |

## Поток конвейера

```
Заказчик ⇄ [ba | plan] → requirements.md → [sa | auto-edit] → openspec/changes/<id>/ + sdd.md
                                                                    │
      ┌─────────────────────────────────────────────────────────────┘
      ▼  (цикл на каждую задачу tasks.md)
[dev | 1 задача/сессия] → код → [code_reviewer | approve/return] → влитая задача
                                                                    │
      [qa_automation] ← approved/* ← [qa_reviewer] ⇄ new/* ← [qa_author] ← checklists ← [qa_checklist]
```

## Связанные документы

- Скиллы (процедуры по best practices): [skills/](../skills/)
- Контракты артефактов: [contracts/artifact_contract.md](../contracts/artifact_contract.md)
- Спеки конвейера (источник правды): [openspec/specs/](../openspec/specs/)
- Бэклог тюнинга: [BACKLOG.md](../BACKLOG.md)

## Планируемые роли (промпты не написаны)

- Release-инженер: сборка, развертывание на VPS, окружение
