# -*- coding: utf-8 -*-
"""J64.14: остаток ревью J63 — раннер и flowctl.

Трассировка:
  TC-J64-J63-001  gc: worktree пакета раннера без finished_at в state — не
                  сносится (маркер в git-dir); докатан — сносится как раньше
  TC-J64-J63-002  отказ после finish accepted: запись цикла →
                  rejected_after_accept, резервация finished → needs_attention
  TC-J64-J63-003  flowctl phase по клону видит запись со scope.repo = worktree
  TC-J64-J63-004  finish --pm-resume при закрытой резервации — отказ без
                  перевода записи в running
  TC-J64-J63-005  git_main_root: worktree bare-репозитория — общий ключ
  TC-J64-J63-006  flowctl close: accepted + finished → closed; не accepted — отказ
  TC-J64-J63-007  gate-стадия оставила файлы — STOP с перечнем (не OUT_OF_ZONE
                  следующей pi-стадии); свой файл вердикта — норма
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flowctl as fc  # noqa: E402
import package_runner as pr  # noqa: E402
import session_check as sc  # noqa: E402
import test_package_runner as tpr  # noqa: E402  (модулем: тесты не собираются повторно)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_git(path: Path) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", str(path))
    git("-C", str(path), "config", "user.email", "t@t")
    git("-C", str(path), "config", "user.name", "t")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    git("-C", str(path), "add", "-A")
    git("-C", str(path), "commit", "-qm", "init")
    return path


def test_gc_runner_guard(tmp_path):
    """TC-J64-J63-001."""
    repo = make_git(tmp_path / "repo")
    wt = tmp_path / "wt"
    git("-C", str(repo), "worktree", "add", "-q", "-b", "pkg", str(wt))
    assert fc.gc_runner_guard(wt) is None                   # маркера нет
    spath = tmp_path / "PLAN-x.md.runner-state.json"
    spath.write_text(json.dumps({"stages": {}}), encoding="utf-8")
    pr.write_package_marker(wt, tmp_path / "PLAN-x.md", spath)
    assert "не докатан" in fc.gc_runner_guard(wt)
    spath.write_text(json.dumps({"finished_at": "2026-11-11T00:00:00Z"}), encoding="utf-8")
    assert fc.gc_runner_guard(wt) is None
    assert not git("-C", str(wt), "status", "--porcelain")  # маркер не в дереве


def _registry(tmp_path, status, delegation="deleg-abc"):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({
        "schema_version": sc.REGISTRY_SCHEMA,
        "sessions": [{"delegation_id": delegation, "status": status,
                      "zones": ["src/**"], "repo": str(tmp_path)}]}),
        encoding="utf-8")
    return reg


def _session_status(reg):
    return json.loads(reg.read_text(encoding="utf-8"))["sessions"][0]["status"]


def test_rejected_after_accept(tmp_path):
    """TC-J64-J63-002."""
    reg = _registry(tmp_path, "finished")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {"status": "accepted",
                                                 "delegation_id": "deleg-abc"}}}),
                     encoding="utf-8")
    gate = {"registry": str(reg), "delegation_id": "deleg-abc", "kind": "flowctl",
            "state": str(state), "cid": "c1"}
    pr.mark_rejected_after_accept(gate, "коммит стадии не создан")
    assert _session_status(reg) == "needs_attention"
    rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["c1"]
    assert rec["status"] == pr.REJECTED_AFTER_ACCEPT
    assert "коммит" in rec["rejected_after_accept"]["reason"]


def test_phase_sees_worktree_scope(tmp_path, capsys):
    """TC-J64-J63-003."""
    repo = make_git(tmp_path / "clone")
    wt = tmp_path / "wt"
    git("-C", str(repo), "worktree", "add", "-q", "-b", "pkg", str(wt))
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {
        "status": "accepted", "action": "chore_task",
        "finished_at": "2026-11-11T00:00:00Z",
        "scope": {"change": "chore-x", "flow": 4, "repo": str(wt),
                  "project": "proj"}}}}),
        encoding="utf-8")
    fc.main(["phase", "--repo", str(repo), "--project", "proj", "--flow", "4",
             "--scope", "chore-x", "--state", str(state)])
    out = json.loads(capsys.readouterr().out)
    assert out["phase"] != "none", out


def test_pm_resume_closed_registry_refused(tmp_path, capsys):
    """TC-J64-J63-004."""
    reg = _registry(tmp_path, "closed")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {
        "status": "blocked", "delegation_id": "deleg-abc", "registry": str(reg),
        "defects": [{"code": "ERROR", "source": "gate"}],
        "scope": {"repo": str(tmp_path)}}}}), encoding="utf-8")
    report = tmp_path / "rep.md"
    report.write_text("# r\n", encoding="utf-8")
    assert fc.main([
        "finish", "--correlation-id", "c1", "--report", str(report),
        "--pm-resume", "--registry", str(reg), "--state", str(state), "--json"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["registry_status"] == "closed"
    rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["c1"]
    assert rec["status"] == "blocked"                  # не ушла в running


def test_git_main_root_bare(tmp_path):
    """TC-J64-J63-005."""
    src = make_git(tmp_path / "src")
    bare = tmp_path / "repo.git"
    git("clone", "-q", "--bare", str(src), str(bare))
    w1, w2 = tmp_path / "w1", tmp_path / "w2"
    git("-C", str(bare), "worktree", "add", "-q", "-b", "b1", str(w1))
    git("-C", str(bare), "worktree", "add", "-q", "-b", "b2", str(w2))
    r1, r2 = sc.git_main_root(w1), sc.git_main_root(w2)
    assert r1 == r2 and Path(r1).resolve() == bare.resolve()
    assert Path(sc.git_main_root(src)).resolve() == src.resolve()   # обычный — как был


@pytest.mark.parametrize("record_status,reg_status,rc,closed", [
    ("accepted", "finished", 0, True),
    ("returned", "finished", 1, False),
    ("accepted", "running", 1, False),
])
def test_close(tmp_path, capsys, record_status, reg_status, rc, closed):
    """TC-J64-J63-006."""
    reg = _registry(tmp_path, reg_status)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {"status": record_status,
                                                 "delegation_id": "deleg-abc"}}}),
                     encoding="utf-8")
    assert fc.main(["close", "c1", "--registry", str(reg),
                    "--state", str(state), "--json"]) == rc
    assert json.loads(capsys.readouterr().out)["closed"] is closed
    assert (_session_status(reg) == "closed") is closed


GATE_ONLY = """\
# PLAN-g

**Флоу: 4**

```yaml
pipeline:
  package: g-pkg
  flow: 4
  stages:
    - id: lint
      run: gate:make lint
```
"""


def test_gate_leftovers_stop(tmp_path, monkeypatch, capsys):
    """TC-J64-J63-007."""
    repo = tpr.make_repo(tmp_path)
    plan = tpr.write_plan(repo, GATE_ONLY, name="PLAN-g.md")

    def gate_leaves_file(cmd, cwd, timeout, stand_env=None):
        (cwd / "lint-report.txt").write_text("x", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(pr, "run_shell", gate_leaves_file)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) != 0
    err = capsys.readouterr().err
    assert "gate-стадия оставила изменения" in err and "lint-report.txt" in err


# ------------------------------------------------ review-001: интеграция


def _gc_worktrees(tmp_path, monkeypatch, sessions):
    reg = tmp_path / "gcreg.json"
    reg.write_text(json.dumps({"schema_version": sc.REGISTRY_SCHEMA,
                               "sessions": sessions}), encoding="utf-8")
    monkeypatch.setattr(fc, "gc_collect_docker", lambda: (None, "docker: тест"),
                        raising=False)
    plan = fc.gc_plan(argparse.Namespace(repo=None, registry=str(reg),
                                         min_age_hours=24))
    return plan["worktrees"]


def test_gc_plan_closed_and_runner_marker(tmp_path, monkeypatch):
    """TC-J64-J63-001: closed — done; пакет без finished_at держит worktree,
    докатанный — сносится; сессия finished→closed (flowctl close) сносится."""
    repo = make_git(tmp_path / "repo")
    wt = tmp_path / "wt"
    git("-C", str(repo), "worktree", "add", "-q", "-b", "pkg", str(wt))
    spath = tmp_path / "s.json"
    spath.write_text(json.dumps({}), encoding="utf-8")
    pr.write_package_marker(wt, tmp_path / "PLAN.md", spath)
    sessions = [{"delegation_id": "a", "status": "closed", "worktree": str(wt)},
                {"delegation_id": "b", "status": "released", "worktree": str(wt)}]
    w = _gc_worktrees(tmp_path, monkeypatch, sessions)
    assert not w["remove"] and all("не докатан" in r["reason"] for r in w["list_only"])
    spath.write_text(json.dumps({"finished_at": "x"}), encoding="utf-8")
    w = _gc_worktrees(tmp_path, monkeypatch, sessions)
    assert {r["delegation_id"] for r in w["remove"]} == {"a", "b"}
    sessions.append({"delegation_id": "c", "status": "running", "worktree": str(wt)})
    w = _gc_worktrees(tmp_path, monkeypatch, sessions)
    assert not w["remove"]                               # делит активная сессия


def test_phase_after_worktree_removed(tmp_path, capsys):
    """TC-J64-J63-003: repo_root в записи — phase и после сноса worktree."""
    repo = make_git(tmp_path / "clone")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {
        "status": "accepted", "action": "chore_task",
        "finished_at": "2026-11-11T00:00:00Z",
        "repo_root": sc.git_main_root(repo),
        "scope": {"change": "chore-x", "flow": 4, "project": "proj",
                  "repo": str(tmp_path / "gone-worktree")}}}}), encoding="utf-8")
    fc.main(["phase", "--repo", str(repo), "--project", "proj", "--flow", "4",
             "--scope", "chore-x", "--state", str(state)])
    assert json.loads(capsys.readouterr().out)["phase"] != "none"


def test_close_idempotent_and_lifecycle(tmp_path, capsys):
    """TC-J64-J63-006: повтор close — idempotent; событие в lifecycle записи."""
    reg = _registry(tmp_path, "finished")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"runs": {"c1": {"status": "accepted",
                                                 "delegation_id": "deleg-abc"}}}),
                     encoding="utf-8")
    argv = ["close", "c1", "--registry", str(reg), "--state", str(state), "--json"]
    assert fc.main(argv) == 0
    capsys.readouterr()
    assert fc.main(argv) == 0
    assert json.loads(capsys.readouterr().out).get("idempotent") is True
    hist = json.loads(state.read_text(encoding="utf-8"))["runs"]["c1"]["lifecycle"]["history"]
    assert hist[0]["event"] == "close"


def test_gate_leftovers_resume_still_stops(tmp_path, monkeypatch, capsys):
    """TC-J64-J63-007: resume после STOP не пропускает файлы прошлой попытки."""
    repo = tpr.make_repo(tmp_path)
    plan = tpr.write_plan(repo, GATE_ONLY, name="PLAN-g.md")

    def gate_leaves_file(cmd, cwd, timeout, stand_env=None):
        (cwd / "lint-report.txt").write_text("x", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(pr, "run_shell", gate_leaves_file)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) != 0
    capsys.readouterr()
    assert pr.cmd_run(plan, dry_run=False) != 0          # resume — снова STOP
    assert "lint-report.txt" in capsys.readouterr().err
