# -*- coding: utf-8 -*-
"""Тесты J57: детерминированный каркас возврата к J9.

Две механики:

1. `flowctl integrate <repo>` — сборка пакета: по реестру сессий показывает
   ветки пакета (flow/*, chore/*, pipeline/*) репозитория, REFUSE при
   активных сессиях (reserved/running/needs_attention), создает
   интеграционную ветку integration/<cid> от origin/main (фолбэк main)
   и печатает список веток для dev-lead'а. Merge/конфликты — семантика
   dev-lead; ветка отсюда не пушится.
2. push_gate (plugins/flow-enforcer): ПМ-push (вне делегации) в продуктовый
   репо требует маркера интеграции [integrate]/[pipeline] в subject HEAD
   ИЛИ влитого HEAD (merged); без — DENY [PM_PUSH_POLICY] «передай сборку
   dev-lead'у». Фабрика исключена (легитимные ПМ-пуши docs-заявок).

Фикстуры: tmp-репозитории, tmp-реестр, tmp-каталог логов — реальный
~/.hermes/state/ и пользовательские проекты не используются.

Трассировка: backlog/J57-pm-ops-worktree-2026-10-19.md; docs/
README-flow-control.md («Делегация и сборка пакета», J57); agents/README
роль №14 (триггер детерминированный).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402
import flowctl  # noqa: E402


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def make_repo(tmp_path: Path, name: str = "proj", subject: str = "wip") -> Path:
    """Tmp git-репозиторий с коммитом и refs/remotes/origin/main (=HEAD)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)  # exist_ok: j41-фикстура кладет PLAN в tmp_path/proj
    git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", subject)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def make_session(repo: Path, *, branch: str | None = "flow/j57-a",
                 status: str = "finished", cid: str | None = "j57-demo",
                 delegation: str = "deleg-j57-a", change: str | None = None,
                 project: str | None = None) -> dict:
    s = {"delegation_id": delegation, "role": "dev", "status": status,
         "repo": str(repo), "worktree": None}
    if branch is not None:
        s["branch"] = branch
    if cid is not None:
        s["correlation_id"] = cid
    if change is not None:
        s["change"] = change
    if project is not None:
        s["project"] = project
    return s


def write_registry(tmp_path: Path, sessions: list[dict]) -> Path:
    reg = tmp_path / "state" / "active_sessions.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps(
        {"schema_version": "active-sessions/2", "sessions": sessions},
        ensure_ascii=False), encoding="utf-8")
    return reg


def run_integrate(repo: Path, registry: Path, *extra: str):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = flowctl.main([
            "integrate", str(repo), "--registry", str(registry),
            "--json", *extra,
        ])
    out = json.loads(buf.getvalue()) if buf.getvalue().strip() else {}
    return code, out


# --------------------------------------------------------- flowctl integrate


def test_integrate_happy_creates_branch_from_origin_main(tmp_path):
    """Happy path: ветки пакета из реестра, integration/<cid> от origin/main."""
    repo = make_repo(tmp_path)
    # ветки пакета существуют в репо (делегации уже запушили локально)
    for b in ("flow/j57-a", "chore/j57-docs", "pipeline/j57-b"):
        git(repo, "branch", b, "HEAD")
    git(repo, "branch", "feature/not-package", "HEAD")  # вне префиксов пакета
    reg = write_registry(tmp_path, [
        make_session(repo, branch="flow/j57-a", status="finished"),
        make_session(repo, branch="chore/j57-docs", status="finished"),
        make_session(repo, branch="pipeline/j57-b", status="finished"),
        # чужой репо — не этот пакет
        make_session(tmp_path / "other", branch="flow/zzz",
                     status="finished", delegation="deleg-zzz"),
    ])
    code, out = run_integrate(repo, reg)
    assert code == 0, out
    assert out["integrated"] is True
    assert out["integration_branch"] == "integration/j57-demo"
    assert out["package_branches"] == [
        "chore/j57-docs", "flow/j57-a", "pipeline/j57-b"]
    assert out["base"] == "origin/main"
    assert "dev-lead" in out["note"]
    # ветка создана и указывает на origin/main; HEAD репо не переключен
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(repo, "rev-parse", "integration/j57-demo") == \
        git(repo, "rev-parse", "origin/main")


def test_integrate_refuses_active_sessions(tmp_path):
    """Активная сессия этого репо → REFUSE, ветка не создается."""
    repo = make_repo(tmp_path)
    reg = write_registry(tmp_path, [
        make_session(repo, branch="flow/j57-a", status="running"),
    ])
    code, out = run_integrate(repo, reg)
    assert code == 1
    assert out["integrated"] is False
    assert out["reason"] == flowctl.INTEGRATE_REASON_ACTIVE
    assert out["active_sessions"] == ["deleg-j57-a"]
    branches = git(repo, "branch", "--list", "integration/*").strip()
    assert branches == ""


def test_integrate_active_session_of_other_repo_does_not_block(tmp_path):
    """Активная сессия ДРУГОГО репо — не повод отказывать этому пакету."""
    repo = make_repo(tmp_path)
    other = make_repo(tmp_path, name="other")
    reg = write_registry(tmp_path, [
        make_session(other, branch="flow/zzz", status="reserved",
                     delegation="deleg-zzz"),
        make_session(repo, branch="flow/j57-a", status="finished"),
    ])
    code, out = run_integrate(repo, reg)
    assert code == 0, out
    assert out["active_sessions"] == []
    assert out["package_branches"] == ["flow/j57-a"]


def test_integrate_requires_cid_when_registry_ambiguous(tmp_path):
    """Нет --cid и реестр не дает однозначного id → отказ входа (exit 2)."""
    repo = make_repo(tmp_path)
    reg = write_registry(tmp_path, [
        make_session(repo, branch="flow/j57-a", status="finished", cid=None,
                     change=None),
    ])
    code, out = run_integrate(repo, reg)
    assert code == 2
    assert out["reason"] == flowctl.INTEGRATE_REASON_CID_REQUIRED
    assert git(repo, "branch", "--list", "integration/*").strip() == ""
    # явный --cid спасает
    code, out = run_integrate(repo, reg, "--cid", "j57-explicit")
    assert code == 0, out
    assert out["integration_branch"] == "integration/j57-explicit"


def test_integrate_never_recreates_existing_branch(tmp_path):
    """Существующая integration-ветка не пересоздается (idempotent, exit 1)."""
    repo = make_repo(tmp_path)
    reg = write_registry(tmp_path, [
        make_session(repo, branch="flow/j57-a", status="finished")])
    git(repo, "branch", "integration/j57-demo", "HEAD")
    # подвину origin/main вперед: пересоздание стерло бы dev-lead-работу
    (repo / "g.txt").write_text("y\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", "next")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    code, out = run_integrate(repo, reg)
    assert code == 1
    assert out["reason"] == flowctl.INTEGRATE_REASON_BRANCH_EXISTS
    assert git(repo, "rev-parse", "integration/j57-demo") == \
        git(repo, "rev-parse", "main~1")


# ------------------------------------------------- enforcer push_gate (J57)


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи/реестр в tmp, продуктовые репо — env."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(state / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    for var in ("FLOW_ENFORCER_PUSH", "FLOW_ENFORCER_PRODUCT_REPOS"):
        monkeypatch.delenv(var, raising=False)
    yield state


def test_push_gate_pm_denied_without_marker(tmp_path, monkeypatch):
    """ПМ-push в продуктовый репо без маркера/merged → DENY с подсказкой."""
    repo = make_repo(tmp_path)
    # новый коммит ПОВЕРХ origin/main без маркера — неинтегрированный HEAD
    (repo / "f.txt").write_text("pm-edit\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", "wip without marker")
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", str(repo))
    res = enforcer.push_gate({
        "command": f"git -C {repo} push origin main", "cwd": str(repo)})
    assert res is not None and res["action"] == "block"
    assert "PM_PUSH_POLICY" in res["message"]
    assert "передай сборку dev-lead'у" in res["message"]
    assert "flowctl integrate" in res["message"]


def test_push_gate_pm_allowed_with_integrate_marker(tmp_path, monkeypatch):
    """Маркер [integrate] в subject HEAD → пуш легален."""
    repo = make_repo(tmp_path)
    (repo / "f.txt").write_text("y\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", "[integrate] сборка пакета j57")
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", str(repo))
    res = enforcer.push_gate({
        "command": f"git -C {repo} push origin main", "cwd": str(repo)})
    assert res is None


def test_push_gate_pm_allowed_with_pipeline_marker(tmp_path, monkeypatch):
    """Легаси-маркер [pipeline] тоже принимается (pm_bounds-канон)."""
    repo = make_repo(tmp_path)
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "--allow-empty", "-m", "[pipeline] изменение конвейера")
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", str(repo))
    res = enforcer.push_gate({
        "command": f"git -C {repo} push origin main", "cwd": str(repo)})
    assert res is None


def test_push_gate_pm_allowed_when_head_already_merged(tmp_path, monkeypatch):
    """HEAD уже влит в origin/main (merged PR) → пуш легален без маркера."""
    repo = make_repo(tmp_path, subject="wip")
    # подвинули origin/main вперед так, что HEAD — его предок
    (repo / "f.txt").write_text("z\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", "next on origin")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", str(repo))
    res = enforcer.push_gate({
        "command": f"git -C {repo} push origin main", "cwd": str(repo)})
    assert res is None


def test_push_gate_factory_excluded(tmp_path, monkeypatch):
    """Фабрика — не продуктовое репо: ПМ-push docs-заявок не ломается,
    даже если factory попал в env-список."""
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", f"{FACTORY},{tmp_path}")
    res = enforcer.push_gate({
        "command": f"git -C {FACTORY} push origin main", "cwd": str(FACTORY)})
    assert res is None


def test_push_gate_delegated_push_unchanged(tmp_path, monkeypatch):
    """Делегированный пуш в ALLOW-ветку — прежнее поведение (не PM-ветка)."""
    repo = make_repo(tmp_path)
    monkeypatch.setenv("FLOW_ENFORCER_PRODUCT_REPOS", str(repo))
    branch = "pipeline/j57-delegated"
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-b", branch, str(wt))
    enforcer_path = Path(enforcer.worktree_registry_path())
    enforcer_path.parent.mkdir(parents=True, exist_ok=True)
    enforcer_path.write_text(json.dumps({"sessions": [{
        "delegation_id": "deleg-j57", "role": "dev", "status": "running",
        "repo": str(repo), "worktree": str(wt), "branch": branch}]}),
        encoding="utf-8")
    res = enforcer.push_gate({
        "command": f"git push origin {branch}", "cwd": str(wt)})
    assert res is None
    # а пуш main из-под делегации по-прежнему DENY [PUSH_POLICY]
    res = enforcer.push_gate({
        "command": "git push origin main", "cwd": str(wt)})
    assert res is not None and "PUSH_POLICY" in res["message"]
