# design.md — add-incident-protocol

Техрешения реализации. Требования — см. requirements.md (утверждены Заказчиком
2026-10-14). Capability пакета — `incident-protocol` (в openspec/specs/capability
у Флоу 3 нет; заводится дельтой пакета, ADDED Requirements — зон нет, пакет
однокомпонентный).

## D1: severity-префикс внутри incident_ref

**Решение:** формат `incident_ref=S1-<краткий-ид>` — severity как префикс внутри
существующего поля; отдельное поле `severity=` отклонено (обоснование в
requirements.md FR-4: рассинхронизация пары полей, ломка потребителей incident_ref).

**Реализация:** разбор префикса регулярным выражением `^S[123]-` в
`scripts/flow_transition.py`. `check_emergency_stabilize` (~строка 1606) сейчас
требует только непустой incident_ref — дополняется проверкой префикса: нет
префикса → Finding MISSING_INPUT «инцидент неклассифицирован» (не UNKNOWN-факт,
а отсутствие входа классификации). Разобранный severity доступен последующим
check-функциям через ctx (контекст одного check_action-вызова).

**Статус: не проверено на проде** (этап 4 плана — dev; в этом change кода нет).

## D2: ворота архивации — flow_transition, НЕ flow_check

**Решение: одно место — `scripts/flow_transition.py`, check архивации Флоу 3**
(новая check-функция archive-этапа, по образцу `_hotfix_debt_findings`,
строки 1217–1240: тот же паттерн — flow==3-специфичная Finding-ветка).
flow_check не трогается.

**Обоснование (почему не flow_check):**

1. **incident_ref доступен только на уровне действия.** incident_ref приходит
   из маркера делегации (enforcer передает `--incident-ref` scope Флоу 3,
   enforcer.py ~552) и живет в Action (flow_transition.py:153), а не в
   состоянии репозитория. `flow_check.check(repo)` — глобальный статический
   обход репо; реестр сессий и Action он не читает (grep по flow_check.py:
   registry/incident — 0 вхождений). Корреляцию «инцидент → post-mortem»
   flow_check строить не из чего.
2. **Нет контекста флоу на действие.** flow_check не знает, какой change
   исполняется по Флоу 3 (у хотфикса нет change-пакета — scope = incident-id);
   правило «архивация Флоу 3» в flow_check потребует эвристики, а это отход
   от NFR-1 (детерминизм, без LLM).
3. **Семантика ворот.** Ворота — условие перехода (DENY с blocking_reason и
   MISSING_INPUT-кодом), а не постфактум-аудит артефактов; это нативная
   семантика flow_transition (Decision/Findings), и она же дает ненулевой
   exit CLI (сценарий FR-3).
4. **NFR-3.** flow_check общий для всех флоу; правило, живущее в check-функции
   STAGE_TABLE[3], физически не может изменить поведение Флоу 1/2/4/5.
   Дублирование правила в flow_check вдобавок к flow_transition — два места
   одной логики (риск расхождения) — противоречит постановке «одно место».

**Проверяемость:** архивация Флоу 3-задачи с incident_ref S1/S2 при отсутствии
`test-model/incidents/`-файла с этим incident_ref → DENY (ненулевой exit CLI);
с post-mortem → ALLOW по воротам; неклассифицированный incident_ref → DENY
(MISSING_INPUT), архивацию не разрешает.

**Статус механизма (flow_transition Decision/Findings, коды причин): проверено**
(работает в проде фабрики со срезов 01–03, поставка 03). **Статус новых ворот:
не проверено на проде** (этап 4 плана — dev).

## D3: STAGE_TABLE Флоу 3 — новые этапы

Сейчас (flow_transition.py:1774–1784): emergency_stabilize → accept_review →
merge_task → deploy_rollback. Новая конфигурация:

```
3: (
    Stage("emergency_stabilize", ...)   # + severity-классификация (D1) в check
    Stage("accept_review", ...)
    Stage("merge_task", ...)
    Stage("deploy_rollback", ...)
    Stage("post_mortem", ("dev", "devops"), False,
          ("post-mortem в test-model/incidents/ (секции: таймлайн, root cause, action items)",),
          check_post_mortem),
    Stage("archive_change", ("sa", "dev_lead", "integrator"), False,
          ("flow_transition ворота post-mortem (D2)",),
          check_archive_flow3),
)
```

- **severity-классификация** — не отдельный этап, а check на emergency_stabilize:
  реакция обязана начинаться с классифицированного маркера (порядок FR-2 шаг 3
  «фиксация incident_ref» внутри initial response); отдельный этап разорвал бы
  окно 0–15 минут процессной процедурой.
- **post_mortem** — этап производства артефакта (после стабилизации и закрытия
  PR-цикла, до архивации); роли dev/devops — участники реакции.
- **archive_change** — этап ворот (D2): роли sa/dev_lead/integrator — те же, что
  для архивации Флоу 1 (решение Заказчика 3.3 S7), конфигурация не плодит
  новых ролей. Порядок гарантирует: архивация без пройденного post_mortem
  недостижима, а check_archive_flow3 независимо перепроверяет файл (зеркалит
  контракт 7: наличие артефакта проверяется в момент ворот).

**Статус: не проверено на проде.**

## D4: хранение post-mortem — test-model/incidents/, append-only

- **Путь:** `test-model/incidents/` (не docs/incidents/ — решение из ограничений
  requirements.md: смежность с QA-контуром test-model).
- **Именование:** `<YYYY-MM-DD>-<incident_ref>.md`, напр.
  `2026-10-15-S1-prod-down.md` — correlation с воротами D2/D3 по подстроке
  incident_ref в имени файла (детерминированный файловый матч, NFR-1).
- **Обязательные секции** (проверка check_post_mortem по заголовкам):
  `## Таймлайн` (с timestamps initial response — проверяемость порога FR-2),
  `## Root cause`, `## Action items`.
- **Append-only (NFR-2):** существующие файлы не удаляются и не переписываются,
  только новые записи. Enforcement — конвенция для агентов (запись в контракте
  каталога) + ревью; машинный контроль неизменяемости (git-history сторож) в
  этот change не входит (Won't-граница: минимальный срез J48). Историческая
  запись J25 (ad hoc-разбор 2026-10-05) переносится дословно без severity —
  решение ОВ-1, в спеку не включается.

**Статус: не проверено на проде.**

## Допущения

| Допущение | Статус |
|---|---|
| Паттерн flow==3 Finding-ветки в flow_transition (D2, образец 1217–1240) | проверено (код существует, поставка 03 в проде) |
| incident_ref в Action и enforcer-маркере (D1) | проверено (flow_transition.py:153, enforcer.py:552) |
| flow_check не читает реестр/Action (аргумент D2.1) | проверено (grep, чтение flow_check.py) |
| Новые ворота/этапы/хранилище в работе | не проверено на проде (этапы 4–7 плана) |
| Файлы test-model/incidents/ не удаляются агентами | не проверено на проде (конвенция, контроль ревью) |
