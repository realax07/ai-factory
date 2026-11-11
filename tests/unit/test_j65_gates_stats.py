# -*- coding: utf-8 -*-
"""J65.9: дисциплина роста ворот — `flowctl gates-stats`.

Статистика срабатываний строится по уже существующим отчетам движка:
отчеты gate_runner, циклы flowctl_state.json, лог энфорсера.

Трассировка:
  TC-J65-GST-001  агрегация: гейты × статус, решения prepare, коды отказа
                  (всего и по этапам), итоги циклов, дефекты finish, события
                  энфорсера (WARNING отдельно)
  TC-J65-GST-002  «без срабатываний»: гейты, исполнявшиеся без FAIL/ERROR,
                  отдельно от не исполнявшихся (только SKIPPED); коды
                  REASON_CODES без отказов — без ненаблюдаемых этими
                  источниками (ZONE_CONFLICT, STALE_SNAPSHOT run)
  TC-J65-GST-003  окно --since/--until по UTC-дате (включительно); записи
                  без времени при окне — счетчик undated_skipped; кривая дата
                  и --since позже --until — exit 2; пустой state — exit 0
  TC-J65-GST-004  битый отчет / строка лога — WARN, остальное считается;
                  state не объект — exit 2; доп. каталоги --reports и лог
                  энфорсера по FLOW_ENFORCER_STATE_DIR; `flowctl gates-stats`
                  = `gates_stats.py`; без модуля отказывает только подкоманда
  TC-J65-GST-005  на записях настоящего flowctl: prepare с DENY виден в
                  статистике; отчеты finish — в каталоге, который читает
                  gates_stats (<state>/gate-reports)
  TC-J65-GST-006  каждый код REASON_CODES без Finding(...) в flow_transition
                  числится ненаблюдаемым (дрейф кодов — красный тест)
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
    assert s["gates_never_failed"] == ["openspec_validate"]
    assert s["gates_not_executed"] == ["pr_validate"]
    _report(tmp_path / "state" / "gate-reports", "d", "2026-11-04T10:00:00+00:00",
            [("pr_validate", "SKIPPED")])
    s = gs.collect(tmp_path / "state" / "flowctl_state.json")
    assert s["gates_not_executed"] == ["pr_validate"]           # только SKIPPED
    assert "STALE_EVIDENCE" in s["reason_codes_never_fired"]
    assert "MISSING_INPUT" not in s["reason_codes_never_fired"]
    for code in ("ZONE_CONFLICT", "STALE_SNAPSHOT"):
        assert code not in s["reason_codes_never_fired"]
        assert code in s["reason_codes_unobservable"]


def test_window_and_usage(tmp_path, capsys):
    """TC-J65-GST-003."""
    state = make_state(tmp_path)
    s = gs.collect(state, since="2026-11-01", until="2026-11-02")
    assert s["gate_reports"] == 1 and s["flowctl_runs"] == 1
    assert s["reason_codes"] == {} and s["enforcer_events"] == {
        "push_denied": 1, "push_allowed": 1}
    assert gs.main(["--state", str(state), "--since", "2026-11"]) == 2
    assert gs.main(["--state", str(state), "--since", "2026-11-05",
                    "--until", "2026-11-01"]) == 2
    data = json.loads(state.read_text(encoding="utf-8"))
    data["runs"]["5"] = _run("dev_task", None, "prepared")
    state.write_text(json.dumps(data), encoding="utf-8")
    assert gs.collect(state, since="2026-11-01")["undated_skipped"] == 1
    assert gs.collect(state)["flowctl_runs"] == 5               # без окна — считается
    empty = tmp_path / "empty" / "flowctl_state.json"
    assert gs.main(["--state", str(empty), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["gate_reports"] == 0 and out["flowctl_runs"] == 0


def test_broken_inputs_and_flowctl_entry(tmp_path, monkeypatch):
    """TC-J65-GST-004."""
    state = make_state(tmp_path)
    (state.parent / "gate-reports" / "gate-report-bad.json").write_text("{", encoding="utf-8")
    with (state.parent / "flow-enforcer.log").open("a", encoding="utf-8") as f:
        f.write("не json\n")
    s = gs.collect(state)
    assert s["gate_reports"] == 3 and len(s["unreadable"]) == 2
    # доп. каталог отчетов и лог энфорсера там, где его пишет энфорсер
    _report(tmp_path / "ci-reports", "x", "2026-11-05T10:00:00+00:00",
            [("pr_validate", "FAIL")])
    elog_dir = tmp_path / "enf"
    elog_dir.mkdir()
    (elog_dir / "flow-enforcer.log").write_text(
        json.dumps({"ts": "2026-11-05T00:00:00+00:00", "event": "push_denied"}) + "\n",
        encoding="utf-8")
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(elog_dir))
    s2 = gs.collect(state, report_dirs=[tmp_path / "ci-reports"])
    assert s2["gates"]["pr_validate"] == {"FAIL": 1}
    assert s2["enforcer_events"] == {"push_denied": 1}
    monkeypatch.delenv("FLOW_ENFORCER_STATE_DIR")
    bad = tmp_path / "bad" / "flowctl_state.json"
    bad.parent.mkdir()
    bad.write_text("[]", encoding="utf-8")
    assert gs.main(["--state", str(bad)]) == 2
    r = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flowctl.py"),
                        "gates-stats", "--state", str(state), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["reason_codes"] == s["reason_codes"]
    text = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flowctl.py"),
                           "gates-stats", "--state", str(state)],
                          capture_output=True, text=True).stdout
    assert "flow_check: FAIL 1, PASS 2" in text and "WARN:" in text
    # копия flowctl без gates_stats.py (старый проект): падает только подкоманда
    import shutil
    scripts = tmp_path / "proj-scripts"
    shutil.copytree(FACTORY / "scripts", scripts,
                    ignore=shutil.ignore_patterns("gates_stats.py", "__pycache__"))
    shutil.copytree(FACTORY / "agents", tmp_path / "agents")
    miss = subprocess.run([sys.executable, str(scripts / "flowctl.py"), "gates-stats"],
                          capture_output=True, text=True)
    assert miss.returncode == 2 and "gates_stats.py" in miss.stderr
    ok = subprocess.run([sys.executable, str(scripts / "flowctl.py"), "status", "--help"],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr


def test_real_engine_records(tmp_path, monkeypatch):
    """TC-J65-GST-005: prepare dev_task без плана релиза — DENY, записанный
    настоящим flowctl; его коды видны в статистике. finish пишет отчеты в
    <state>/gate-reports — тот же каталог читает gates_stats."""
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
    src = (FACTORY / "scripts" / "flowctl.py").read_text(encoding="utf-8")
    assert 'report_dir=args.report_dir or str(state_path.parent / "gate-reports")' in src
    assert set(s["reason_codes"]) <= set(gs.ft.REASON_CODES)


def test_unobservable_codes_drift():
    """TC-J65-GST-006."""
    import re
    src = (FACTORY / "scripts" / "flow_transition.py").read_text(encoding="utf-8")
    for code in gs.ft.REASON_CODES:
        if not re.search(r"Finding\(\s*" + code + r"\b", src):
            assert code in gs.UNOBSERVABLE_CODES, code
    assert set(gs.UNOBSERVABLE_CODES) <= set(gs.ft.REASON_CODES)
