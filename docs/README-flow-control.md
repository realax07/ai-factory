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
| Этапные ворота | approval_ref = decision_id записи `decisions/<YYYY-MM-DD>-<slug>.md` (action/scope/SHA/expiration сверяются) | flow_transition check + gate_runner record-decision | HUMAN_APPROVAL_REQUIRED, STALE_EVIDENCE |

## Флоу 1 — полный (фича)

```
Заказчик: «погнали» → requirements.md (БА, ревью, УТВЕРЖДЕН)
  → create_change (sa) → sdd.md → architecture_review
  → цикл задач: dev_task → code_review → merge_task   ← [P]-задачи параллельно (зоны из reservation)
  → qa_impact_analysis → qa_cases → qa_review
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
incident_ref=S<1|2|3>-<id> (severity-классификация J48 — в маркере делегации;
  без префикса enforcer → FLOW_MARKER_INVALID)
  → emergency_stabilize (dev/devops; неклассифицированный incident_ref — DENY)
  → ПОСЛЕ стабилизации ОБЯЗАТЕЛЬНЫЙ PR-цикл: dev_task → code_review → merge_task
  └─ пока PR-цикл не закрыт: все post-emergency действия несут STALE_EVIDENCE
     (долг хотфикса) — «завершить» merge без последующего PR нельзя
  → deploy/rollback: только при существующих полномочиях (approval_ref)
     + EXTERNAL_ENFORCEMENT_UNKNOWN (локальный PASS ≠ защита main)
  → post_mortem (dev/devops): test-model/incidents/<YYYY-MM-DD>-<incident_ref>.md,
     секции Таймлайн/Root cause/Action items; append-only (J48, обязателен S1/S2)
  → archive_change (sa/dev_lead/integrator): ворота post-mortem (D2) —
     S1/S2 без post-mortem = DENY; S3 — протокол не применяется
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

Контракт: `contracts/flow_control_contract.md`. Спека: `openspec/specs/deterministic-flow/` (после слияния). Прогон всего: `python3 -m pytest tests/` (446 green).

## Журнал решений Заказчика (P0.4)

Этапные ворота (`approve_requirements`, `create_change`, `release`, …) принимают `--approval-ref` только как **decision_id** записи журнала решений:

```
# запись (append-only, не перезаписывается):
python3 scripts/gate_runner.py record-decision --repo . \
    --decision-id 2026-10-02-start-add-widget \
    --project proj --change add-widget --phase 1 \
    --action create_change --commit auto \
    --source "чат-лог: «погнали»" --quote "погнали"

# проверка действия по записи:
python3 scripts/flow_transition.py check --repo . --project proj --flow 1 \
    --change add-widget --action create_change --role sa \
    --approval-ref 2026-10-02-start-add-widget
```

Запись `decisions/<YYYY-MM-DD>-<slug>.md` несет машиночитаемый блок
`decision-record/1`: decision_id, date, scope (project/change_id/phase),
action, commit (SHA на момент решения), source (канал/дословная цитата),
опционально expiration. Проверяется соответствие записи запросу: action,
scope, SHA записи — предок HEAD или равен ему («SHA в истории», не TTL),
expiration не истек. Непустая строка без записи журнала решением НЕ является.
Журнал — НЕ защищенная подпись: «решение зафиксировано», не «личность
подтверждена».

## Regress (J51.2/J51.3, 2026-10-17)

`flowctl regress --change <id> [--final] [--tier smoke]` — детерминированный
регресс затронутых доменов: дифф (main...HEAD) → маппинг доменов
(frontend → tests/web, backend → tests/api, иное → tests/; общий домен
сворачивает частичные — BUG-005). Артефакт
`test-model/regress/<change>/regress-<N>.md` (append-only): verdict,
commit, worktree, сьюты, хвост лога. `--final` пишет `regress-final.md`.
Проектная карта доменов (`test-model/regress-domains.json`, J52-w1.3)
делает домены кейс-каталогами и при активной карте НЕ сворачивает их:
multi-domain прогон — один pytest-вызов, тот же профиль, что до дедупа
BUG-005 — bare `from conftest import` в кейс-доменах роняет коллекцию
(pytest exit 2 → FAIL), правило — хелперы через фикстуры (шов J51 #8).
Домен, затронутый диффом без каталога тестов (в т.ч. частичный skip при
активной карте) — WARN-вердикт, не молчаливый PASS.

Ворота merge (pr_validate, change-PR): regress-final обязателен — PASS,
commit-предок HEAD (в CI: full-history checkout + GitHub API compare —
BUG-022), сам артефакт исключен из сверки свежести (BUG-023), worktree
машины прогона нечитаем в CI → WARNING (инвариант несет commit-сверка).
Исполнитель — роль regress_runner (узкий бриф: ветка/коммит/сьюты;
различение бага от флака изолированным перепрогоном; FAIL → возврат dev).

Планы: J54 — эшелоны (домен → cross-domain smoke → regress-final),
baseline известных фейлов, freeze tooling (контракт роли regress_runner,
J52-w2: после regress-final tooling-пути `scripts/**`, `.github/**` не
коммитятся до merge — мета-коммит после артефакта = перегон).

Обкатка ворот в CI (J52-w3): ворота проверяются harness-имитацией
CI-среды до merge — `tests/test_gate_harness.py` строит эталонное
tmp-репо с артефактами change-пакета (коммиты датированы:
GIT_AUTHOR/COMMITTER_DATE, NOW минус N минут, шаг ≥60с — без дат
секундная гранулярность схлопывает свежестную сверку `ts > art_ts`),
делает shallow-клон (как actions/checkout fetch-depth 1) и гоняет
`pr_validate`/`flow_check`/`factory_init` сабпроцессом в чистом env
(env -i: минимальный PATH, чистый HOME без `~/ai-factory`/`~/.hermes`,
без `GITHUB_*` и openspec). Эталонные кейсы: pass-репо (в т.ч.
верификация предка через unshallow — ветка BUG-022), stale-артефакт →
REGRESS_FINAL_STALE, missing-артефакт → REGRESS_FINAL_MISSING,
graceful-деградация без openspec CLI (класс инцидента J53); fresh-ось
(BUG-023/024): мета-коммит `code-reviews/**` после regress-final →
PASS, продуктовый `tests/**` после артефакта → STALE (на пре-фиксных
pr_validate 596d262~1/12496ec~1 мета-кейс дает ложный STALE — ось
покрыта). Harness входит в `pytest tests/` шага Run tests job
test-flow-control (`.github/workflows/flow.yml`) — конвейер сам
обкатывает свои ворота в CI-условиях; отдельный шаг не несет
отдельного env-контекста. Из класса BUG-022/023/024 («в комфортной
среде автора PASS, в CI ложняк») покрыты ancestry-ось (BUG-022) и
fresh-ось (BUG-023/024).

## Ревью-мета и маппинг (J10, контракты в промпт code_reviewer — J52-w2)

Review-файл `code-reviews/<change-id>/review-<задача>-<NNN>.md` —
машиночитаемый контракт: ворота (flow_check, pr_validate) парсят строки,
не прозу.

- Вердикт — заголовком: `## Вердикт: approve` или `## Вердикт: return`
  (форма `approve|return`; нумерованный `## 7. Вердикт` и слово в прозе не
  парсятся). Действует вердикт ПОСЛЕДНЕЙ итерации задачи (max rev), не
  старый approve (BUG-AF-RECHECK-003).
- Мета делегации — строка `Reviewer-Delegation: deleg_<id>`: платформенный
  id вплотную (`deleg_<id>`), первая мета файла; SELF_REVIEW-защита —
  сверка с async_delegations (не dev-делегация задачи, статус completed).
- Несколько задач на один файл (или историческое имя без числовых id) →
  `review-mapping.json` рядом: `{"review-002.md": ["2.1", "2.2"]}`;
  числовые id в имени файла тоже читаются.
- Нет вердикта/меты в этом формате → задача НЕ покрыта воротами (approve
  не засчитан); формат — стоячий контракт в `agents/code_reviewer_agent.md`,
  не знание ПМ.
