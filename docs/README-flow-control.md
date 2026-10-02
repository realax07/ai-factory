# README — Детерминированный Flow Control (add-deterministic-flow)

> Срезы 1–4 завершены 2026-10-02. Режим: **enforcing** (решение Заказчика;
> переключение — `python scripts/flow_mode.py set shadow|enforcing`).

## Производственный процесс: все флоу с развилками и валидациями

Общая рамка (для любого флоу):

```
Решение Заказчика (зафиксировано) → план с флоу → flowctl prepare
   → [ворота: ALLOW?] → reservation зоны → run (manual/delegate)
   → работа в worktree → finish → zone-check + gates (gate_runner)
   → provenance review → accepted / returned / blocked
```

Валидации на каждом шаге (режим enforcing — DENY/UNKNOWN блокируют):

| Шаг | Проверка | Скрипт | Коды отказа |
|---|---|---|---|
| Старт пакета | решение Заказчика привязано к scope/фазе | flow_transition | HUMAN_APPROVAL_REQUIRED |
| Снимок | факты по пакету (requirements/tasks/reviews/Git/реестр) | flow_state inspect | missing/invalid/unknown |
| Действие | порядок этапа, роль, зависимости, [P], QA-порядок | flow_transition check | INVALID_GATE, WRONG_ROLE, MISSING_INPUT, ZONE_CONFLICT, STALE_EVIDENCE |
| Запуск сессии | атомарная резервация зоны, идемпотентность | session_check reserve | ZONE_CONFLICT, DUPLICATE_PAYLOAD |
| Запуск делегации | переснимок перед стартом | flowctl run | STALE_SNAPSHOT |
| Приемка | diff ⊆ зона (renames/symlink), branch, worktree | session_check check | OUT_OF_ZONE |
| Ворота | openspec strict + flow_check + pm_bounds + pr_validate (digest, timeout) | gate_runner run | FAIL/ERROR/SKIPPED(≠PASS) |
| Ревью | sidecar: SHA/diff_digest/автор/ревьюер, независимость | gate_runner record-review + check | STALE_EVIDENCE, WRONG_ROLE |

## Флоу 1 — полный (фича)

```
Заказчик: «погнали» → requirements.md (БА, ревью, УТВЕРЖДЕН)
  → create_change (sa) → sdd.md → architecture_review
  → цикл задач: dev_task → code_review → merge_task   ← [P]-задачи параллельно (зоны из reservation)
  → qa_impact_analysis → qa_checklist → qa_cases → qa_review
  → approved кейсов СВОЕГО пакета → qa_automation
  → archive_change (sa, дельты слиты) → release (ТОЛЬКО после archive, 3.2-Б)
```
Валидации: требования УТВЕРЖДЕН до dev (R4); approve по SHA/диффу и независимой роли; QA-автоматизация только при approved_cases_of_change (3.1-А); release после archive.

## Флоу 2 — багфикс

```
BUG-NNN + существующая спека → dev_task (без БА/СА)
  └─ если меняет ожидаемое поведение/API/схему → ЭСКАЛАЦИЯ:
       next_candidates = [create_change (Флоу 1), escalate_to_customer]
```
Валидации: BUG-NNN обязателен; эскалация обязательна при spec_delta (иначе DENY).

## Флоу 3 — хотфикс (авария)

```
incident_ref → emergency_stabilize (dev/pm, минимальный цикл)
  → ПОСЛЕ стабилизации ОБЯЗАТЕЛЬНЫЙ PR-цикл: dev_task → code_review → merge_task
  └─ пока PR-цикл не закрыт: все post-emergency действия несут STALE_EVIDENCE
     (долг хотфикса) — «завершить» merge без последующего PR нельзя
  → deploy/rollback: только при существующих полномочиях (approval_ref)
     + EXTERNAL_ENFORCEMENT_UNKNOWN (локальный PASS ≠ защита main)
```

## Флоу 4 — обслуживание фабрики/проекта

```
[chore]-маркер → chore_task (dev) → code_review → merge_task
  └─ НЕ обходится PR/review; изменение ПРАВИЛ фабрики = отдельное решение
     Заказчика (rules_change) — без него DENY
```
Именно по этому флоу сделан сам change add-deterministic-flow.

## Флоу 5 — экспресс

```
условия экспресс-режима из BACKLOG/README → минимальный цикл
  └─ до ЗАКРЫТИЯ обязательны ретроспективные артефакты:
     requirements (ретроспектива) + spec delta + кейсы
  └─ без них закрытие → DENY (урок R1.3)
```

## Режимы

- **shadow** — решения вычисляются и логируются, не блокируют (для прогонов на истории).
- **enforcing** — DENY/UNKNOWN останавливают действие (текущий режим).
- Переключение: `python scripts/flow_mode.py set enforcing|shadow --by <кто>`; состояние: `~/.hermes/state/flow_mode.json`.

## Инциденты и recovery

- Падение процесса → `flowctl reconcile` (или `session_check reconcile`): PID/worktree/status → stale/needs_attention. Ничего не удаляется молча.
- Timeout/crash не продвигают шаг; worktree сохраняется; повторный run без нового решения отказывает.
- Дропнутые при rollover отчеты делегаций — `state.db → async_delegations.result_json`.

## Компоненты

| Скрипт | Назначение |
|---|---|
| `flow_state.py` | снимок фактов по scope (чистый, read-only) |
| `flow_transition.py` | ALLOW/DENY/UNKNOWN + коды причин, графы флоу |
| `session_check.py` | резервация зон, post-check, reconcile |
| `gate_runner.py` | ворота с digest/STALE, provenance, audit JSONL |
| `flowctl.py` | оркестратор: prepare/run/finish/status/reconcile |
| `flow_mode.py` | shadow/enforcing |

Контракт: `contracts/flow_control_contract.md`. Спека: `openspec/specs/deterministic-flow/` (после слияния). Прогон всего: `python3 -m pytest tests/` (348 green).
