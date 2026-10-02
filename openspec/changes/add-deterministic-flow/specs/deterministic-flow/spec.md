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

#### Scenario: Запись журнала решений валидна → ворота исполнены (P0.4)
- **GIVEN** в журнале решений репозитория есть запись
  `decisions/<YYYY-MM-DD>-<slug>.md` с машиночитаемым блоком
  `decision-record/1` (decision_id, date, scope: project/change_id/phase,
  action, commit — SHA на момент решения, source — дословная цитата/канал,
  опциональный expiration), и `approval_ref` = decision_id этой записи
- **WHEN** запрошено действие этапных ворот, и запись соответствует запросу:
  action записи покрывает запрошенное действие, scope записи покрывает scope
  запроса, SHA записи — предок текущего HEAD или равен ему, expiration не истек
- **THEN** ворота Заказчика считаются исполненными («решение зафиксировано»,
  НЕ «личность подтверждена»); запись журнала указана в evidence_refs решения

#### Scenario: Чужой или истекший decision_id → HUMAN_APPROVAL_REQUIRED (P0.4)
- **GIVEN** approval_ref ссылается на decision_id, записи которого нет в
  `decisions/`, или запись покрывает другое действие (action), другой scope
  (project/change_id/phase), или ее expiration истек, или ее SHA не является
  предком текущего HEAD
- **WHEN** запрошено действие этапных ворот
- **THEN** decision = DENY с кодом HUMAN_APPROVAL_REQUIRED (для SHA не из
  истории — STALE_EVIDENCE) и конкретной причиной: нет записи / чужой action /
  чужой scope / истекло / SHA не в истории; отказ называет формат
  (`decisions/<YYYY-MM-DD>-<slug>.md`, контракт §10)

#### Scenario: Произвольная строка approval_ref не является решением (P0.4)
- **GIVEN** approval_ref — непустая строка, не являющаяся decision_id записи
  журнала решений (ссылка «PLAN.md: погнали», пересказ ПМ)
- **WHEN** запрошено действие этапных ворот
- **THEN** decision = DENY с кодом HUMAN_APPROVAL_REQUIRED: непустая строка
  без записи журнала решением не является (сужение D5 — пересмотр плана P0.4);
  словарь customer_decision v1 остается допустимым для программных вызовов

#### Scenario: Журнал решений — не защищенная подпись (P0.4)
- **GIVEN** ворота Заказчика исполнены по валидной записи журнала решений
- **WHEN** формируется человекочитаемый отчет
- **THEN** решение описано как «решение зафиксировано», без утверждений о
  подтвержденной личности Заказчика или защищенной подписи (журнал в том же
  репо способен быть изменен общим пользователем — известное допущение)

### Requirement: Честная граница enforcement
Система MUST различать локально проверяемое и внешнее: локальный PASS gates не
доказывает защиту main (branch protection). При недоступности подтверждения внешней
защиты релевантные решения MUST получать пометку `EXTERNAL_ENFORCEMENT_UNKNOWN`, не
повышающую статус разрешения. Подтверждение внешней защиты — машиночитаемый факт:
адаптер `gate_runner.py github_protection` (решение А) вызывает GitHub Rulesets API
`GET /repos/{repo}/rules/branches/{branch}` и пишет JSON-отчет
`.flow-evidence/github-protection.json` (дата + HTTP-код + привязка к repo/branch/
HEAD + машиночитаемый разбор rulesets); факт учитывается только при свежести ≤ 24ч
и совпадении привязки. Защита подтверждена, когда среди активных rulesets есть
ruleset с `enforcement=active`, rules содержит `type=pull_request`, а обход ролью
не разрешен (`bypass` отсутствует или ни у одного элемента нет
`bypass_mode=always`).
Отрицательное подтверждение (404 / нет такого ruleset) MUST давать
DENY на merge/release с кодом `EXTERNAL_ENFORCEMENT_UNKNOWN` и деталью «защита
main не настроена» — это знание, а не незнание. Решения merge_task/release MUST
раздельно показывать локальную готовность (`local_ready` — ALLOW/DENY/UNKNOWN
по локальным фактам) и внешний enforcement (`external_enforcement` — PASS/DENY/
UNKNOWN по факту защиты). Если действие требует внешний факт (политика
`merge_requires_external`, по умолчанию включена), внешний UNKNOWN оставляет
общий статус UNKNOWN — скрытое превращение UNKNOWN в ALLOW запрещено. Архивация
change доказывается фактом `change.archived` (пакет
`openspec/changes/archive/<id>/` в репо, решение Б) при выполнении ВСЕХ условий:
каталог существует, каждый Requirement дельт пакета присутствует в
`openspec/specs/` (логика контракта 7, переиспользуется из flow_check), и
`openspec validate --all --strict` проходит; недоступность openspec CLI дает
unknown с причиной, не ready. Его отсутствие при release MUST давать
DENY/INVALID_GATE «release до архивации». Релизное решение Заказчика фиксируется
файлом `releases/<change-id>.md` (change-id + слово согласия + строка
«SHA: <hash>»/«commit: <hash>», решение В1): hash сверяется с актуальным HEAD
(допускается родитель коммита с записью — журнал фиксирует решение после
факта); при ready требование approval_ref на release считается исполненным.
Конфликт записей (два файла/две строки на один change с разными SHA) MUST давать
unknown с формулировкой AMBIGUOUS_STATE, а не молчаливый выбор одной записи.
Журнал решения в том же репо НЕ является независимым одобрением Заказчика:
в отчетах пишется «решение зафиксировано», не «личность подтверждена». При
полном комплекте фактов (архивация + релизное решение + свежее подтверждение
branch protection) переходы merge_task/release MUST достигать статуса ALLOW.

#### Scenario: Локальный PASS без подтверждения branch protection
- **GIVEN** все локальные gates прошли, подтверждение branch protection недоступно
- **WHEN** формируется decision на merge
- **THEN** decision содержит EXTERNAL_ENFORCEMENT_UNKNOWN и не выдает защиту main
  за доказанную

#### Scenario: Раздельный вывод local_ready и external_enforcement
- **GIVEN** все локальные факты merge чисты, факт branch protection отсутствует
- **WHEN** формируется decision на merge_task или release
- **THEN** вывод содержит local_ready=ALLOW и external_enforcement=UNKNOWN
  раздельно; общий статус UNKNOWN (политика merge_requires_external), а не
  скрытый ALLOW

#### Scenario: Полный комплект фактов
- **GIVEN** change заархивирован (openspec/changes/archive/<id>/ с слитыми
  дельтами и пройденным openspec validate --strict), релизное решение
  зафиксировано (releases/<change-id>.md с change-id, словом согласия и строкой
  SHA, совпадающей с HEAD), branch protection подтверждена свежим отчетом
  github_protection (ruleset enforcement=active + pull_request + без bypass always)
- **WHEN** запрошены действия merge_task (с чистым provenance) и release
- **THEN** оба решения имеют статус ALLOW без EXTERNAL_ENFORCEMENT_UNKNOWN

#### Scenario: Защита main не настроена
- **GIVEN** адаптер github_protection получил HTTP 404 (или среди активных
  rulesets нет ruleset с enforcement=active + rules type=pull_request +
  без bypass always)
- **WHEN** запрошены действия merge_task или release
- **THEN** decision = DENY с кодом EXTERNAL_ENFORCEMENT_UNKNOWN и деталью
  «защита main не настроена»

#### Scenario: Отчет branch protection устарел или чужой
- **GIVEN** отчет github-protection старше 24ч, без даты или привязан к другому
  repo/branch/HEAD
- **WHEN** запрошено действие merge_task
- **THEN** пометка EXTERNAL_ENFORCEMENT_UNKNOWN сохраняется (статус не выше UNKNOWN)

#### Scenario: Защита обходится ролью (bypass always)
- **GIVEN** активный ruleset содержит rules type=pull_request, но bypass
  элемент с bypass_mode=always
- **WHEN** адаптер github_protection разбирает ответ Rulesets API
- **THEN** protection_ok=False — защита, обходуемая ролью всегда, не считается
  подтвержденной

#### Scenario: Архивированный пакет с неслитыми дельтами
- **GIVEN** пакет в openspec/changes/archive/<id>/, но Requirement дельты
  отсутствует в openspec/specs/ (или openspec validate --strict падает)
- **WHEN** строится факт change.archived
- **THEN** факт invalid (дельты не слиты) или unknown (CLI недоступен, причина
  в значении факта), но не ready

#### Scenario: Конфликт записей релизного решения
- **GIVEN** на один change есть две записи с разными SHA (второй файл
  releases/<id>*.md или вторая строка SHA)
- **WHEN** строится факт release.approval
- **THEN** факт unknown с причиной AMBIGUOUS_STATE; release не разрешен выбором
  записи «на глаз»

#### Scenario: Решение без привязки к SHA или с чужим SHA
- **GIVEN** releases/<change-id>.md с change-id и словом согласия, но без
  строки SHA — или с SHA, которому предшествуют новые коммиты
- **WHEN** строится факт release.approval
- **THEN** факт invalid (привязка к версии работы отсутствует или устарела)

#### Scenario: Формулировка решения в отчете
- **GIVEN** факт release.approval ready
- **WHEN** формируется человекочитаемый отчет о release
- **THEN** решение описано как «решение зафиксировано», без утверждений о
  подтвержденной личности Заказчика

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
