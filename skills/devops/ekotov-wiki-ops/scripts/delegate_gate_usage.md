# delegate_gate / delegate_watchdog — делегации через машину (P11+)

Продолжение правил делегаций ekotov-wiki после инцидента SELF_REVIEW
(add-containerization, 2026-10-03). Канон в скилле ekotov-factory-pipeline
(разделы «Делегации через машину» и «Три слоя гарантии»); здесь — рабочие
команды и ловушки первого прогона.

## Команды

```bash
# start: DENY/MISSING_INPUT/ZONE_CONFLICT → делегация не создается
python3 scripts/delegate_gate.py start --repo . --project wiki \
  --flow 1 --change <change-id> --task <N> --action dev_task --role dev \
  --path "<зона>/**" --approval-ref <decision_id> --owner-pm pm-main
# → печатает GATE: ALLOW — correlation_id=<id>; id в ТЗ сабагента

# finish: без него сессия висит running в flowctl status (видимый долг)
python3 scripts/delegate_gate.py finish --correlation-id <id> \
  --report /tmp/report.md --flow <N>

# status: открытые running-сессии = видимый долг
python3 scripts/delegate_gate.py status
```

## Ловушки первого прогона (все воспроизведены на wiki)

- **exit code 0 при DENY**: flowctl пишет `prepared: False` YAML-строкой при
  rc=0 — решение читать из машиночитаемого факта, не из exit code.
- **prepared: True** в YAML — заглавная; парсить `^prepared:\s*true` (re.M|re.I).
- **ZONE_CONFLICT на stale-резерве**: завершенная сессия держит зону — сначала
  `flowctl.py reconcile --delegation-id <id>` (помечает stale), потом повтор.
- **reconcile требует decision ПМ** — сам не решает, только помечает stale.
- Гейт-скрипт, отсутствующий в проекте (pm_bounds_check не ставился) →
  gate_runner честно ERROR/blocked — это НЕ обход, чинить установкой (E15).

## Связка платформенный id ↔ flowctl id

`~/.hermes/state/delegate_gate_gated_map.json` маппит платформенный
`deleg_…` (async_delegations) на flowctl `deleg-…`. После ЛЮБОГО delegate_task,
исполненного под prepare/run-циклом, добавь запись — unmapped gated-делегация
выглядит для вотчдога как BYPASS-инцидент. Полная процедура пере-диспатча после
падения делегации — в скилле ai-factory-flow-control (раздел Re-dispatch).

## Детектор обхода (delegate_watchdog)

- Сверяет async_delegations (state.db — платформенный факт, пишется при
  каждом delegate_task) с prepare-записями flowctl.
- Делегация мимо машины → BYPASS-инцидент в
  `~/.hermes/state/delegate_bypass_incidents.json` + exit 1; забытый finish →
  STALE.
- Baseline `delegate_gate_baseline.json` хранит installed_at — делегации до
  него история, не инцидент. Переходные легитимные случаи (ретро-ревью до
  внедрения) — фиксировать resolution-блоком в incidents-файле (см. пример
  deleg_31e8a5c7), вотчдог их не читает — это документ для Заказчика.
- Крон: hermes cron `*/5` с `--failure-deliver telegram` — BYPASS приходит
  Заказчику машинным сообщением с маркером `[FLOW-GATE BYPASS]`, отдельно от
  статусов ПМ. Крон-скрипты ищутся в `~/.hermes/scripts/` — копировать туда.

## SELF_REVIEW-мета (связка с flow_check)

review-файл обязан нести `Reviewer-Delegation: deleg_<id>`; approve без меты
не покрывает задачи. Ревьюер-сабагент не знает свой id — вписывает
оркестратор из async_delegations после завершения. Self-review файлы — в
`archive/` подкаталог пакета (не удалять), они не считаются.
