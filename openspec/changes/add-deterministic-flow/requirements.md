# Requirements: Детерминированный Flow Control (change add-deterministic-flow)

> Статус: УТВЕРЖДЕН r1 | Автор: pm_agent | История: r1 (2026-10-02, решение Заказчика «Погнали» на срез 1, ветка deterministic-flow)

## Описание

Детерминированный Flow Control для AI Factory: исполняемая модель состояния и переходов конвейера, которая по репозиторию, Git и реестру сессий объясняет, что уже доказано, какие действия разрешены, какой агент может их выполнить и почему действие заблокировано. ПМ перестает быть единственным носителем правил переходов: правила кодируются, решения ПМ проходят shadow-сверку с машиной.

Срез 1 (этот change): поставки 01 (контракт), 02 (flow_state.py — снимок), 03 (flow_transition.py — проверка действий). Режим shadow, без enforcement.

## Аудитория

- ПМ-агент: получает допустимые следующие действия (next_candidates) и причины запретов.
- Заказчик: получает доказуемую картину «гарантировано / на честном слове» (закрывает часть J14).
- Dev/QA-сабагенты: опосредованно — через проверки перед запуском (следующие срезы).

## Функциональные требования

- **FR-1.** Снимок состояния: `inspect(repo, scope) -> FlowSnapshot` — чистая, read-only, детерминированная; scope = repo + project + flow(1–5) + change/BUG/chore + task.
- **FR-2.** Каждый факт: key, value, source, observed_at, fingerprint, confidence ∈ {verified, unknown}; раздельно наличие и пригодность артефакта; статусы missing/invalid/unknown/ready.
- **FR-3.** Разрешение действия: `check_action(snapshot, action) -> Decision` — чистая; Decision содержит allowed, status ALLOW|DENY|UNKNOWN, blocking_reasons (стабильные коды), required_gates, evidence_refs, next_candidates; UNKNOWN не разрешает исполнение.
- **FR-4.** Стабильные коды причин: MISSING_INPUT, INVALID_GATE, HUMAN_APPROVAL_REQUIRED, WRONG_ROLE, ZONE_CONFLICT, STALE_EVIDENCE, AMBIGUOUS_STATE, STALE_SNAPSHOT, EXTERNAL_ENFORCEMENT_UNKNOWN; каждая причина с человекочитаемой деталью и путем к evidence.
- **FR-5.** Правила Флоу 1–5: полный цикл, багфикс с эскалацией при изменении поведения, хотфикс с обязательным последующим PR-циклом, обслуживание без обхода review, экспресс с ретроспективными артефактами; параллельные задачи только при [P] + выполненных зависимостях + непересекающихся зонах.
- **FR-6.** Этапные ворота Заказчика: старт change, релиз/фаза, работы вне плана → DENY/HUMAN_APPROVAL_REQUIRED без зафиксированного решения, привязанного к scope/фазе.
- **FR-7.** Честная граница: локальные PASS не доказывают branch protection → EXTERNAL_ENFORCEMENT_UNKNOWN.
- **FR-8.** CLI: `flow_state.py inspect` и `flow_transition.py check|next` c --json; exit 0 ALLOW / 1 DENY / 2 UNKNOWN или ошибка входа.

## Нефункциональные требования

- **NFR-1.** Только Python stdlib + pytest; никаких LangGraph/CrewAI/Temporal/БД событий.
- **NFR-2.** Детерминизм: двукратный вызов inspect на неизменном вводе — эквивалентный JSON.
- **NFR-3.** Read-only: inspect/check/next не пишут в репозиторий и реестр, не запускают агентов.
- **NFR-4.** Существующие ворота (flow_check.py, pm_bounds_check.py, pr_validate.py) не изменяются; их exit codes и режимы сохраняются.
- **NFR-5.** Ошибки чтения источников дают структурированную проблему и ненулевой exit, не пустые результаты.

## Приоритеты

- Must: FR-1…FR-6, FR-8, NFR-1…NFR-5.
- Should: FR-7 (пометка EXTERNAL_ENFORCEMENT_UNKNOWN в decision на merge).
- Won't (этот change): enforcement-блокировки, запуск агентов, HTTP/WebUI, автоматический Hermes-adapter, provenance-инфраструктура (поставка 05).

## Ограничения

- Режим shadow: решения машины не блокируют ПМ, расхождения фиксируются как данные.
- Правила флоу берутся из актуальных AGENTS.md/контрактов; при текстовых правилах без исполняемого критерия — UNKNOWN, не выдумывание правила.
- Реестр сессий — оперативный источник вне Git; отсутствие/битость ≠ «сессий нет».
- Изменения только в ветке deterministic-flow; в main не вливать до явного решения Заказчика.

## Открытые вопросы

- ОВ-1 (закрыт решением Заказчика 2026-10-02): скоуп = срез 1, поставки 01–03, ветка deterministic-flow.
- ОВ-2 (к поставке 03): формат маркера Флоу 4 — принимать ли `[chore]` в сообщении коммита плана или в файле плана задачи; дефолт: файл плана (docs/plan-*.md) с явным «Флоу: N».
