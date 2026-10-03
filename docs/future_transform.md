# Future Transform: поэтапная трансформация AI Factory

> План для агента, который будет выполнять миграцию. Дата: 2026-10-03.
> База анализа: main, commit b9804454c4462fb05f626eb5987d12217a9743fe.
> Повторная проверка: 2026-10-03; HEAD прежний. Уточнения: обязательные API + Playwright, полный as-is/change reconciliation. См. future_transform_review.md и as_is_change_consistency_task.md.
> Статус: предложение целевой архитектуры и последовательности работ. Этот документ НЕ меняет действующие правила, права ролей, approval gates или режим enforcing.
> Текущая работа: Флоу 4, документация — создать этот план и передать через PR. Реализация стадий ниже — отдельные будущие change-пакеты после разрешения Заказчика.

## 1. Цель и важное уточнение Заказчика

Перестроить фабрику вокруг последовательных преобразований бизнес-задачи в исполнимые изменения и доказательства их корректности.

Одна стадия = одно сфокусированное контекстное окно = одно основное преобразование. Предыдущая стадия снимает определенный класс неопределенности и передает следующей достаточно информации для ее работы.

Дословное уточнение Заказчика:

> «важный момент, инструкции по флоу сабагентам я вносил чтобы они меньше тыкались и зрали свой флоу»

Смысл уточнения для миграции: инструкции по flow выполняют полезную навигационную функцию. Их нельзя просто удалить под предлогом экономии контекста. Детерминированная проверка запрещает неправильное действие, но сама по себе не объясняет агенту, какое действие правильно и чего сейчас не хватает.

Сохранить два взаимодополняющих слоя:

1. **Flow awareness для агента:** где он находится, что должен получить, что имеет право делать, кому передает результат, как распознать блокер.
2. **Flow enforcement в runtime:** права, резервации, state transitions, проверки, provenance, приемка и запрет обходов.

Оптимизировать объем навигации, а не лишать агента знания процесса. Механика переносится из prompt только после появления проверенного эквивалента в runtime/skill.

## 2. Что считать успехом

Фабрика должна последовательно устранять:

| Стадия | Класс неопределенности | Что становится определенным |
|---|---|---|
| Intent / BA | Бизнес-смысл | Цель, границы, требования, принятые решения |
| Behavior / Specification | Наблюдаемое поведение | Сценарии, состояния, ошибки, правила |
| Solution | Способ реализации | Компоненты, интерфейсы, данные, технические ограничения |
| Architecture validation | Совместимость решения | Конфликты, подтвержденные ограничения, риски |
| Execution planning | Исполнение | DAG задач, зависимости, зоны и вход каждого окна |
| DEV | Материализация задачи | Изменение кода, реализующее заданное поведение |
| Code review | Корректность реализации | Контрпримеры или обоснованный результат проверки |
| QA obligations | Полнота проверяемых обязательств | Модель проверок наблюдаемого поведения |
| QA scenarios | Воспроизводимость проверки | Конкретные данные, действия, ожидаемые результаты |
| QA review | Корректность сценариев | Принятые сценарии и их доказуемая трассировка |
| QA automation | Исполнимость проверки | Детерминированные проверки утвержденных сценариев |
| Integration / archive | Согласованность общего состояния | Интегрированный код и актуальная master-spec |
| Release / ops | Готовность конкретной версии | Evidence для решения о выпуске и проверенный runbook |

Не каждое окно обязано дробить артефакт на несколько файлов. Производящие стадии уточняют или декомпозируют; reviewer-стадии проверяют утверждения; интеграция объединяет результаты. Не заставлять все стадии искусственно вести себя как planners.

«DEV не принимает продуктовых решений» не означает запрет локальных инженерных решений: имена функций, внутренний рефакторинг в своей зоне и выбор эквивалентного алгоритма допустимы, если не меняют заданные контракты и соседние задачи.

## 3. Уровни ответственности и источники истины

| Слой | Содержимое | Предлагаемое размещение |
|---|---|---|
| Semantic prompt | Purpose, transformation, authority, completion, escalation | agents/*_agent.md |
| Flow card | Место стадии, вход, действие, выход, блокеры | Короткая секция prompt / генерируемая карточка |
| Reasoning skill | Метод выполнения преобразования | skills/<name>/SKILL.md + references |
| Policy | Обязательные запреты, права, approval rules | Действующие specs/contracts и их исполняемые проверки |
| Artifact contract | Формат, связи, версия, критерии приемки | contracts/, templates/ |
| Runtime profile | Реальные capabilities и режим запуска | Новые профили, подключенные через адаптер |
| Runtime executor | Prepare/reserve/gates/provenance/merge/cleanup | Существующие scripts/ с постепенным расширением |
| Project context | Стек, инфраструктура, дизайн, env | Артефакты проекта / проектные skills |

Сохранить действующий порядок изменения правил: **спека → контракт → policy/runtime → prompt/skills/templates → проверка**. Новая папка policies/ не должна стать вторым независимым источником правил. Сначала определить, будет ли она генерируемой проекцией specs или исполняемой конфигурацией со ссылкой на норму.

При конфликте prompt, skills, реестра ролей и runtime агент возвращает конфликт через ПМ. Этот документ не дает права выбрать удобную версию правила.

## 4. Общий Agent Contract v2

Применить шаблон к каждой стадии, сохраняя ее актуальные входы, зоны и gates:

```markdown
# <stage>: <one transformation>

## PURPOSE
Какой класс неопределенности снимает это окно и кому нужен результат.

## INPUT STATE
Обязательные артефакты, их версии, статусы и достаточность.
Невалидный вход возвращается предыдущему владельцу через ПМ.

## TRANSFORMATION
Одно основное преобразование входа в выход.
Какие решения должны стать явными.

## DECISION AUTHORITY
Что можно решить локально.
Что принадлежит предыдущей стадии, соседним задачам или Заказчику.

## OUTPUT STATE
Артефакты и семантические свойства результата.
Что следующий агент получает и чего ему больше не нужно додумывать.

## COMPLETION INVARIANT
Проверяемые условия завершения; отчет сам по себе не evidence.

## ESCALATION CONDITION
Типы недостаточности/конфликтов и адресат возврата.

## FLOW CARD
Предыдущая стадия → эта стадия → следующая.
Входной контракт; действие runtime; зона; обязательные gates.
DENY/UNKNOWN → stop + код причины + missing evidence → ПМ.
Prepare/reserve/finish выполняет назначенный runtime-владелец.

## METHODS
Какие role skills нужны всегда, какие загружаются по условию.
```

Размер prompt — метрика, а не цель. Не вводить лимит, из-за которого пропадет важная граница решений. Сохранять короткие запреты, требующие осознания агентом: не обходить DENY, не менять чужую спеку, не расширять задачу, не подгонять тесты.

## 5. Flow awareness: обязательная часть миграции

### 5.1. Карточка стадии

Для каждой роли подготовить короткую карточку из актуального контракта и stage table:

```yaml
# Предлагаемый формат AI Factory; не API Hermes.
stage: dev_task
upstream: validated_execution_unit
downstream: code_review
entry:
  - task_and_source_refs_present
  - dependencies_accepted
  - runtime_prepared_and_zone_reserved
authority:
  - implement_assigned_task
  - make_local_technical_choices_within_contract
forbidden:
  - change_product_behavior
  - bypass_flow_denial
  - write_outside_reserved_scope
runtime_owner: orchestrator
on_block:
  report: [reason_code, missing_evidence, source_ref, requested_owner]
```

Использовать реальные stage names/codes из текущего runtime. Новые названия выше — семантические понятия, не готовые переходы state machine.

### 5.2. Как изменить factory-flow

Сохранить skills/factory-flow как навигационный skill. Его текущее назначение уже соответствует потребности Заказчика: карта стадий, блокеров и эскалаций.

Разделить содержимое:

- Короткий общий скелет: prepare → reserve → work → zone-check/gates → provenance → accept/return.
- Карточки ролей: только свой вход, шаг, выход и блокеры.
- Полный справочник флоу 1–5 и recovery: ссылки / references, загрузка по необходимости.
- Механика выполнения: runtime commands и их проверенные interfaces.

Не заставлять каждого исполнителя читать целиком все пять флоу при каждой задаче, если он уже получил flow_id и свою карточку. Но сохранять доступ к полной карте.

Перед генерацией карточек сопоставить docs/README-flow-control.md, flow_transition.py, role_zone_policy.py, agents/README.md и contracts. Сейчас текстовые источники могут расходиться: например, ownership merge/architecture_review и порядок impact analysis. Фиксировать расхождения как дефекты, а не воспроизводить их в генераторе.

### 5.3. Приемка

Агент по карточке до первой записи должен правильно назвать:

- свою текущую стадию и legal next step;
- отсутствующий вход, если он отсутствует;
- границу записи и runtime-владельца;
- реакцию на DENY/UNKNOWN/STALE_EVIDENCE;
- следующего потребителя артефакта.

Сравнить число ошибочных попыток, повторных tool calls и токены до первого полезного действия с baseline. Сокращение prompt при росте «тыканья» — регрессия.

## 6. Детальные изменения по когнитивным стадиям

### 6.1. BA / Intent refinement

**Текущие файлы:** agents/ba_agent.md, skills/requirements-elaboration/SKILL.md.

**Purpose:** снять бизнес-неопределенность до состояния, когда можно описать поведение без догадок о намерении Заказчика.

**Вход:** запрос, актуальный product overview, ограничения, ответы Заказчика, текущие specs для brownfield.

**Преобразование:** отделить FACT, GOAL, CONSTRAINT, REQUIREMENT, ASSUMPTION, DECISION_NEEDED, OUT_OF_SCOPE. Для каждого значимого утверждения сохранить источник. Перевести цели в проверяемые FR/NFR, явно оформить нерешенные вопросы.

**Выход:** действующий requirements.md, answers_roundN.md и предусмотренные проектом обзорные документы; реестр неопределенности внутри согласованного формата.

Добавить к записи неопределенности: ID, текст, источник, влияет на какие FR/NFR, blocking/non-blocking, владелец решения, статус, основание закрытия. Допущение не становится утвержденным требованием из-за отсутствия возражения.

**Authority:** структурировать и уточнять; предлагать варианты; не выбирать приоритеты или бизнес-поведение без соответствующего полномочия.

**Completion:** каждое Must проверяемо, имеет источник и не зависит от скрытого блокирующего допущения. SA не нужно восстанавливать бизнес-смысл из переписки.

**Skill:** сохранить elicitation, FR/NFR, MoSCoW; добавить метод классификации неопределенности, проверку противоречий и примеры преобразования расплывчатого запроса. Не превращать классификатор в обязательное раздувание каждого документа.

**Flow card:** Заказчик → BA → approve_requirements → Specification. Явное утверждение остается; лимит раундов вопросов не отменяет blocking ambiguity.

**Приемка:** кейс с противоречивыми ответами возвращается как DECISION_NEEDED; кейс с фразой «быстро» получает измеримый критерий или вопрос; неподтвержденное допущение не маскируется под FACT.

### 6.2. Specification / Behavioral refinement

**Текущий носитель:** agents/sa_agent.md и openspec-authoring. Сначала выделить ответственность логически внутри SA; физическое разделение — отдельная миграция.

**Purpose:** требования → полная модель наблюдаемого поведения.

**Вход:** утвержденные requirements, ответы, master-spec и границы change.

**Преобразование:** сценарии состояний/переходов, позитивные и негативные ветви, роли/права, инварианты, наблюдаемые ошибки, условия приемки; дельты ADDED/MODIFIED/REMOVED.

**Выход:** proposal и spec deltas с FR/NFR → Requirement → Scenario. Не смешивать их с выбором библиотек и реализацией.

**Authority:** формализовать уже утвержденный смысл; при новом бизнес-выборе возвращать BA/Заказчику. Технические детали в поведении допустимы, когда сами являются внешним контрактом.

**Completion:** design и QA могут работать от одинаковой модели поведения; сценарии имеют однозначный oracle либо явно блокируют стадию.

**Skill:** выделить behavior-specification методику из общего openspec-authoring; сохранить правила CLI и формат MODIFIED целиком, включая непоменявшиеся сценарии. Research/design/tasks перестают быть побочными задачами этого окна после подключения новых стадий.

**Flow card:** approve_requirements → create_change/behavior artifact → Solution + QA obligations. До появления отдельных runtime stages использовать текущий легальный маршрут SA.

**Приемка:** отсутствие FR Must обнаруживается; сценарий, требующий нового бизнес-решения, эскалируется; MODIFIED не теряет старые сценарии.

### 6.3. Solution refinement

**Предлагаемая стадия:** отдельное окно или явно отдельный запуск SA в переходный период. Не создавать новую роль только ради нового названия.

**Purpose:** поведение → реализуемое техническое решение в текущих ограничениях.

**Вход:** версия spec deltas, NFR, архитектурная карта/ADR, факты кода и среды, проектный стек.

**Преобразование:** компоненты, интерфейсы, API, данные, транзакции, миграции, обработка ошибок, deployment assumptions, варианты и обоснование выбора.

**Выход:** research.md, design.md, change-scoped технические контракты, согласованное обновление sdd.md.

Глобальный sdd.md — общая зона: не допускать параллельных писателей. Рассмотреть change-scoped дизайн и сборку global SDD при приемке; сначала проверить совместимость потребителей.

**Authority:** выбрать техническое решение в пределах specs/NFR; новые зависимости с изменением разрешений/ресурсов — эскалация согласно текущим правам.

**Completion:** интерфейсы между будущими задачами определены; критичные предположения либо подтверждены, либо блокируют планирование; task planner не выбирает архитектуру заново.

**Skill:** методы сравнения вариантов, API/data contracts, failure modes. Проектные пути/порты/топология получаются из project context, не из универсального prompt.

**Flow card:** Specification → Solution → Architecture validation → Planning.

**Приемка:** неверное предположение о раздаче статики видно как assumption с evidence; API и схема согласованы; невозможный NFR возвращается владельцу.

### 6.4. Architect / Constraint validation

**Файл:** agents/architect_agent.md.

**Purpose:** проверить решение на совместимость с целой системой.

**Вход:** proposed design, specs, актуальная карта, ADR, подтвержденные факты среды.

**Преобразование:** поиск конфликтов, непроверенных допущений, нарушения NFR, зависимостей и границ компонентов. Reviewer не переписывает design автора.

**Выход:** version-bound architecture review; карта/ADR обновляются только для принятых решений с соответствующим статусом proposed/accepted/implemented.

Для assumption фиксировать: ID, statement, evidence_ref, confidence/verification_status, impact_if_false, owner, required_validation. «Проверено на проде» — один вид evidence; код, конфиги и тесты тоже допустимы с указанием области действия.

**Completion:** нет открытого блокирующего конфликта; review относится к конкретной версии design; остаточные риски явно приняты уполномоченным владельцем.

**Skill:** архитектурная инспекция, карта/ADR, риск-анализ. Проверить доступность architecture-diagram и codebase-inspection в Hermes: они упоминаются в prompt, но не лежат в skills/ этого репо.

**Flow card:** Solution → architecture_review → Planning либо return Solution. Согласовать фактическую роль runtime с новым владельцем; не просто заменить pm строкой architect в тексте.

**Приемка:** изменение design после approve делает evidence stale; карта не объявляет предложенный компонент уже работающим.

### 6.5. UI designer / Frontend refinement и visual contract

**Файл:** agents/ui_designer_agent.md.

**Purpose:** заданные пользовательские взаимодействия → проработанное решение фронта и готовый к реализации HTML/визуальный контракт. Фокус окна — фронт: структура экранов, компоненты, состояния и их взаимодействие, визуальная система и ограничения frontend. Это шире декоративного оформления.

**Вход:** UI-сценарии, принятый дизайн проекта, ограничения, перечень экранов/состояний.

**Выход:** HTML-макеты как проверяемый эталон фронта, структура компонентов, токены, состояния, адаптивность, доступность, связи с Scenario, выбранная Заказчиком версия. При необходимости — frontend design notes для DEV с границами компонентов и интеграции. Зона продукт-кода остается определенной действующим контрактом; расширять ее без отдельного изменения policy нельзя.

**Authority:** визуальные варианты внутри заданного поведения; новый пользовательский путь/действие возвращается в Specification.

**Completion:** DEV знает, какие экраны и состояния реализовать, где источник токенов и какой вариант принят.

**Skill:** вынести подробности сетки, типографики, forms/modal/focus и метод визуальной проверки в доступный ui-design skill или подтвержденные внешние skills. Сохранить проектные ограничения. Не объявлять сетку 8px универсальным обязательством всех проектов.

**Flow card:** UI scenarios → frontend refinement/HTML artifact → customer selection (если требуется) → Planning/DEV → конечная валидация готового фронта по принятому HTML-макету. Независимые backend-задачи не должны ждать UI, если зависимости этого не требуют. Финальная HTML-сверка — обязательный для UI-дельты элемент целевой модели, а не необязательное украшение.

**Приемка:** неизвестное поведение modal не изобретается незаметно; выбранный mockup имеет version/hash; непроверенная accessibility помечена честно.

### 6.6. Task Planner / Execution decomposition

**Главное структурное изменение:** выделить tasks.md из SA в собственное окно после валидированного design. Предлагаемые новые файлы: agents/task_planner_agent.md, skills/task-planning/SKILL.md и контракт execution-unit. Это будущие файлы, не существующие API.

**Purpose:** design → минимальный достаточный DAG исполнимых задач.

**Вход:** согласованные specs/design, architecture review, UI contract для соответствующих задач, current code map.

**Запись задачи:**

```yaml
# Предлагаемый контракт, согласовать со schema и текущим tasks.md.
task_id: T-2.3
goal: One observable or technical outcome
source_refs: [FR-1, requirement_ref, scenario_ref]
input_refs: [design_section, api_contract_ref]
depends_on: [T-2.1]
write_scope: [specific/path]
read_scope: [relevant/path]
interface_constraints: [contract_ref]
acceptance: [falsifiable_condition]
verification: [command_or_procedure_ref]
out_of_scope: [neighbor_task_decision]
block_on: [missing_contract, product_ambiguity]
```

**Преобразование:** обеспечить покрытие дельт; выделить зависимости данных/интерфейсов/артефактов; определить write scopes; отличить техническую независимость от возможности параллельной записи.

**Правило размера:** задача достаточно мала для одного окна, но не дробится на бессмысленные микрокоммиты. Если для выполнения требуется выбрать API соседней задачи — decomposition не завершена.

**Authority:** дробить, объединять и упорядочивать исполнение; не менять поведение/архитектуру.

**Completion:** DAG без циклов, источники покрыты, зависимости существуют, shared files сериализованы; каждое leaf-окно имеет достаточный вход. [P] вычисляется/проверяется из зависимостей и зон, не из интуиции.

**Flow card:** validated solution → task planning → dev_task per leaf. Добавить роль/stage/bundle/zone/acceptance только после обновления specs/contracts/runtime.

**Приемка:** две задачи, пишущие один shared файл, не запускаются одновременно; неизвестный API возвращается Solution; задача с отсутствующим FR обнаруживается.

### 6.7. DEV / Materialization

**Файлы:** agents/dev_agent.md, skills/implementation/SKILL.md.

**Purpose:** материализовать одну execution unit, сохранив поведение и окружающие ограничения.

**Вход:** задача, source refs, technical contracts, принятые зависимости, worktree и зарезервированная зона.

**Выход:** code delta, локальные проверки, task status/evidence, локальный commit. Публикация ветки и PR — по текущему owner/push policy.

**Authority:** локальные технические решения в своей задаче; нельзя решить продуктовую неопределенность или перепроектировать интерфейс соседней задачи. Недостаточная decomposition возвращается Planner.

**Completion:** delta реализует acceptance, не нарушает контракты; diff в зоне; проверка привязана к SHA; незакрытые условия не скрыты.

**Skill:** сохранить методы implementation и исправления замечаний; универсальный метод отделить от fast line, NFR-5 и других требований пилотного проекта.

**Flow card:** accepted dependencies → dev_task → code_review → accept/return. Worktree/reservation доставляет runtime; агент проверяет полученные границы. Пока runtime не делает нужное сам, операционная инструкция остается доступной.

**Shared tasks.md:** параллельные DEV не должны писать общий чекбокс без согласованной механики. Рассмотреть отдельные task-result артефакты и обновление статуса оркестратором, затем мигрировать policy и проверку.

**Приемка:** нехватка контракта дает BLOCKED, а не самовольную реализацию; соседний «маленький фикс» выявляется zone-check/review.

### 6.8. Code reviewer / Independent falsification

**Файлы:** agents/code_reviewer_agent.md, skills/code-review/SKILL.md.

**Purpose:** найти контрпример утверждению «delta полностью реализует задачу и сохраняет ограничения».

**Вход:** task/spec/design refs, base/head SHA и diff digest, процедура проверки, evidence прогонов.

**Преобразование:** проверка поведения, негативных ветвей, интеграции, регрессий, scope и claims документации.

**Выход:** approve/return + конкретные замечания с источником, местом и воспроизведением; provenance записывается уполномоченным runtime.

**Authority:** принять/вернуть; не писать код автора и не менять spec. Стиль — замечание только при нарушении принятой нормы или конкретном риске.

**Completion:** все назначенные оси реально проверены; blocker/major отсутствуют для approve; неопределенность не маскируется как доказанная корректность. «Не нашел контрпример» само по себе недостаточно без процедуры и coverage scope.

**Контекст:** не передавать всю историю рассуждений автора; сохранять важные factual notes, known limitations и evidence. Независимость не означает лишение данных для воспроизведения.

**Skill/runtime:** сохранить актуальное правило статического review и вынесения длительных прогонов в оркестратор. Reviewer проверяет соответствие evidence SHA/env/scope; недостающее проверяет разрешенными короткими процедурами или запрашивает прогон. Не повторяет автоматически полный долгий suite.

**Flow card:** dev delta → code_review/accept_review → merge_task либо return DEV. Новый commit инвалидирует старое review evidence.

**Приемка:** seeded defect дает конкретный counterexample; исправленный diff требует новой связки evidence, само-review блокируется.

### 6.9. QA checklist / Verification obligations

**Файл:** agents/qa_checklist_agent.md.

**Purpose:** spec → модель проверяемых обязательств.

**Вход:** актуальная версия spec и change, impact decisions для измененного поведения.

**Выход:** текущий test-model/checklists/<id>.md с CHK IDs. Сохранить имя пути для совместимости; семантически это verification model.

**Запись CHK:** source Requirement/Scenario/FR, проверяемое утверждение, oracle, класс проверки, риск/приоритет, partitions/states при необходимости.

**Completion:** каждое наблюдаемое обязательство покрыто проверкой или явным согласованным исключением. Requirement ≥1 CHK — полезная структурная проверка, но не доказательство полноты сценариев.

**Authority:** выбирать техники проверки, не дописывать недостающий бизнес-oracle.

**Skill:** выделить метод obligations: equivalence classes, boundaries, state transitions, actor matrix, negative classes и traceability. Если отдельного skill нет, создать после проверки бандлов.

**Flow card:** spec/impact → qa_checklist → qa_cases; непроверяемая spec возвращается Specification.

**Приемка:** несколько разных обязательств в одном Requirement не скрываются одним формальным CHK; неизвестный oracle фиксируется как defect spec.

### 6.10. QA case author / Scenario decomposition

**Файлы:** agents/qa_case_author_agent.md, skills/test-case-design/SKILL.md.

**Purpose:** обязательства → воспроизводимые сценарии.

**Вход:** CHK, spec, API/data contracts, ограничения стенда.

**Выход:** один TC = один файл в test-model/new/<id>/; предусловия, действия, конкретные данные и oracle.

**Целевая связь:** CHK 1 → N TC, когда разные partition/actor/state требуют разных сценариев. Сначала сохранить существующее 1:1, затем отдельным change изменить specs, contracts, scripts/validators, templates, prompts, traceability и fixtures вместе. Не включать 1:N одной правкой prompt.

Для первого перехода каждому TC назначать один основной CHK; многозначную связь N:M не вводить без отдельной потребности. Полноту определяет coverage partitions, не количество файлов.

**Authority:** выбрать данные и шаги в пределах поведения; дефект CHK возвращается checklist owner; отсутствие oracle возвращается Specification.

**Completion:** другой исполнитель воспроизводит сценарий без догадок; partitions CHK представлены; нет противоречивых ожиданий.

**Skill:** добавить правила дробления, таблицу partitions → TC и примеры 1:N. Сохранить конкретность данных, атомарность шагов, негативные ветви.

**Flow card:** qa_checklist → qa_cases → qa_review; перенос в approved не право автора.

**Приемка:** один CHK «границы длины» естественно развернут в несколько TC; ни один обязательный partition не исчезает.

### 6.11. QA case reviewer / Verification falsification

**Файлы:** agents/qa_case_reviewer_agent.md, skills/case-review/SKILL.md.

**Purpose:** опровергнуть claims о корректности, воспроизводимости и полноте TC относительно obligations/spec.

**Выход:** append-only review по версии cases; approve/return, затем разрешенный перенос approved.

**Проверять:** source trace, oracle, данные, предусловия, однозначность шагов, partitions/negative coverage, отсутствие придуманного поведения. Сохранять G8-проверку автотестов до обоснованного выделения отдельного окна.

**Authority:** принимать или возвращать; не исправлять cases автора. Перенос и provenance должны учитывать rename/изменение пути, сохраняя проверяемую идентичность содержания.

**Completion:** утвержден именно проверенный content; mixed approved/new batches не позволяют принять непроверенные files.

**Skill:** добавить falsification questions и partition coverage вместо проверки механического 1:1 после миграции.

**Flow card:** new cases → qa_review → approved → qa_automation; return → author. Батчи ревью сохраняют общий coverage manifest.

**Приемка:** недостаточное oracle или пропущенный partition дает return; content после approve изменен → stale evidence.

### 6.12. QA automation / Executable assertions

**Файлы:** agents/qa_automation_agent.md, skills/test-automation/SKILL.md.

**Purpose:** approved scenario → исполнимая детерминированная проверка.

**Вход:** принятые TC с review evidence, проектный test stack, контракты и инструкции стенда.

**Выход:** tests, TC traceability, run evidence и классифицированные defect reports.

**Authority:** реализация теста/фикстур; нельзя ослаблять oracle под текущий код или править продукт.

**Completion:** каждое утверждение TC представлено assertion либо проверенным эквивалентом; все approved TC учтены; результаты PASS/FAIL/ERROR/SKIPPED различимы. SKIPPED не выдается за покрытое поведение.

**Skill:** отделить универсальную методику от профилей pytest/requests/Playwright. Текущий стек пилота сохранить. Проверить согласованность примеров: обещание проверки JWT не должно материализоваться только assert наличия token.

Классифицировать падение: product defect / test defect / environment defect / spec ambiguity. Фраза «верный тест падает» не доказывает автоматически продуктовый баг — требуется воспроизводимое сравнение expectation/fact.

**Flow card:** approved → qa_automation → test-code review / integration evidence. Баги возвращаются по актуальному flow.

**Приемка:** тест с зависимостью от порядка обнаруживается; fixed sleeps не появляются; падение env не записывается как доказанный баг продукта.

### 6.13. QA impact analyst / Verification delta

**Файл:** agents/qa_impact_analyst_agent.md.

**Purpose:** behavior delta + существующая test model → решения об обновлении проверок.

**Выход:** test-model/impact/<id>.md, keep/revalidate/retire с причиной, source refs и затронутыми TC/tests.

**Authority:** определить impact; не редактировать тесты/кейсы без соответствующей стадии.

**Completion:** каждое затронутое обязательство имеет судьбу, replacement/update owner и условие восстановления покрытия.

Не допускать, чтобы revalidate молча снял обязательную проверку с релизного набора. Pending update учитывается как coverage gap до замены/явного решения.

**Flow card:** семантически impact нужен до формирования обновленного QA scope. Сначала сверить действующий STAGE_TABLE: в текстовых картах порядок может отличаться. Перестановка — только через spec/runtime migration.

**Приемка:** удаление поведения retire соответствующий тест с аудитом; изменение actor permissions приводит к revalidate, даже если endpoint прежний.

### 6.14. Design validator / Visual conformance

**Файл:** agents/design_validator_agent.md.

**Purpose:** реализованный UI → evidence соответствия принятому HTML-макету и frontend contract. Заказчик отдельно отметил, что такая валидация хорошо показала себя на конечных этапах; сохранить этот самостоятельный фокус и не растворять его в code review или DOM-тестах.

**Вход:** selected design version, tokens, UI delta, стенд конкретного SHA.

**Выход:** review с screenshot/computed-style evidence, source refs, approve/return.

**Authority:** искать расхождения; не менять CSS и не устраивать редизайн.

**Completion:** проверены необходимые страницы/состояния/viewport; неподтвержденные состояния честно отмечены.

**Skill:** вынести Georgia, V3, терракотовый цвет и frontend/static/css/app.css из универсального prompt в контекст ekotov-wiki. Факт наличия «не-дефолтных CSS» не универсальный критерий качества: native control допустим, если предусмотрен дизайном.

**Flow card:** после интеграции UI-дельты на стенде проверяемого SHA, в конечном QA-контуре: готовый фронт + selected HTML mockup → visual validation → final acceptance/release evidence либо return DEV/UI contract owner. Точное место закрепить в runtime-графе. Проверять итоговый собранный фронт, а не только отдельный компонент до интеграции; значимая последующая UI-правка требует повторной проверки затронутой области.

**Приемка:** visual mismatch ловится даже при зеленом DOM suite; другой проект не получает требования палитры V3.

### 6.15. Dev Lead / Integration executor

**Файл:** agents/dev_lead_agent.md.

**Purpose:** принятые task deltas → согласованная интегрированная версия.

Выделять детерминированную механику постепенно: порядок по DAG, freshness reviews, gates, merge, cleanup и журналирование. LLM оставлять для анализа неформализованной причины блокировки; разрешение semantic conflict — отдельная ограниченная задача по утвержденному контракту, если разрешено.

**Выход:** integration SHA, полный manifest включенных tasks/reviews, gate evidence, статус worktrees.

**Completion:** каждый включенный delta принят, evidence актуально относительно проверяемых объектов; integration checks выполнены на итоговой версии. Merge не сохраняет автоматически все claims task-level checks.

**Flow card:** accepted tasks → merge_task → integration gates → QA/archive. Права push/main остаются действующими.

**Приемка:** детерминированный executor не принимает чужой/stale approve; сбой посередине восстановим; worktree с невлитым результатом не удаляется.

### 6.16. DevOps / Infrastructure and configuration refinement

**Файл:** agents/devops_agent.md. Роль уже существует в текущем tree; утверждение старого реестра «DevOps-агента нет» требует согласования, а не автоматического удаления роли.

**Purpose:** требования к системе + подтвержденные факты среды → согласованное инфраструктурное решение, конфигурации и эксплуатационные контракты. Фокус окна — инфраструктура, конфиги и сопутствующие механизмы: сервисы, сеть, процессы, зависимости, хранилища, переменные окружения, наблюдаемость, backup/restore, поставка и восстановление. Не сводить DevOps к подготовке релиза.

**Вход:** NFR, solution/architecture constraints, topology facts, текущие конфиги, runbook и access boundaries; для release-задачи дополнительно target SHA и release constraints. Нужен и ранний вызов до DEV/Planning, если инфраструктурные решения определяют исполнимость задач.

**Выход:** инфраструктурные схемы/контракты, конфиги и их templates, перечень проверенных env/dependency assumptions, а для поставки — deploy/runbook/rollback/smoke artifacts с evidence, dry-run и проверками на безопасном стенде. Расширенные пути инфраструктурных артефактов сначала согласовать с role zones; текущие deploy/** и ops/** не расширяются этим описанием автоматически.

**Authority:** собирать факты разрешенным чтением, готовить скрипты; production write не становится разрешенным из-за наличия нового profile.

**Skill:** project-specific ops knowledge отдельно от универсальных процедур. Не помещать секреты в context package или артефакты.

**Completion:** инфраструктурные и конфигурационные предположения подтверждены или явно блокируют зависимые задачи; схемы/env/process contracts согласованы с приложением; пути/порты/пользователи проверены. Для поставки rollback и backup проверены в заданной области; dry-run не выдается за реальный deploy.

**Flow card:** ранняя ветвь — Solution/NFR → infrastructure/config refinement → Architecture/Planning/DEV; конечная ветвь — release candidate → ops preparation/review → customer approval → authorized execution → smoke evidence. Одна смысловая ответственность, разные точки вызова по зависимости. Конфиги проходят review, итоговое окружение — проверку фактических параметров.

### 6.17. PM / Semantic orchestration

**Файл:** agents/pm_agent.md.

**Purpose:** определить следующее разрешенное преобразование и собрать достаточный вход для него.

**Вход:** цель, состояния артефактов, DAG, approval refs, runtime facts, бюджеты/ограничения текущей фазы.

**Выход:** delegation/context manifest, journal, acceptance/return decision и понятная эскалация.

**Authority:** выбирать ready task и возвращать дефект владельцу; не исполнять все роли в своем окне и не принимать новые фазы без существующего разрешения.

**Skill/runtime:** унести многократно повторяемую механику prepare/reserve/gates/watchdog/cleanup в executor; сохранить у ПМ понимание результата и исключений.

**Completion:** нет делегации с неполным входом/невалидной зоной; отчет сверяется с файлами и evidence; фаза не продолжается за границей разрешения.

**Flow card:** next semantic stage определяется графом + state machine + approval constraints. LLM не выбирает legal transition вопреки runtime.

**Приемка:** ПМ корректно возвращает behavioral ambiguity в Specification, decomposition defect в Planner и env defect runtime-владельцу.

### 6.18. Regression analysis и archive/release

В agents/README.md упомянут регресс-аналитик, но отдельного prompt в текущем tree нет. Не считать его уже работающей ролью: проверить реальную установку и потребность.

Regression decisions должны опираться на поведение/риски, а не удалять тесты только ради скорости. candidate-archive — предложение, не разрешение уничтожить evidence.

Архивация сохраняет действующий контракт 7: accepted implementation + QA + разрешение → слияние дельт master-spec → archive. Не переносить master-spec в будущее состояние до выполнения условий.

Уточнить ownership archive между SA/dev_lead/runtime через нормы. Release decision отдельно от archive: актуальная spec не означает автоматическое разрешение выпуска. Обязательный SKIPPED gate, неизвестная защита main или открытый coverage gap остаются явными фактами.

## 7. Переработка skills: конкретные действия

| Существующий skill | Сохранить | Добавить/отделить |
|---|---|---|
| requirements-elaboration | Elicitation, FR/NFR, MoSCoW | Uncertainty register, source classification, blocking ambiguity |
| openspec-authoring | Форматы, CLI, delta semantics | Разделы behavior/solution/planning/archive с загрузкой по стадии |
| implementation | Реализация и локальная проверка задачи | Чтение execution-unit contract; project assumptions в project context |
| code-review | Оси проверки, воспроизведение, замечания | Falsification procedure, SHA-bound evidence, scope долгих прогонов |
| test-case-design | Данные, шаги, oracle | Partitions → несколько TC после совместной миграции 1:N |
| case-review | Traceability и воспроизводимость | Coverage obligations/partitions, content/version evidence |
| test-automation | Fixtures, assertions, isolation | Универсальное ядро + test stack profiles, классификация падений |
| factory-flow | Навигация, блокеры, эскалации | Компактные role cards + полный reference; generation/drift check |

Для каждого внешнего skill, упомянутого в prompts (claude-design, design-md, dogfood, architecture-diagram, codebase-inspection, ekotov-wiki-ops, hermes-agent), проверить: установлен ли, версия, доступен ли delegate, как загружается, стоимость и права. Отсутствие в этом репозитории не доказывает отсутствие в Hermes.

Новые skills создавать только там, где есть отдельная повторяемая методика. Не создавать skill из одной строки purpose и не копировать runtime manual в несколько role skills.

Для E16 recovery сохранить stop-on-repeat правило; запись improvements вне зоны проекта должна иметь отдельный разрешенный канал. При недостаточной write scope агент сообщает observation в отчете, а runtime записывает append-only improvement. Не расширять зону молча ради логирования.

## 8. Hermes profiles: сначала capability audit

### 8.1. Обязательный аудит установленной версии

Не считать YAML из обсуждения готовой конфигурацией Hermes. До реализации агент на машине фабрики:

1. Фиксирует версию/commit Hermes, текущие settings и установленный delegate_task schema без вывода секретов.
2. Читает фактическую реализацию/документацию delegate_task и загрузки role prompts/skills.
3. Проверяет изоляцию контекста, наследование tools/env/cwd/skills, параметры model/reasoning, лимиты, timeout/cancel, async resume и persistence.
4. Заполняет capability matrix: свойство → native support → factory adapter → enforcement → evidence test.
5. Все неподдерживаемые свойства обозначает явно. Prompt-инструкция о запрете shell/network не является sandbox.

Эта проверка нужна по актуальной версии на VPS. В данной инструкции параметры Hermes намеренно не заявлены как подтвержденные.

### 8.2. Предлагаемая декларация AI Factory

```yaml
# Factory-owned profile, НЕ native Hermes config.
profile_version: 1
agent: dev
semantic_contract: contracts/agents/dev.md
flow_stage: dev_task
prompt: agents/dev_agent.md
skills: [implementation, factory-flow]
context:
  strategy: manifest
  include_parent_chat: false
  scope: execution_unit
authority:
  product_decisions: false
  local_technical_decisions: true
write_scope:
  source: task_manifest
runtime:
  cwd_source: reserved_worktree
  push_owner: orchestrator
  delegation_allowed: false
execution_preferences:
  reasoning_class: medium
  model_class: implementation
completion:
  artifacts_required: true
  mandatory_gates_required: true
```

reasoning_class/model_class — логические предпочтения фабрики. Адаптер сопоставляет их с реальными параметрами провайдера/версии Hermes; не отправляет неизвестные поля в delegate_task.

Разделить **requested / effective / enforced** capabilities в runtime report. Например: requested network=false, effective network=true, enforced=false — это заметный конфликт, а не тихая «успешная настройка».

Fail closed на неподдерживаемом свойстве, критичном для прав/изоляции. Для preferences разрешен документированный fallback. Temperature/creativity/adversarial mode не придумывать как API-параметры; adversarial objective можно выразить в semantic prompt.

### 8.3. Матрица профилей

| Окно | Начальный reasoning preference | Контекст | Запись |
|---|---|---|---|
| BA | высокий для противоречий | Intent, source decisions, scope | Requirements/answers |
| Specification | высокий | Requirements + relevant master-spec | Behavior deltas |
| Solution | высокий | Spec + architecture + project facts | Design/contracts |
| Planner | высокий при сложном DAG | Accepted design + code boundaries | Tasks/context manifests |
| DEV | средний, повышать по измерениям | Одна задача и связанные constraints | Task scope |
| Review | высокий на рискованных delta | Task/spec/diff/evidence | Review artifacts |
| QA author | средний | CHK partitions/contracts | New cases |
| QA automation | средний | Approved cases + test profile | Tests/bug reports |
| Deterministic integration | LLM не требуется для механики | DAG + evidence | Integration state |

Параметры выбирать по измерениям качества/стоимости, не по должности. На одном VPS лимитировать тяжелые стенды и tool workloads отдельно от количества LLM contexts.

## 9. Context compiler

### 9.1. Минимальный жизнеспособный вариант

Сначала генерировать manifest путей/секций и версий, не сложный retrieval engine:

- stage, flow_id, change_id, task_id;
- base/head SHA и versions/digests входов;
- semantic prompt + role flow card;
- обязательные skills и способ загрузки;
- task/source refs, related spec scenarios;
- API/data/design/architecture constraints;
- allowed write scope + worktree;
- approval_refs, runtime preflight facts;
- expected output, gates, escalation route.

Малый goal указывает на manifest. Ссылки на файлы не дают экономии, если агент затем читает целиком все документы: измерять реально загруженный контекст.

### 9.2. Правила полноты

Минимальность подчиняется достаточности. Помимо прямых ссылок включать общие constraints: auth, isolation, transactions, NFR, error semantics. Один task fragment без общих инвариантов опасен.

Агент может запросить расширение read context с причиной; это не дает права расширить write scope. На старте лучше переизбыток релевантных данных, чем агрессивная обрезка.

При передаче фрагментов указывать path, section/source IDs, version/hash; исходный файл доступен для проверки. Устаревший manifest пересобирается.

Retry/dorabotka получает fresh input manifest + review refs + текущий SHA. Передача только блоков 5–7 старого шаблона допустима лишь при гарантированно сохраненном контексте; новое окно не знает прежнюю задачу.

### 9.3. Reviewer context

Исключить длинное самообоснование автора; включить delta, contract, воспроизводимые facts и ограничения. Полный прогон evidence содержит SHA, environment, command, result, scope, timestamp и digest inputs; числа без provenance недостаточны.

## 10. Порядок миграции: отдельные reviewable change-пакеты

Каждую стадию запускать в пределах разрешенной фазы. Не реализовывать весь документ одним большим коммитом.

### M0. Baseline и карта расхождений

**Работа:** инвентаризировать prompts, local/external skills, bundles, contracts, runtime stage table и зоны; собрать несколько известных успешных/неуспешных делегаций.

**Артефакты:** inventory, conflict register, capability audit plan, baseline metrics.

**Особенно сверить:** push policy dev, наличие DevOps, ownership archive/merge/architecture review, порядок impact analysis, E16 write zone, общий tasks.md/SDD, reviewer long-suite policy.

**Приемка:** все реальные роли учтены; неизвестное отмечено; противоречия не «исправлены» выбором удобного текста.

### M1. Agent Contract v2 + flow cards

**Работа:** согласовать semantic/flow шаблоны; применить к BA, SA и DEV без изменения runtime маршрута.

**Артефакты:** templates, role prompts, reference mapping, equivalence checklist.

**Приемка:** сохранены права, flow awareness, gates и escalation; replay проверяет раннее обнаружение неверного входа.

**Откат:** предыдущие prompt versions; runtime неизменен.

### M2. Разделение SA и выделение Planner

**Работа:** специфицировать behavior/solution/planning границы; сначала раздельные запуски, затем отдельная роль Planner при выполнении критериев роли.

**Артефакты:** OpenSpec change, contract updates, task schema, planner skill/prompt/bundle, zones и runtime tests.

**Приемка:** Planner не начинает по невалидированному design; DAG корректен; DEV получает достаточную execution unit; parallel writes не пересекаются.

**Совместимость:** старые change-пакеты продолжают работать по старой версии контракта. Версию выбирает manifest; не переинтерпретировать tasks.md задним числом.

### M3. Остальные prompts/skills

**Работа:** Solution/Architect/UI, оба reviewers, QA pipeline, impact/design validator/DevOps/PM по разделу 6.

**Приемка:** у каждого окна одна основная ответственность; project knowledge отделено; skill availability подтверждена; flow cards присутствуют.

**Откат:** prompt/profile pinning, без удаления существующих артефактов.

### M4. QA cardinality 1:N

**Работа:** согласованный change specs/contracts/validators/templates/prompts/test fixtures.

**Приемка:** legacy 1:1 валиден; новый 1:N валиден; orphan TC/CHK и пропущенные обязательные partitions отклоняются. История IDs/review сохраняется.

**Откат:** прекратить создание новых 1:N пакетов; уже принятые не ломать возвратом старого валидатора.

### M5. Profiles и Hermes adapter

**Работа:** завершить capability audit; profile schema/validation, requested-effective-enforced report, адаптер delegate_task.

**Приемка:** unsupported fields не игнорируются; cwd/context/zone/delegation bounds проверены; secrets не попадают в manifest.

**Откат:** прежний подтвержденный launch path; права не расширяются.

### M6. Context compiler

**Работа:** начать с DEV и reviewer; manifest completeness/freshness, затем Planner/QA.

**Приемка:** context не теряет cross-cutting constraints; stale input отклоняется; метрики показывают экономию без роста дефектов/возвратов.

**Откат:** полный прежний explicit input package с теми же scopes и approval rules.

### M7. Детерминированное исполнение механики

**Работа:** переносить повторяемые операции PM/Dev Lead в executor по одной: prepare/reserve, acceptance evidence, merge, cleanup/reconcile.

**Приемка:** идемпотентность, восстановление после crash, freshness checks, запрет удаления незавершенной работы; LLM не нужен для happy-path механики.

**Откат:** прежний исполнитель той же policy. Enforcing не выключать ради отката.

### M8. Сквозной пилот и закрепление

**Работа:** небольшой brownfield change с поведением, несколькими task nodes и QA; отдельный UI и ops кейс по необходимости.

**Приемка:** полная traceability, независимый review, зеленые обязательные gates, честные SKIPPED/UNKNOWN, корректная архивация и отсутствие самовольного release.

**Результат:** metrics comparison, обновленный реестр/документация, наблюдения в backlog, решение Заказчика о масштабировании. Для UI-пилота обязательна конечная сверка собранного фронта с HTML-макетами; для инфраструктурного — проверка согласованности конфигов и фактического окружения.

## 11. Сквозной пример: изменение срока сессии

Иллюстрация целевого конвейера, не новое требование текущего продукта.

1. **Intent:** «После простоя пользователь должен заново войти».
2. **BA:** уточняет idle или absolute timeout, величину, роли, сохранение незавершенных данных; фиксирует решения, а не выбирает значения молча.
3. **Specification:** описывает активную/истекшую сессию, запрос после истечения, параллельные запросы и UI-переход; связывает с FR.
4. **Solution:** выбирает механизм учета времени, общий auth contract и migration policy, сохраняя заданное поведение.
5. **Architect:** проверяет кеши, clock assumptions и влияние на существующую авторизацию.
6. **Planner:** отделяет backend expiry, UI handling и миграцию; фиксирует API errors до запуска DEV; shared auth файлы сериализует.
7. **DEV:** реализует свой leaf, не меняет длительность timeout или UX соседней задачи.
8. **Code reviewer:** ищет контрпример — например, обход expiry при втором типе запроса.
9. **Impact:** определяет судьбу существующих auth TC.
10. **QA obligations:** границы до/в момент/после expiry, продление при активности, actor/state partitions.
11. **QA author:** несколько TC на один CHK границ, если 1:N уже включено.
12. **QA reviewer/automation:** валидируют oracle и используют управляемые часы/подходящий test seam вместо ожидания реального timeout.
13. **Integration/archive:** проверяет итоговую версию, обновляет master-spec; release — отдельное разрешенное действие.

## 12. Метрики и meaningful verification

Собирать по stage/profile/version и сложности задачи:

| Метрика | Что показывает |
|---|---|
| Input rejection и причина | Качество предыдущего handoff |
| Product decisions, сделанные DEV | Недостаточность BA/spec/design/planning |
| Возвраты после review | Качество реализации и контрактов |
| Контекст tokens + calls to first useful action | Цена входа и «тыканье» |
| Wrong stage / out-of-zone attempts | Качество flow awareness |
| Tool retry loops / environment failures | Качество runtime подготовки |
| End-to-end стоимость и latency | Экономика полного конвейера |
| Defects escaped after approve | Ограничения reviewers/QA |
| Coverage gaps и mandatory skipped | Реальная полнота verification |
| Stale evidence failures | Корректность управления версиями |

Не принимать уменьшение prompt как успех без end-to-end сравнения. Baseline и pilot должны иметь сопоставимую сложность. Количество контекстных окон само по себе не показатель качества.

Для runtime/schema changes нужны тесты реальных отказов: missing input, invalid approval, stale SHA/digest, wrong role, zone overlap, cyclic DAG, unsupported capability, crash/reconcile. Для prompt-only правок важнее scenario replay с проверкой содержательных решений, чем тест совпадения строк.

Нужны также semantic checks: seeded product ambiguity, conflicting requirements, missing API contract, missed boundary partition, visual mismatch. Они не заменяются structural validators.

## 13. Пакет передачи агенту-исполнителю

Первый запуск — **только M0**, если Заказчик не разрешил больше. В goal передать:

- этот файл и актуальный base SHA;
- scope M0, flow_id и существующие approval refs;
- paths sources, runtime availability и read/write boundaries;
- ожидаемые inventory/conflict/baseline артефакты;
- запрет менять действующий flow/enforcing и prompts в рамках аудита;
- результат: конкретный план M1 с изменяемыми файлами, verification и rollback.

После M0 подготовить следующий change-пакет по действующему процессу. Не трактовать «реализуй план» как разрешение отменить customer phase gates, права production write или независимость review.

## 14. Итоговый acceptance checklist миграции

- [ ] Для каждой реальной роли описаны transformation, authority и completion.
- [ ] Flow awareness сохранен; role cards соответствуют исполняемым правилам.
- [ ] Все semantic/runtime изменения прошли spec → contract → implementation.
- [ ] Нет расходящихся policy sources и неподтвержденных capabilities.
- [ ] Planner действительно компилирует достаточные context units.
- [ ] QA 1:N введено совместимо, без потери legacy traceability.
- [ ] Project-specific знания доступны из context, а не захардкожены глобально.
- [ ] Reviewer evidence независим и связан с конкретной версией.
- [ ] Длительные прогоны не дублируются без причины.
- [ ] Mandatory SKIPPED/UNKNOWN не становятся PASS.
- [ ] Worktree/reservations/recovery сохраняют невлитые артефакты.
- [ ] Нет автоматического расширения прав, phases или production access.
- [ ] Пилот доказал улучшение качества/экономики относительно baseline.

## 15. Уточнения после повторной проверки

### 15.1. As is и change-пакет

Постоянные артефакты сохраняются: master-spec, архитектура/ADR, системные/API/data contracts, принятый дизайн и HTML-макеты, тестовая модель, API/UI автотесты, инфраструктурные конфиги и runbook. Change содержит дельты и evidence. Closure требует согласованной актуализации всех impacted видов; unchanged/not_applicable имеют явное обоснование. Наличие archive/spec merge не доказывает актуальность остальных артефактов. См. отдельное задание as_is_change_consistency_task.md.

Различать accepted code baseline и deployed state по окружениям. Manifest связывает реальные версии и evidence, а не заменяет их. Исторический archived change проверяется на своем result revision: поздние легальные изменения master не должны ломать историческую проверку.

### 15.2. Контролируемые API и UI тесты

Сохранить API pytest/requests и UI pytest/Playwright. Это обязательные контуры для соответствующего поведения, а не выбор автоматизатора. Каждый CHK/TC получает verification layer; cross-layer behavior покрывается обоими. Coverage и run results учитывать отдельно. API PASS не компенсирует отсутствующий UI scope. Обязательный SKIPPED/ERROR — gap.

Каждый runnable продуктовый тест связан с конкретным approved TC; TC review привязан к content/version; изменения oracle требуют повторного review. Автотесты проходят независимое test-code review. Конечная HTML-сверка собранного фронта — отдельное evidence и не заменяет Playwright. Для unit tests инфраструктуры фабрики определить честный отдельный контракт вместо фиктивных TC-ID.

### 15.3. Подтвержденные расхождения runtime

На проверенном SHA architecture_review закреплен в STAGE_TABLE за pm; отдельный architect уже существует. docs/README-flow-control.md помещает impact до checklist, STAGE_TABLE перечисляет impact после qa_review. Archive runtime допускает sa/dev_lead/integrator. Перед изменением потока согласовать причинные проверки и тексты; позиции в списке сами по себе не доказывают строгий enforced order.

### 15.4. Порядок включения

As-is reconciliation — самостоятельный change-пакет, который можно выполнять до выделения Planner. M0 должен учитывать отдельное задание; новые stages не вводить без согласованных output/baseline contracts. Экономия context и устранение LLM из интеграции остаются гипотезами до пилотных измерений. Статический аудит не подтверждает capabilities установленного Hermes или фактическую полноту пилотного проекта.

