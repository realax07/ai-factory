#!/usr/bin/env python3
"""gates_stats.py — сколько раз срабатывал каждый гейт и код отказа (J65.9).

Дисциплина роста ворот: новый гейт — при повторе класса инцидента или
высокой цене одиночного промаха; гейт без срабатываний за период —
кандидат на удаление или перевод в предупреждение (квартальный пересмотр,
резолюция — в бэклоге). Эта команда дает фактуру для пересмотра; решение —
за Заказчиком.

Источники — уже существующие файлы памяти движка (новых журналов нет):
  1. отчеты gate_runner      <state>/gate-reports/gate-report-*.json
                             (gate_id × статус PASS/FAIL/ERROR/SKIPPED);
  2. циклы flowctl           <state>/flowctl_state.json, runs:
                             решение prepare (статус, blocking_reasons —
                             коды flow_transition.REASON_CODES), итог цикла,
                             дефекты finish (код × источник);
  3. энфорсер                <state>/flow-enforcer.log (JSONL, события).
<state> — каталог flowctl_state.json (по умолчанию factory_paths.state_dir(),
env AF_STATE_DIR). Окно — по полю времени записи (started_at / created_at /
ts), даты включительно.

Не видит (честно): отказы prepare ДО записи цикла — запрос зоны вне
политики роли (ZONE_OUTSIDE_POLICY) и защищенные пути без [pipeline]
(J3): flowctl их только печатает; STOP раннера — в его state рядом с
планом проекта.

Usage:
  python3 scripts/gates_stats.py [--state PATH] [--since YYYY-MM-DD]
                                 [--until YYYY-MM-DD] [--json]
  python3 scripts/flowctl.py gates-stats ...   (то же)

Exit: 0 — отчет построен (в т.ч. пустой); 2 — ошибка использования/чтения.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory_paths as fp  # noqa: E402
import flow_transition as ft  # noqa: E402
import gate_runner as gr  # noqa: E402

SCHEMA = "gates-stats/1"


class StatsError(Exception):
    pass


def _day(ts: object) -> str | None:
    """'2026-11-11T14:12:20+00:00' → '2026-11-11'; иначе None."""
    s = str(ts or "")
    try:
        date.fromisoformat(s[:10])
    except ValueError:
        return None
    return s[:10]


def _in_window(ts: object, since: str | None, until: str | None) -> bool:
    day = _day(ts)
    if day is None:
        return since is None and until is None  # без времени — только без окна
    return (since is None or day >= since) and (until is None or day <= until)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatsError(f"{path}: не читается ({exc})") from exc


def collect(state_path: Path, since: str | None = None,
            until: str | None = None) -> dict:
    state_dir = state_path.parent
    gates: dict[str, Counter] = {}
    reports = 0
    broken: list[str] = []
    rdir = state_dir / "gate-reports"
    for rp in sorted(rdir.glob("gate-report-*.json")) if rdir.is_dir() else []:
        try:
            rep = _read_json(rp)
        except StatsError as exc:
            broken.append(str(exc))
            continue
        if not _in_window(rep.get("started_at"), since, until):
            continue
        reports += 1
        for g in rep.get("gates") or []:
            gates.setdefault(str(g.get("gate_id", "?")), Counter())[
                str(g.get("status", "?"))] += 1

    decisions: Counter = Counter()          # статус решения prepare
    reasons: Counter = Counter()            # коды blocking_reasons
    reasons_by_action: dict[str, Counter] = {}
    outcomes: Counter = Counter()           # итог цикла (accepted/returned/…)
    defects: Counter = Counter()            # дефекты finish: "код (источник)"
    runs = 0
    if state_path.is_file():
        st = _read_json(state_path)
        for rec in (st.get("runs") or {}).values():
            if not _in_window(rec.get("created_at") or rec.get("started_at"),
                              since, until):
                continue
            runs += 1
            dec = rec.get("decision") or {}
            decisions[str(dec.get("status", "?"))] += 1
            for code in dec.get("blocking_reasons") or []:
                reasons[str(code)] += 1
                reasons_by_action.setdefault(str(rec.get("action", "?")),
                                             Counter())[str(code)] += 1
            outcomes[str(rec.get("status", "?"))] += 1
            for d in rec.get("defects") or []:
                defects[f"{d.get('code', '?')} ({d.get('source', '?')})"] += 1

    events: Counter = Counter()
    warnings: Counter = Counter()
    elog = state_dir / "flow-enforcer.log"
    if elog.is_file():
        for line in elog.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                broken.append(f"{elog}: строка не JSON")
                continue
            if not isinstance(ev, dict) or not _in_window(ev.get("ts"), since, until):
                continue
            name = str(ev.get("event", "?"))
            events[name] += 1
            if ev.get("level") == "WARNING":
                warnings[name] += 1

    fired = {g for g, c in gates.items()
             if c.get(gr.STATUS_FAIL) or c.get(gr.STATUS_ERROR)}
    return {
        "schema_version": SCHEMA,
        "state": str(state_path),
        "window": {"since": since, "until": until},
        "gate_reports": reports,
        "gates": {g: dict(sorted(c.items())) for g, c in sorted(gates.items())},
        "gates_never_failed": sorted(set(gr.KNOWN_GATES) - fired),
        "flowctl_runs": runs,
        "decisions": dict(sorted(decisions.items())),
        "reason_codes": dict(reasons.most_common()),
        "reason_codes_by_action": {a: dict(c.most_common())
                                   for a, c in sorted(reasons_by_action.items())},
        "reason_codes_never_fired": [c for c in ft.REASON_CODES if not reasons[c]],
        "run_outcomes": dict(sorted(outcomes.items())),
        "finish_defects": dict(defects.most_common()),
        "enforcer_events": dict(events.most_common()),
        "enforcer_warnings": dict(warnings.most_common()),
        "unreadable": broken,
    }


def render(s: dict) -> str:
    w = s["window"]
    out = [f"gates-stats: {s['state']} "
           f"(окно {w['since'] or '…'} — {w['until'] or '…'})", ""]
    out.append(f"Гейты gate_runner — отчетов: {s['gate_reports']}")
    for g, c in s["gates"].items():
        out.append(f"  {g}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    out.append("  без FAIL/ERROR за период: "
               + (", ".join(s["gates_never_failed"]) or "—"))
    out += ["", f"Решения flowctl prepare — циклов: {s['flowctl_runs']}"]
    out.append("  статусы: " + (", ".join(f"{k} {v}" for k, v in
                                           s["decisions"].items()) or "—"))
    out.append("  коды отказа: " + (", ".join(f"{k} {v}" for k, v in
                                              s["reason_codes"].items()) or "—"))
    for a, c in s["reason_codes_by_action"].items():
        out.append(f"    {a}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    out.append("  коды без срабатываний: "
               + (", ".join(s["reason_codes_never_fired"]) or "—"))
    out.append("  итог циклов: " + (", ".join(f"{k} {v}" for k, v in
                                              s["run_outcomes"].items()) or "—"))
    out.append("  дефекты finish: " + (", ".join(f"{k} {v}" for k, v in
                                                 s["finish_defects"].items()) or "—"))
    out += ["", "Энфорсер — события: " + (", ".join(
        f"{k} {v}" for k, v in s["enforcer_events"].items()) or "—")]
    if s["enforcer_warnings"]:
        out.append("  из них WARNING: " + ", ".join(
            f"{k} {v}" for k, v in s["enforcer_warnings"].items()))
    for b in s["unreadable"]:
        out.append(f"WARN: {b}")
    out += ["", "Не видно: отказы prepare до записи цикла (ZONE_OUTSIDE_POLICY, "
                "защищенные пути J3), STOP раннера (state рядом с планом)."]
    return "\n".join(out)


def add_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--state", default=None,
                    help="flowctl_state.json (по умолчанию — state движка)")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD включительно")
    ap.add_argument("--until", default=None, help="YYYY-MM-DD включительно")
    ap.add_argument("--json", action="store_true", dest="as_json")


def run(args: argparse.Namespace) -> int:
    for name in ("since", "until"):
        val = getattr(args, name)
        if val is not None and _day(val) != val:
            print(f"gates-stats: --{name} — дата YYYY-MM-DD, есть {val!r}",
                  file=sys.stderr)
            return 2
    state = Path(args.state) if args.state else fp.flowctl_state_path()
    try:
        stats = collect(state, args.since, args.until)
    except StatsError as exc:
        print(f"gates-stats: ОШИБКА — {exc}", file=sys.stderr)
        return 2
    print(json.dumps(stats, ensure_ascii=False, indent=2) if args.as_json
          else render(stats))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_arguments(ap)
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
