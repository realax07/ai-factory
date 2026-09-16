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

## Реестр

| Агент | Системный промпт | Режим | Скилл | Бандл |
|---|---|---|---|---|
| Бизнес-аналитик | [ba_agent.md](ba_agent.md) | plan | requirements-elaboration | `/af-ba` |
| Системный аналитик | [sa_agent.md](sa_agent.md) | auto-edit | openspec-authoring, requirements-elaboration | `/af-sa` |
| QA: аналитик чеклистов | [qa_checklist_agent.md](qa_checklist_agent.md) | auto-edit | test-case-design, openspec-authoring | `/af-qa-checklist` |
| QA: автор тест-кейсов | [qa_case_author_agent.md](qa_case_author_agent.md) | auto-edit | test-case-design | `/af-qa-author` |
| QA: ревьюер тест-кейсов | [qa_case_reviewer_agent.md](qa_case_reviewer_agent.md) | auto-edit | case-review, test-case-design | `/af-qa-reviewer` |
| QA: автоматизатор | [qa_automation_agent.md](qa_automation_agent.md) | auto-edit | test-automation, test-case-design | `/af-qa-automation` |

Скиллы установлены в `~/.hermes/skills/ai-factory/` (единое хранилище Hermes), бандлы собирают их по ролям: `/af-ba`, `/af-sa`, `/af-qa-checklist`, `/af-qa-author`, `/af-qa-reviewer`, `/af-qa-automation`. Инструкция бандла задает роль и режим запуска (см. hermes bundles list).

## Поток конвейера

```
Заказчик ⇄ [ba | plan] → requirements.md → [sa | auto-edit] → openspec/ + sdd.md
                                                                    │
      [qa_automation] ← approved/ ← [qa_reviewer] ⇄ new/ ← [qa_author] ← checklists ← [qa_checklist]
```

## Связанные документы

- Скиллы (процедуры по best practices): [skills/](../skills/)
- Контракты артефактов: [contracts/artifact_contract.md](../contracts/artifact_contract.md)
- Спеки конвейера (источник правды): [openspec/specs/](../openspec/specs/)

## Планируемые роли (промпты не написаны)

- Разработчик: change-пакет → код продукта (режим auto-edit)
- Код-ревьюер: валидация кода против спеки и контракта 2
- Release-инженер: сборка, развертывание, окружение
