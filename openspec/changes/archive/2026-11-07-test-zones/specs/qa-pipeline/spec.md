## ADDED Requirements

### Requirement: Раскладка автотестов
Автотесты MUST лежать по уровню: tests/unit/ — unit-тесты разработчика; tests/api/ — приемка через HTTP API; tests/web/ — приемка через браузер (сьют против стенда — tests/web/e2e/); tests/integration/ — приемка через сервисный слой без HTTP и браузера. Смоук регресса MUST лежать в tests/smoke_cross/, архивные тесты — в tests/archive/. Запись в tests/unit/ MUST принадлежать роли dev, в остальные каталоги — роли qa_automation.

#### Scenario: Приемочный тест бота без HTTP API
- **GIVEN** проект не имеет HTTP API и UI
- **WHEN** автоматизатор пишет тест по одобренному кейсу
- **THEN** тест кладется в tests/integration/ с TC-ID в docstring

### Requirement: Проверка раскладки автотестов
Тестовый файл вне каталогов раскладки (в том числе в корне tests/) MUST считаться нарушением раскладки. Строгость проверки задает проект файлом test-model/test-layout.json: режим warn — предупреждение, strict — ошибка ворот. При отсутствии файла MUST применяться warn; нечитаемый файл MUST давать ошибку ворот.

#### Scenario: Тест в корне tests/ при строгой раскладке
- **GIVEN** test-model/test-layout.json задает режим strict
- **WHEN** в корне tests/ появляется файл test_*.py
- **THEN** проверка порядка артефактов завершается ошибкой раскладки

#### Scenario: Проект до миграции раскладки
- **GIVEN** файла test-model/test-layout.json нет
- **WHEN** тестовые файлы лежат вне каталогов раскладки
- **THEN** проверка выдает предупреждение и не блокирует мерж

#### Scenario: Unit-тест обращается к сети
- **GIVEN** файл в tests/unit/ импортирует requests или playwright
- **WHEN** проверка порядка артефактов
- **THEN** фиксируется нарушение стека по режиму раскладки

## MODIFIED Requirements

### Requirement: Трассировка автотестов
Каждый приемочный автотест (tests/api/, tests/web/, tests/integration/, tests/smoke_cross/, tests/archive/) MUST ссылаться на ID тест-кейса в docstring. Приемочный тест без ссылки на кейс MUST NOT приниматься. Матрица кейс → тест MUST находиться в tests/README.md. Unit-тесты разработчика (tests/unit/) пишутся без тест-кейсов: ссылка на TC-ID для них MUST NOT требоваться, ссылка на FR-N или задачу tasks.md SHOULD присутствовать.

#### Scenario: Тест без трассировки
- **GIVEN** автотест не содержит ID кейса в docstring
- **WHEN** ревью кода тестов
- **THEN** тест помечается дефектом трассировки

### Requirement: Стек автотестов
API-тесты MUST быть написаны на Python с pytest и requests. Web-тесты MUST быть написаны на Python с pytest и playwright. Unit- и integration-тесты MUST быть написаны на Python с pytest и MUST NOT использовать сеть (requests) и браузер (playwright). Автотесты MUST быть изолированы (независимость от порядка запуска) и детерминированы (запрет sleep вместо ожиданий).

#### Scenario: Sleep вместо ожидания
- **GIVEN** в коде теста используется time.sleep для ожидания условия
- **WHEN** ревью кода тестов
- **THEN** тест помечается дефектом (для web — автожидания Playwright, для API — poll-цикл с таймаутом)
