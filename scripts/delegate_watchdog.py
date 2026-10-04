#!/usr/bin/env python3
"""delegate_watchdog.py — детектор обхода flowctl (слой 2 гарантии, J35).

Проблема (инцидент add-containerization 2026-10-03): 6 делегаций диспатчились
напрямую через delegate_task, минуя flowctl prepare/run/finish — state machine
стояла в стороне. Контрактный запрет «на бумаге» не остановил. Гарантия должна
быть технической: обход НЕВОЗМОЖНО не заметить.

Механика: реестр делегаций Hermes (~/.hermes/state/active_sessions.json) пишется
платформой при КАЖДОМ delegate_task — независимо от воли агента. Вотчдог
сопоставляет делегации реестра с prepare-записями flowctl
(~/.hermes/state/flowctl_state.json):

  - делегация с scope проекта, где стоит машина, БЕЗ записи flowctl →
    BYPASS (обход): репорт + опционально файл-инцидент;
  - делегация, у которой flowctl-сессия осталась running после завершения
    делегации → STALE_FINISH (забыт finish): репорт.

Запуск: крон (`*/5 * * * * --no-agent`) или руками.
Exit 0 = чисто; 1 = найдены нарушения (детали в stdout).
"""
import json
import sys
import time
from pathlib import Path

REGISTRY_DB = Path.home() / ".hermes" / "state.db"   # async_delegations — платформенный факт
FLOWCTL_STATE = Path.home() / ".hermes" / "state" / "flowctl_state.json"
INCIDENTS = Path.home() / ".hermes" / "state" / "delegate_bypass_incidents.json"
PM_NUDGE_STATE = Path.home() / ".hermes" / "state" / "delegate_watchdog_pm_nudge.json"
GRACE_SECONDS = 120  # делегациям младше 2 минут даем время на prepare (гонка старт)
# Анти-рекурсия (требование Заказчика 2026-10-04): [PM-INSTRUCTION] доставляется
# ПМ как OUT-OF-BAND; ПМ в ответе может триггерить новые делегации → новый
# инцидент → новая инструкция → бесконечный цикл прерываний. Защита тройная:
# 1) дедуп по fingerprint (одинаковый состав инцидентов НЕ печатается повторно);
# 2) cooldown: после каждой доставки инструкция молчит PM_COOLDOWN_SECONDS даже
#    при изменении состава — у ПМ есть окно на реакцию без встречных пингов;
# 3) MAX_NUDGES_PER_HOUR: жесткий потолок доставок (сверх него канал ПМ молчит,
#    машинный отчет Заказчику и файл инцидентов продолжают писаться).
PM_COOLDOWN_SECONDS = 900        # 15 минут тишины между инструкциями ПМ
MAX_NUDGES_PER_HOUR = 3          # потолок инструкций ПМ в час


def load(path):
    """JSON-файл (flowctl_state)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"WARN: {path.name} поврежден ({e}) — пропуск прогона", file=sys.stderr)
        return None


def load_delegations() -> list[dict] | None:
    """Все делегации из async_delegations (пишется платформой при каждом
    delegate_task — независимо от воли агента)."""
    import sqlite3
    if not REGISTRY_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{REGISTRY_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT delegation_id, parent_session_id, state, delivery_state,"
            " dispatched_at, completed_at FROM async_delegations"
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"WARN: state.db недоступен ({e})", file=sys.stderr)
        return None
    out = []
    for r in rows:
        out.append({"delegation_id": r["delegation_id"], "state": r["state"],
                    "delivery_state": r["delivery_state"],
                    "dispatched_at": r["dispatched_at"],
                    "completed_at": r["completed_at"],
                    "parent_session_id": r["parent_session_id"]})
    return out


def main() -> int:
    delegations = load_delegations()
    flow = load(FLOWCTL_STATE)
    if delegations is None or flow is None:
        print("clean: реестры недоступны/пусты — сверка невозможна")
        return 0

    flow_runs = flow.get("runs", {})
    gated = {r.get("delegation_id") for r in flow_runs.values() if isinstance(r, dict)}

    now = time.time()
    bypasses, stale = [], []

    for d in delegations:
        if not isinstance(d, dict):
            continue
        did = d.get("delegation_id") or d.get("id")
        created = d.get("created_at") or d.get("dispatched_at") or d.get("started_at")
        status = (d.get("state") or "").lower()
        project = (d.get("scope") or {}).get("project") or d.get("project") or ""

        if not did or did in gated:
            continue
        # возраст: строки ISO или epoch — терпимо к обоим
        age = None
        try:
            if isinstance(created, (int, float)):
                age = now - float(created)
            elif created is None:
                age = None
            elif isinstance(created, str) and created:
                from datetime import datetime, timezone
                ts = created.replace("Z", "+00:00")
                age = now - datetime.fromisoformat(ts).timestamp()
        except Exception:
            age = None
        if age is not None and age < GRACE_SECONDS:
            continue  # стартовая гонка — prepare еще идет

        finished = status in ("completed", "error")
        if finished:
            bypasses.append({"delegation_id": did, "project": project,
                             "status": status, "created_at": created})
        elif status in ("running", "active", "prepared"):
            stale.append({"delegation_id": did, "project": project,
                          "status": status, "created_at": created})

    # STALE_FINISH: gated-делегации, чья flowctl-сессия застряла в running
    for r in flow_runs.values():
        if not isinstance(r, dict):
            continue
        if r.get("status") == "running" and r.get("finished_at"):
            stale.append({"delegation_id": r.get("delegation_id"),
                          "project": (r.get("scope") or {}).get("project"),
                          "status": "running-with-finished_at", "created_at": None})

    # Baseline: делегации до внедрения delegate-gate не инциденты (история).
    baseline_path = Path.home() / ".hermes" / "state" / "delegate_gate_baseline.json"
    baseline = load(baseline_path)
    if baseline is None:
        # Первый прогон: запоминаем "сейчас" как границу — все прошлые делегации
        # вне зоны ответственности вотчдога (внедрение = начало отсчета).
        baseline = {"installed_at": time.time(),
                    "note": "дата внедрения delegate-gate; делегации до неё — история"}
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline, indent=2))
    installed_at = baseline.get("installed_at", 0)
    bypasses = [b for b in bypasses
                if isinstance(b.get("_age_ok"), bool) or (b.get("created_at") or 0) > installed_at]
    bypasses = [b for b in bypasses if (b.get("created_at") or 0) > installed_at]

    report = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "bypass": bypasses, "stale_finish": stale}
    if bypasses or stale:
        INCIDENTS.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        # Решение Заказчика 2026-10-04, вторая редакция: два канала.
        #   Канал 1 — ПМ (main-сессия): инструкция [PM-INSTRUCTION], которую
        #     шлюз доставляет в main-чат как OUT-OF-BAND (как правка
        #     Заказчика посреди задачи). Анти-рекурсия — тройная (см.
        #     константы выше): fingerprint-дедуп + cooldown + часовой потолок.
        #   Канал 2 — Заказчику: сухой машинный отчет «как раньше»
        #     (без обращений к ПМ — ему не нужно читать нареканий в свой
        #     адрес, это между машиной и ПМ).
        now_ts = time.time()
        prev_nudge = load(PM_NUDGE_STATE) or {}
        fingerprint = json.dumps(
            sorted(b["delegation_id"] for b in bypasses)
            + sorted((s["delegation_id"] or "") for s in stale),
            sort_keys=True)
        changed = prev_nudge.get("fingerprint") != fingerprint
        in_cooldown = (now_ts - prev_nudge.get("last_sent", 0)) < PM_COOLDOWN_SECONDS
        history = [t for t in prev_nudge.get("sent_history", [])
                   if now_ts - t < 3600]
        over_budget = len(history) >= MAX_NUDGES_PER_HOUR
        if changed and not in_cooldown and not over_budget:
            history.append(now_ts)
            PM_NUDGE_STATE.parent.mkdir(parents=True, exist_ok=True)
            PM_NUDGE_STATE.write_text(json.dumps(
                {"fingerprint": fingerprint, "last_sent": now_ts,
                 "sent_history": history}, indent=2))
            ids = ", ".join(sorted(b["delegation_id"] for b in bypasses)) or "—"
            print("[PM-INSTRUCTION] (watchdog → ПМ, вне очереди) Обнаружены "
                  f"делегации мимо delegate_gate: {ids}. Действуй немедленно, "
                  "не дожидаясь текущего шага: (1) активные/будущие диспатчи — "
                  "только через scripts/delegate_gate.py prepare → run → finish "
                  "с валидным approval_ref; (2) по каждому bypass-id оформи "
                  "ворота задним числом (decision-record) или доложи "
                  "Заказчику, почему их нет; (3) подтверждение — ответ в "
                  "main-чат. Детали: " + str(INCIDENTS))
        elif over_budget:
            print(f"PM-INSTRUCTION suppressed: лимит {MAX_NUDGES_PER_HOUR}/ч "
                  "исчерпан — см. файл инцидентов (канал Заказчика работает)")
        print(f"BYPASS DETECTED: обходов={len(bypasses)}, забытых finish={len(stale)}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print("clean: все делегации покрыты flowctl, открытых финишей нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
