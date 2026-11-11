# -*- coding: utf-8 -*-
"""J65.9: дисциплина роста ворот — `flowctl gates-stats`.

Статистика срабатываний строится по уже существующим отчетам движка:
отчеты gate_runner, циклы flowctl_state.json, лог энфорсера.

Трассировка:
  TC-J65-GST-001  агрегация: гейты × статус, решения prepare, коды отказа
                  (всего и по этапам), итоги циклов, дефекты finish, события
                  энфорсера (WARNING отдельно)
  TC-J65-GST-002  «без срабатываний»: гейты без FAIL/ERROR и коды
                  REASON_CODES без отказов за период
  TC-J65-GST-003  окно --since/--until по времени записи (включительно);
                  кривая дата — exit 2; пустой state — пустой отчет, exit 0
  TC-J65-GST-004  битый отчет / строка лога — WARN, остальное считается;
                  `flowctl gates-stats` = `gates_stats.py` (одна реализация)
  TC-J65-GST-005  на настоящих отчетах: prepare с DENY и finish с FAIL гейта,
                  записанные flowctl/gate_runner, видны в статистике
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import gates_stats as gs  # noqa: E402


def _report(d: Path, name: str, started: str, gates: list[tuple[str, str]]):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"gate-report-{name}.json").write_text(json.dumps({
        "schema_version": "gate-report/1", "started_at": started,
        "gates": [{"gate_id": g, "status": s} for g, s in gates]}), encoding="utf-8")


def _run(action, created, status, verdict="ALLOW", reasons=(), defects=()):
    return {"action": action, "created_at": created, "status": status,
            "decision": {"status": verdict, "blocking_reasons": list(reasons)},
            "defects": [{"code": c, "source": s} for c, s in defects]}


def make_state(tmp_path: Path) -> Path:
    st = tmp_path / "state"
    rd = st / "gate-reports"
    _report(rd, "a", "2026-10-01T10:00:00+00:00", [("flow_check", "PASS"),
                                                   ("openspec_validate", "PASS")])
    _report(rd, "b", "2026-11-02T10:00:00+00:00", [("flow_check", "FAIL"),
                                                   ("pm_bounds_check", "ERROR")])
    _report(rd, "c", "2026-11-03T10:00:00+00:00", [("flow_check", "PASS")])
    (rd / "latest.json").write_text("{}", encoding="utf-8")   # не отчет
    runs = {
        "1": _run("dev_task", "2026-10-01T09:00:00+00:00", "prepared", "DENY",
                  ["PLAN_RELEASE_MISSING", "ARCH_REVIEW_MISSING"]),
        "2": _run("dev_task", "2026-11-02T09:00:00+00:00", "returned",
                  defects=[("FAIL", "gate")]),
        "3": _run("code_review", "2026-11-03T09:00:00+00:00", "prepared",
                  "UNKNOWN", ["MISSING_INPUT"]),
        "4": _run("create_change", "2026-11-03T09:30:00+00:00", "accepted"),
    }
    (st / "flowctl_state.json").write_text(json.dumps({"runs": runs}),
                                           encoding="utf-8")
    (st / "flow-enforcer.log").write_text("\n".join(json.dumps(e) for e in [
        {"ts": "2026-10-01T08:00:00+00:00", "event": "sequence_violation"},
        {"ts": "2026-11-02T08:00:00+00:00", "event": "push_denied", "level": "WARNING"},
        {"ts": "2026-11-02T08:01:00+00:00", "event": "push_allowed"},
    ]) + "\n", encoding="utf-8")
    return st / "flowctl_state.json"


def test_aggregates_all_sources(tmp_path):
    """TC-J65-GST-001."""
    s = gs.collect(make_state(tmp_path))
    assert s["gate_reports"] == 3
    assert s["gates"] == {"flow_check": {"FAIL": 1, "PASS": 2},
                          "openspec_validate": {"PASS": 1},
                          "pm_bounds_check": {"ERROR": 1}}
    assert s["flowctl_runs"] == 4
    assert s["decisions"] == {"ALLOW": 2, "DENY": 1, "UNKNOWN": 1}
    assert s["reason_codes"] == {"PLAN_RELEASE_MISSING": 1, "ARCH_REVIEW_MISSING": 1,
                                 "MISSING_INPUT": 1}
    assert s["reason_codes_by_action"]["dev_task"] == {"PLAN_RELEASE_MISSING": 1,
                                                       "ARCH_REVIEW_MISSING": 1}
    assert s["run_outcomes"] == {"accepted": 1, "prepared": 2, "returned": 1}
    assert s["finish_defects"] == {"FAIL (gate)": 1}
    assert s["enforcer_events"] == {"sequence_violation": 1, "push_denied": 1,
                                    "push_allowed": 1}
    assert s["enforcer_warnings"] == {"push_denied": 1}


def test_never_fired(tmp_path):
    """TC-J65-GST-002."""
    s = gs.collect(make_state(tmp_path))
    assert s["gates_never_failed"] == ["openspec_validate", "pr_validate"]
    assert "ZONE_CONFLICT" in s["reason_codes_never_fired"]
    assert "MISSING_INPUT" not in s["reason_codes_never_fired"]


def test_window_and_usage(tmp_path, capsys):
    """TC-J65-GST-003."""
    state = make_state(tmp_path)
    s = gs.collect(state, since="2026-11-01", until="2026-11-02")
    assert s["gate_reports"] == 1 and s["flowctl_runs"] == 1
    assert s["reason_codes"] == {} and s["enforcer_events"] == {
        "push_denied": 1, "push_allowed": 1}
    assert gs.main(["--state", str(state), "--since", "2026-11"]) == 2
    empty = tmp_path / "empty" / "flowctl_state.json"
    assert gs.main(["--state", str(empty), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["gate_reports"] == 0 and out["flowctl_runs"] == 0


def test_broken_inputs_and_flowctl_entry(tmp_path):
    """TC-J65-GST-004."""
    state = make_state(tmp_path)
    (state.parent / "gate-reports" / "gate-report-bad.json").write_text("{", encoding="utf-8")
    with (state.parent / "flow-enforcer.log").open("a", encoding="utf-8") as f:
        f.write("не json\n")
    s = gs.collect(state)
    assert s["gate_reports"] == 3 and len(s["unreadable"]) == 2
    r = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flowctl.py"),
                        "gates-stats", "--state", str(state), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["reason_codes"] == s["reason_codes"]
    text = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flowctl.py"),
                           "gates-stats", "--state", str(state)],
                          capture_output=True, text=True).stdout
    assert "flow_check: FAIL 1, PASS 2" in text and "WARN:" in text


def test_real_engine_records(tmp_path, monkeypatch):
    """TC-J65-GST-005: prepare dev_task без плана релиза и архитектурного
    ревью — DENY, записанный настоящим flowctl; его коды видны в статистике."""
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    import os
    full = dict(os.environ, **env)
    for f in list(repo.iterdir()):
        if f.name.startswith("PLAN-"):
            f.unlink()        # J41-фикстура conftest: здесь план нужен отсутствующим
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=full)
    (repo / "requirements.md").write_text("# ТЗ\n\n> Статус: УТВЕРЖДЕН\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=full)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True, env=full)
    st = tmp_path / "engine"
    st.mkdir()
    state = st / "flowctl_state.json"
    r = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flowctl.py"), "prepare",
                        "--repo", str(repo), "--project", "proj", "--flow", "1",
                        "--change", "add-x", "--task", "1.1", "--role", "dev",
                        "--action", "dev_task", "--owner-pm", "pm",
                        "--registry", str(st / "reg.json"), "--state", str(state),
                        "--json"],
                       capture_output=True, text=True,
                       env=dict(full, FLOW_MODE_FILE=str(st / "mode.json")))
    assert state.is_file(), r.stdout + r.stderr
    s = gs.collect(state)
    assert s["flowctl_runs"] == 1 and s["decisions"] == {"DENY": 1}
    assert "PLAN_RELEASE_MISSING" in s["reason_codes"], s   # J41: плана нет
    assert set(s["reason_codes"]) <= set(gs.ft.REASON_CODES)
