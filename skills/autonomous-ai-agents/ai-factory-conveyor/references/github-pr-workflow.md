# GitHub PR-ворота и flow-контроль делегаций (J41–J46)

Питфоллы и правила, подтвержденные живыми прогонами в ai-factory и ekotov-wiki. Детали процесса — AGENTS.md репозиториев; здесь — то, что ломает ход работы.

## PR-ворота

- **Маркер в title обязателен** (`[BUG-NNN]`/`[change-id]`/`[chore]`/`[docs]`/`[ops]`) — без него pr_validate красит flow-чек. Правка title НЕ перезапускает required checks: после правки ЗАКРЫТЬ И ПЕРЕОТКРЫТЬ PR.
- `gh pr edit` при правке title может упасть с GraphQL-ошибкой Projects-classic — править через `gh api repos/<o>/<r>/pulls/<N> -X PATCH -f title=...`.
- **Прямой push в main отклонен ruleset'ом (GH013)** в обоих репо — даже однострочная ПМ-документация идет через PR. Мерж с красным required check без admin-прав токена невозможен (API возвращает 405 «Repository rule violations») — единственный легальный путь: сделать чек зеленым, не искать обходов.
- **«No commits between main and branch»** — ветка уже ancestor main (контент слился другим PR): проверять `git log main..branch` до `gh pr create`; пустую ветку удалить.
- Основная ветка контента может слиться не тем PR'ом, каким планировалось (промпт-PR подтягивает скриптовую ветку, если та уже запушена и влита в него) — перед созданием PR сверять `git log origin/main..branch`, не создавать дубликат.

## flow-enforcer (J43): заголовок делегации

Каждая конвейерная делегация несет первую строку goal:

```
flow: flow=<1-5> role=<роль> repo=<путь> scope=<идентификатор>
```

- scope по флоу: Ф1 change-id, Ф2 BUG-NNN, Ф3 incident-id, Ф4 chore-slug, Ф5 slug.
- Режимы `FLOW_ENFORCER_MODE=permissive|strict`; bypass — только дословно `flow: bypass --by customer` (пишется в incident-лог).
- Продуктовый dev_task без approve-архитектурного ревью → блок ARCH_REVIEW_MISSING (J46); порядок этапов — sequence-gate (FLOW_ENFORCER_SEQUENCE=1).
- Плагин — source of truth `plugins/flow-enforcer/` в фабрике; установка factory_init / `hermes plugins install realax07/ai-factory --ref <pin>`; переживает обновления Hermes; при обновлении плагина — скопировать в `~/.hermes/plugins/flow-enforcer/` и перезапустить gateway (живой процесс подхватывает только на старте).

## План релиза (J41)

Релиз стартует с PLAN-<change>.md (или openspec/changes/<change>/PLAN.md), пишет ПМ до диспатча СА; обязательна строка `Флоу: N`. Ф1/Ф2/Ф4 — обязателен (Ф2: PLAN-BUG-NNN.md или общий test-model/bugs/PLAN.md), Ф3 — incident_ref, Ф5 — без плана. Без плана create_change/dev_task → DENY PLAN_RELEASE_MISSING / PLAN_FLOW_UNDECLARED.

## Архитектор (J46)

- `architecture_review` актор — **architect** (легаси pm устранен); продуктовый dev_task без approve-ревью `test-model/reviews/<change>/review-NNN-architecture.md` → DENY ARCH_REVIEW_MISSING.
- В arch-ревью обязательна строка `Карта: обновлена` или `Карта: без изменений` — иначе архивация пакета = FLOW-ERROR.
- `architecture/map.md` обязателен в проекте с backend/services; устаревание карты ловить ревью архитектора, не отдельным скриптом.
- Модель архитектору — общая (flash); пиннинг большей модели — только по данным живых прогонов.

## QA (J23) и скилл/промпт

- Чеклист CHK упразднен: qa_case_author читает спеку напрямую, трассировка TC → Requirement/Scenario; негатив/границыы — оси qa_case_reviewer.
- Формула Заказчика: **скилл = инструкции КАК для конкретной задачи; системный промпт = мир роли** (as-is, контракты, скиллы). Best practice для всех ролей — в системные промпты (verification-блок «Факты до заявления готовности» — во всех agents/*.md).
- Сквозные (межсервисные) процессы тестируются на QA-этапе: СА специфицирует процесс/деградацию в design и включает сквозной набор в план прогонов, не создавая dev-задачу смоука (скилл service-decomposition).
