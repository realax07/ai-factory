# Deterministic Flow Control Specification

## Purpose

Исполняемая модель состояния и переходов конвейера: по репозиторию, Git и реестру
сессий система объясняет, что доказано, какие действия разрешены, какой агент может
их выполнить и почему действие заблокировано. Самоотчет агента не является
доказательством; источники фактов — Git, файлы, результаты gates, реестр сессий.

## ADDED Requirements

### Requirement: Снимок состояния по scope
Система MUST предоставлять чистую операцию `inspect(repo, scope) -> FlowSnapshot`,
вычисляющую состояние для области `repo + project + flow(1–5) + change/BUG/chore +
task`. Snapshot MUST содержать `schema_version`, `scope`, `repo_head`, `dirty_paths`,
`registry_digest`, `facts` (каждый факт: key, value, source, observed_at,
fingerprint, confidence ∈ {verified, unknown}), `problems`, `snapshot_digest`.
Операция MUST NOT выполнять записей, fetch, checkout, запуск агентов.

#### Scenario: Повторный вызов на неизменном вводе
- **GIVEN** репозиторий и реестр не менялись между вызовами
- **WHEN** `inspect` вызван дважды с одним scope
- **THEN** JSON-выдача эквивалентна (временные поля исключены из digest)

#### Scenario: Отсутствующий реестр сессий
- **GIVEN** файл `active_sessions.json` отсутствует или содержит битый JSON
- **WHEN** выполняется `inspect`
- **THEN** соответствующий факт помечен `unknown` с кодом проблемы
- **AND** система не трактует это как «активных сессий нет»

#### Scenario: Попытка записи при inspect
- **GIVEN** репозиторий чист перед вызовом
- **WHEN** `inspect` выполнен
- **THEN** `git status` не изменился и ни один файл не создан

### Requirement: Разрешение действия
Система MUST предоставлять чистую функцию `check_action(snapshot, action) -> Decision`.
Decision MUST содержать `allowed`, `status ∈ {ALLOW, DENY, UNKNOWN}`, `action`,
`scope`, `actor_role`, `snapshot_digest`, `blocking_reasons` (стабильные коды),
`required_gates`, `evidence_refs`, `next_candidates`. UNKNOWN MUST NOT разрешать
исполнение. Стабильные коды причин: `MISSING_INPUT`, `INVALID_GATE`,
`HUMAN_APPROVAL_REQUIRED`, `WRONG_ROLE`, `ZONE_CONFLICT`, `STALE_EVIDENCE`,
`AMBIGUOUS_STATE`, `STALE_SNAPSHOT`, `EXTERNAL_ENFORCEMENT_UNKNOWN`.

#### Scenario: Действие с недостаточным evidence
- **GIVEN** в snapshot отсутствует факт, обязательный для действия
- **WHEN** `check_action` выполнен
- **THEN** decision = DENY с кодом MISSING_INPUT и путем к ожидаемому evidence

#### Scenario: Неоднозначное состояние
- **GIVEN** в snapshot два противоречащих факта одной стадии
- **WHEN** `check_action` выполнен
- **THEN** decision = UNKNOWN с кодом AMBIGUOUS_STATE, исполнение заблокировано

#### Scenario: Чужая роль
- **GIVEN** action содержит actor_role=dev, а действие зарезервировано роли
  code_reviewer
- **WHEN** `check_action` выполнен
- **THEN** decision = DENY с кодом WRONG_ROLE

### Requirement: Порядок флоу 1–5
Transition Validator MUST проверять порядок флоу по действующим контрактам:
Флоу 1 (утвержденные требования → change/SDD → architecture review → dev
task/review/merge → QA → archive → release), Флоу 2 (BUG-NNN + существующая спека;
изменение ожидаемого поведения/API → эскалация), Флоу 3 (аварийная стабилизация +
обязательный последующий PR-цикл), Флоу 4 (обслуживание без обхода PR/review),
Флоу 5 (экспресс по условиям BACKLOG/README + ретроспективные артефакты до
закрытия). Параллельная dev-задача допускается только при маркере `[P]`,
выполненных зависимостях и непересекающихся зонах.

#### Scenario: Dev до архитектурного ревью (Флоу 1)
- **GIVEN** change с утвержденными требованиями, но без architecture review
- **WHEN** запрошено действие dev_task
- **THEN** decision = DENY с кодом INVALID_GATE и указанием пропущенного этапа

#### Scenario: Независимые задачи ready одновременно
- **GIVEN** две задачи одного change, обе с `[P]`, зависимости выполнены
- **WHEN** запрошен `next`
- **THEN** обе задачи присутствуют в next_candidates

#### Scenario: Флоу 2 для нового поведения
- **GIVEN** BUG-изменение вводит новое ожидаемое поведение (дельта спеки)
- **WHEN** проверяется действие по Флоу 2 без эскалации
- **THEN** decision = DENY с указанием правила эскалации

### Requirement: Этапные ворота Заказчика
Действия, требующие решения Заказчика (старт нового change-пакета, релиз/фаза
релиза, новый релиз из backlog, работы вне утвержденного плана), MUST возвращать
DENY с кодом `HUMAN_APPROVAL_REQUIRED` при отсутствии зафиксированного решения,
относящегося к данному scope/фазе. Текст «ПМ считает согласованным» решением не
является. Разрешение ограничено указанной фазой и не переносится после её закрытия.

#### Scenario: Старт нового change без решения
- **GIVEN** нет зафиксированного решения Заказчика для scope
- **WHEN** запрошено действие create_change
- **THEN** decision = DENY с кодом HUMAN_APPROVAL_REQUIRED

#### Scenario: Решение другой фазы
- **GIVEN** решение Заказчика зафиксировано для фазы A
- **WHEN** запрошено действие фазы B, ссылающееся на то же решение
- **THEN** decision = DENY с кодом HUMAN_APPROVAL_REQUIRED

### Requirement: Честная граница enforcement
Система MUST различать локально проверяемое и внешнее: локальный PASS gates не
доказывает защиту main (branch protection). При недоступности подтверждения внешней
защиты релевантные решения MUST получать пометку `EXTERNAL_ENFORCEMENT_UNKNOWN`, не
повышающую статус разрешения.

#### Scenario: Локальный PASS без подтверждения branch protection
- **GIVEN** все локальные gates прошли, подтверждение branch protection недоступно
- **WHEN** формируется decision на merge
- **THEN** decision содержит EXTERNAL_ENFORCEMENT_UNKNOWN и не выдает защиту main
  за доказанную

### Requirement: Provenance review (строгий режим)
Approve ревью MUST приниматься только при соответствии task/change/SHA/diff и
независимой роли автора. До внедрения provenance-блока (поставка 05) переходы,
зависящие от идентичности diff, MUST возвращать UNKNOWN либо проходить отдельный
консервативный compatibility gate.

#### Scenario: Approve устарел после нового коммита
- **GIVEN** approve зафиксирован для SHA X, после чего появился коммит Y
- **WHEN** проверяется accept_review для Y
- **THEN** decision = DENY с кодом STALE_EVIDENCE (в строгом режиме) либо UNKNOWN
  (compatibility mode поставки 03)

#### Scenario: Автор ревьюит себя
- **GIVEN** author delegation == reviewer delegation
- **WHEN** проверяется accept_review
- **THEN** decision = DENY с кодом WRONG_ROLE

### Requirement: Восстановление после сбоя
Все компоненты MUST восстанавливаться из фактов (Git/файлы/реестр) после
прерывания процесса: состояние не хранится исключительно в памяти или логе. Audit-
события (JSONL) помогают разбору, но не являются единственным доказательством.

#### Scenario: Перезапуск после прерывания
- **GIVEN** процесс прерван между снимками
- **WHEN** компонент перезапущен
- **THEN** состояние вычислено заново из фактов без ручного вмешательства

### Requirement: Режим shadow (срез 1)
Поставки 01–03 MUST работать в режиме inspect/check/next без блокировок и без
запуска агентов. Расхождения с решениями ПМ фиксируются как данные для решения о
следующем срезе; переход в enforcement — отдельное решение Заказчика.

#### Scenario: Shadow не блокирует конвейер
- **GIVEN** срез 1 развернут на проекте
- **WHEN** ПМ выполняет любое действие конвейера
- **THEN** никакой компонент среза 1 не изменяет репозиторий и не блокирует работу
