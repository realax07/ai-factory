# Artifacts Specification — remove-qa-checklist (дельта)

## MODIFIED Requirements

### Requirement: Трассировка требований
Каждый Requirement в спеке MUST ссылаться на идентификатор ТЗ (FR-N/NFR-N). Каждый тест-кейс MUST иметь ссылку на источник: заголовок `### Requirement:` или `#### Scenario:` спеки (remove-qa-checklist: трассировка через CHK-чеклист упразднена). Матрица трассировки MUST находиться в sdd.md.

#### Scenario: Кейс без трассировки к спеке
- **GIVEN** тест-кейс не ссылается ни на один заголовок Requirement/Scenario спеки
- **WHEN** flow_check проверяет артефакты
- **THEN** кейс помечается дефектом трассировки

#### Scenario: Requirement без источника
- **GIVEN** Requirement не ссылается на FR-N/NFR-N
- **WHEN** любой потребитель проверяет артефакт
- **THEN** элемент помечается дефектом трассировки

### Requirement: Директории QA-артефактов
QA-артефакты MUST располагаться: новые тест-кейсы — `test-model/new/<change-id>/`, ревью — `test-model/reviews/<change-id>/`, одобренные кейсы — `test-model/approved/<change-id>/`, баг-репорты — `test-model/bugs/`. Каталог `test-model/checklists/` — append-only история упраздненного этапа чеклистов: существующие файлы MUST NOT удаляться, новые чеклисты MUST NOT создаваться.

#### Scenario: Кейсы размещены в новой папке
- **GIVEN** автор тест-кейсов завершил работу
- **WHEN** файлы кейсов записаны в test-model/new/<change-id>/
- **THEN** ревьюер вправе начать ревью

#### Scenario: Автотесты начаты до одобрения
- **GIVEN** кейсы отсутствуют в test-model/approved/<change-id>/
- **WHEN** автоматизатор получает задачу
- **THEN** работа не начинается до появления одобренных кейсов
