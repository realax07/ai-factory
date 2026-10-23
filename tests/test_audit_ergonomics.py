# -*- coding: utf-8 -*-
"""Тесты эргономики flowctl/delegate_gate (аудит-блок АУД: Н6/Н7/Н8/Н12/Н14/Н18).

Н6: finish при pr_validate SKIPPED (нет PR-контекста) НЕ финализирует
    вердикт — статус provisional, сессия открыта; повторный finish с
    появившимся --pr-id пересчитывает ворота и финализирует.
Н7: prepare при ZONE_CONFLICT с finished-сессией (вердикт returned, работа
    не влита) показывает в диагностике команду авто-освобождения;
    --release-stale выполняет авто-reconcile (release + повтор резервации).
Н8: delegate_gate принимает и пробрасывает --incident-ref/--spec-delta/
    --paths/--small-change — Флоу 3/4/5 проходимы через машину делегаций.
Н12: диагностика AMBIGUOUS_STATE указывает конкретное невалидное поле;
     невалидный --flow — JSON-диагностика FLOW_ID_INVALID, не сырой argparse.
Н14: prepare --paths (через запятую) подает конкретные пути в protected-
     paths (J3) ворота: chore_task c --paths deploy/x = DENY J3 без маркера.
Н18: delegate_gate --registry PATH — sandbox-режим: боевой
     ~/.hermes/state/ не трогается.

Fixture-репозитории/реестры — в tmp_path; реальный ~/.hermes/state/ тесты
НЕ пишут (Н18-тест читает его read-only до/после).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flowctl  # noqa: E402
import test_flowctl as base  # noqa: E402  (общие fixture-хелперы)


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True,
                       check=True)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def registry_sessions(reg: Path) -> list[dict]:
    return json.loads(reg.read_text(encoding="utf-8")).get("sessions", [])


def prepare_argv(repo: Path, registry: Path, state: Path, tmp_path: Path,
                 **kw) -> list[str]:
    argv = [
        "prepare",
        "--repo", str(repo), "--project", "proj",
        "--flow", str(kw.get("flow", 1)),
        "--change", kw.get("change", "add-widget"),
        "--action", kw.get("action", "dev_task"),
        "--role", kw.get("role", "dev"),
        "--path", kw.get("path", "src/**"),
        "--owner-pm", "pm-main",
        "--registry", str(registry), "--state", str(state),
        "--audit", str(tmp_path / "audit.jsonl"),
        "--correlation-id", kw.get("cid", "corr0001"),
        "--json",
    ]
    task = kw.get("task", "1.1")
    if task is not None:
        argv += ["--task", task]
    for extra in kw.get("extra", []):
        argv.extend(extra)
    if kw.get("dry_run"):
        argv.append("--dry-run")
    return argv


def finish_argv(tmp_path: Path, reg: Path, state: Path, report: Path,
                cid: str = "corr0001", **kw) -> list[str]:
    argv = [
        "finish", "--correlation-id", cid,
        "--report", str(report),
        "--gate-scope", "post_agent",
        "--openspec-cmd", "true",
        "--pm-mode", "commits", "--pm-commits", "HEAD",
        "--registry", str(reg), "--state", str(state),
        "--audit", str(tmp_path / "audit.jsonl"),
        "--log-dir", str(tmp_path / "logs"),
        "--report-dir", str(tmp_path / "greports"),
        "--json",
    ]
    if kw.get("gates"):
        argv += ["--gates", kw["gates"]]
    if kw.get("pr_id"):
        argv += ["--pr-id", str(kw["pr_id"])]
    return argv


def run_flowctl(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
        capture_output=True, text=True,
    )


def run_delegate_gate(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "delegate_gate.py"), *argv],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def prepare_and_run(tmp_path: Path, repo: Path, reg: Path, state: Path,
                    cid: str = "corr0001", **kw) -> Path:
    """prepare + run + «работа агента» в зоне (для finish-тестов)."""
    r = run_flowctl(*prepare_argv(repo, reg, state, tmp_path, cid=cid, **kw))
    assert r.returncode == 0, r.stdout + r.stderr
    r = run_flowctl("run", "--correlation-id", cid,
                    "--registry", str(reg), "--state", str(state), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    write(repo, kw.get("work_file", "src/widget.py"), "X = 42\n")
    git("-C", str(repo), "add", "-A")
    git("-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", "dev: работа в зоне")
    report = tmp_path / f"report-{cid}.md"
    report.write_text("# Отчет\nизменено в зоне\n", encoding="utf-8")
    return report


def finish_returned_out_of_zone(tmp_path: Path, repo: Path, reg: Path,
                                state: Path, cid: str = "corr0001") -> None:
    """Доводит сессию до финального returned (работа не влита): коммит вне
    зоны → вердикт returned, реестр: finished (зону продолжает держать)."""
    report = prepare_and_run(tmp_path, repo, reg, state, cid=cid,
                             work_file="tests/out_of_zone_probe.py")
    r = run_flowctl(*finish_argv(tmp_path, reg, state, report, cid=cid))
    assert r.returncode == 1, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["verdict"] == "returned"


def make_chore_repo(tmp_path: Path) -> Path:
    """Fixture-репозиторий Флоу 4: change=chore + легкий план PLAN-chore.md."""
    repo = base.make_repo(tmp_path)
    write(repo, "PLAN-chore.md", "# PLAN-chore\n\n**Флоу: 4** (легкий план).\n")
    git("-C", str(repo), "add", "-A")
    git("-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", "chore: план")
    return repo


# ------------------------------------------------------------------- Н6


class TestN6ProvisionalFinish:
    def test_finish_pr_validate_skipped_not_finalized(self, tmp_path):
        """pr_validate SKIPPED (нет PR-контекста) → вердикт provisional:
        НЕ финализирован, сессия открыта (running в реестре)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = prepare_and_run(tmp_path, repo, reg, state)
        r = run_flowctl(*finish_argv(tmp_path, reg, state, report,
                                     gates="pr_validate"))
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["verdict"] == "provisional"
        assert data["provisional"] is True
        assert "pr_validate" in data["skipped_gates"]
        # State: статус provisional (не финальный).
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "provisional"
        assert rec["provisional"]["skipped_gates"] == ["pr_validate"]
        # Реестр: сессия НЕ закрыта (зона удерживается до финального finish).
        sessions = registry_sessions(reg)
        assert len(sessions) == 1
        assert sessions[0]["status"] == "running"

    def test_finish_with_pr_id_refinalizes(self, tmp_path):
        """Повторный finish с появившимся --pr-id пересчитывает ворота и
        выносит ФИНАЛЬНЫЙ вердикт (provisional больше не возвращается)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = prepare_and_run(tmp_path, repo, reg, state)
        r1 = run_flowctl(*finish_argv(tmp_path, reg, state, report,
                                      gates="pr_validate"))
        assert json.loads(r1.stdout)["verdict"] == "provisional"
        # PR-контекст появился: pr_validate выполняется (без реального PR
        # ворота честно FAIL — вердикт final, не provisional).
        r2 = run_flowctl(*finish_argv(tmp_path, reg, state, report,
                                      gates="pr_validate", pr_id=4242))
        data2 = json.loads(r2.stdout)
        assert data2["verdict"] != "provisional"
        assert data2["verdict"] in ("accepted", "returned", "blocked")
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == data2["verdict"]
        sessions = registry_sessions(reg)
        assert sessions[0]["status"] == "finished"

    def test_provisional_repeat_without_pr_id_stays_provisional(self, tmp_path):
        """Повтор finish без PR-контекста — снова provisional (не blocked)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = prepare_and_run(tmp_path, repo, reg, state)
        for _ in range(2):
            r = run_flowctl(*finish_argv(tmp_path, reg, state, report,
                                         gates="pr_validate"))
            data = json.loads(r.stdout)
            assert data["verdict"] == "provisional"
        assert registry_sessions(reg)[0]["status"] == "running"


# ------------------------------------------------------------------- Н7


class TestN7ReleaseStale:
    def _setup(self, tmp_path):
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        return repo, reg, state

    def test_zone_conflict_diagnoses_stale_holder_with_release_cmd(
            self, tmp_path):
        """ZONE_CONFLICT с finished+returned-сессией: диагностика содержит
        держателя и ГОТОВУЮ команду авто-освобождения."""
        repo, reg, state = self._setup(tmp_path)
        finish_returned_out_of_zone(tmp_path, repo, reg, state, cid="corrA")
        r = run_flowctl(*prepare_argv(repo, reg, state, tmp_path, cid="corrB"))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["reservation"]["reason"] == "ZONE_CONFLICT"
        assert data["stale_holders"], "держатель не найден в диагностике"
        holder = data["stale_holders"][0]
        assert holder["correlation_id"] == "corrA"
        assert holder["verdict"] == "returned"
        assert "release" in holder["release_cmd"]
        assert "corrA" in holder["release_cmd"]
        # Без --release-stale ничего не освобождено:
        statuses = {s["delegation_id"]: s["status"]
                    for s in registry_sessions(reg)}
        assert "released" not in statuses.values()

    def test_release_stale_auto_reconciles_and_reserves(self, tmp_path):
        """--release-stale: finished+returned-держатель освобожден, резервация
        нового prepare прошла, worktree/записи не удалены."""
        repo, reg, state = self._setup(tmp_path)
        finish_returned_out_of_zone(tmp_path, repo, reg, state, cid="corrA")
        r = run_flowctl(*prepare_argv(
            repo, reg, state, tmp_path, cid="corrB",
            extra=[["--release-stale"]]))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["prepared"] is True
        assert any("RELEASED_STALE" in w for w in data["warnings"])
        statuses = {s["delegation_id"]: s["status"]
                    for s in registry_sessions(reg)}
        assert sorted(statuses.values()) == ["released", "reserved"]
        # State-запись держателя честно помечена released (не удалена).
        rec_a = json.loads(state.read_text(encoding="utf-8"))["runs"]["corrA"]
        assert rec_a["status"] == "released"

    def test_release_stale_does_not_touch_running_holder(self, tmp_path):
        """Живой (running) держатель — не stale: авто-освобождения нет."""
        repo, reg, state = self._setup(tmp_path)
        run_flowctl(*prepare_argv(repo, reg, state, tmp_path, cid="corrA"))
        run_flowctl("run", "--correlation-id", "corrA",
                    "--registry", str(reg), "--state", str(state))
        r = run_flowctl(*prepare_argv(
            repo, reg, state, tmp_path, cid="corrB",
            extra=[["--release-stale"]]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["reservation"]["reason"] == "ZONE_CONFLICT"
        assert data["stale_holders"] == []
        assert data["released_stale"] == []
        statuses = [s["status"] for s in registry_sessions(reg)]
        assert statuses.count("running") == 1  # держатель не тронут


# ------------------------------------------------------------------- Н8


class TestN8DelegateGateFlows:
    """Флоу 3/4/5 проходимы через машину делегаций (delegate_gate start)."""

    def test_flow3_hotfix_through_gate(self, tmp_path):
        repo = base.make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "3", "--change", "BUG-042",
            "--action", "emergency_stabilize", "--role", "dev",
            "--incident-ref", "S2-login-500", "--path", "src/**",
            "--owner-pm", "pm-main",
            "--registry", str(reg))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "GATE: ALLOW" in r.stdout
        sessions = registry_sessions(reg)
        assert len(sessions) == 1
        assert sessions[0]["status"] == "running"
        assert sessions[0]["role"] == "dev"

    def test_flow3_without_incident_ref_denied(self, tmp_path):
        """Без проброса --incident-ref машина Флоу 3 честно DENY-ит."""
        repo = base.make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "3", "--change", "BUG-042",
            "--action", "emergency_stabilize", "--role", "dev",
            "--path", "src/**", "--registry", str(reg))
        assert r.returncode == 1
        assert "GATE: prepare не прошел" in r.stderr
        assert registry_sessions(reg) == []

    def test_flow4_chore_through_gate(self, tmp_path):
        repo = make_chore_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "4", "--change", "chore",
            "--action", "chore_task", "--role", "dev",
            "--path", "scripts/**", "--paths", "scripts/tool.py",
            "--owner-pm", "pm-main", "--registry", str(reg))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "GATE: ALLOW" in r.stdout
        assert registry_sessions(reg)[0]["status"] == "running"

    def test_flow5_express_through_gate(self, tmp_path):
        repo = base.make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "5", "--change", "quick-widget",
            "--action", "express_task", "--role", "dev",
            "--small-change", "--path", "src/**",
            "--owner-pm", "pm-main", "--registry", str(reg))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "GATE: ALLOW" in r.stdout
        assert registry_sessions(reg)[0]["status"] == "running"

    def test_flow5_without_small_change_not_allowed(self, tmp_path):
        """Флоу 5 без --small-change машина не пропускает (UNKNOWN)."""
        repo = base.make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "5", "--change", "quick-widget",
            "--action", "express_task", "--role", "dev",
            "--path", "src/**", "--registry", str(reg))
        assert r.returncode == 1


# ------------------------------------------------------------------- Н18


def _file_state(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestN18RegistrySandbox:
    def test_registry_flag_does_not_touch_prod_state(self, tmp_path):
        """delegate_gate start --registry PATH: боевой ~/.hermes/state не
        меняется (ни active_sessions.json, ни flowctl_state.json)."""
        prod_reg = Path.home() / ".hermes" / "state" / "active_sessions.json"
        prod_state = Path.home() / ".hermes" / "state" / "flowctl_state.json"
        before = (_file_state(prod_reg), _file_state(prod_state))
        repo = base.make_repo(tmp_path)
        sandbox_reg = tmp_path / "sandbox" / "active_sessions.json"
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "5", "--change", "quick-widget",
            "--action", "express_task", "--role", "dev",
            "--small-change", "--path", "src/**",
            "--registry", str(sandbox_reg))
        assert r.returncode == 0, r.stdout + r.stderr
        after = (_file_state(prod_reg), _file_state(prod_state))
        assert before == after, "боевой ~/.hermes/state изменился (Н18)"
        # Сессия — в sandbox-реестре (state рядом с ним):
        sessions = registry_sessions(sandbox_reg)
        assert len(sessions) == 1
        sandbox_state = sandbox_reg.parent / "flowctl_state.json"
        assert sandbox_state.is_file()
        runs = json.loads(sandbox_state.read_text(encoding="utf-8"))["runs"]
        assert len(runs) == 1

    def test_registry_flag_finish_also_sandboxed(self, tmp_path):
        """finish с --registry тоже не трогает боевые пути."""
        prod_reg = Path.home() / ".hermes" / "state" / "active_sessions.json"
        prod_state = Path.home() / ".hermes" / "state" / "flowctl_state.json"
        before = (_file_state(prod_reg), _file_state(prod_state))
        repo = base.make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        r = run_delegate_gate(
            "start", "--repo", str(repo), "--project", "proj",
            "--flow", "5", "--change", "quick-widget",
            "--action", "express_task", "--role", "dev",
            "--small-change", "--path", "src/**",
            "--registry", str(reg))
        assert r.returncode == 0, r.stdout + r.stderr
        cid = registry_sessions(reg)[0]["delegation_id"].replace(
            "deleg-", "", 1)
        # finish в sandbox: некорректный отчет → finish не принят, но пути
        # боевые не тронуты.
        report = tmp_path / "no-report.md"
        r2 = run_delegate_gate(
            "finish", "--correlation-id", cid, "--report", str(report),
            "--flow", "5", "--repo", str(repo), "--registry", str(reg))
        assert r2.returncode != 0
        assert (_file_state(prod_reg), _file_state(prod_state)) == before


# ------------------------------------------------------------------- Н12


class TestN12Diagnostics:
    def test_ambiguous_state_names_invalid_field(self, tmp_path):
        """AMBIGUOUS_STATE: диагностика называет поле — scope=xxx не
        соответствует формату Флоу 3 (BUG-NNN)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*prepare_argv(repo, reg, state, tmp_path,
                                      flow=3, change="xxx",
                                      action="emergency_stabilize",
                                      task=None,
                                      extra=[["--incident-ref", "S2-inc-1"]]))
        assert r.returncode == 2  # AMBIGUOUS_STATE → UNKNOWN (exit 2)
        data = json.loads(r.stdout)
        hints = data.get("field_diagnostics") or []
        assert hints, "нет field_diagnostics при AMBIGUOUS_STATE"
        assert any(
            "scope=xxx" in h and "Флоу 3 (BUG-NNN" in h for h in hints), hints
        # record.decision реально содержит AMBIGUOUS_STATE:
        decision = data["record"]["decision"]
        assert any("AMBIGUOUS_STATE" in str(x) for x in
                   decision["blocking_reasons"] + decision["details"])
        assert registry_sessions(reg) == []

    def test_ambiguous_state_flow4_names_chore_format(self, tmp_path):
        repo = make_chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*prepare_argv(repo, reg, state, tmp_path,
                                      flow=4, change="mysmallfix",
                                      action="chore_task", task=None))
        assert r.returncode == 1
        hints = json.loads(r.stdout).get("field_diagnostics") or []
        assert any("Флоу 4" in h and "[chore]" in h for h in hints), hints

    def test_invalid_flow_json_diagnostic_not_argparse(self, tmp_path):
        """Невалидный --flow — JSON-диагностика FLOW_ID_INVALID (не сырой
        argparse-usage в stderr)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv[argv.index("--flow") + 1] = "9"
        r = run_flowctl(*argv)
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["error"] == "FLOW_ID_INVALID"
        assert data["field"] == "--flow"
        assert data["value"] == "9"
        assert "1–5" in data["expected"]
        # Сырого argparse-usage нет (диагностика — в stdout JSON).
        assert "usage:" not in r.stderr

    def test_invalid_flow_non_numeric(self, tmp_path):
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv[argv.index("--flow") + 1] = "hotfix"
        r = run_flowctl(*argv)
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["error"] == "FLOW_ID_INVALID"
        assert data["value"] == "hotfix"

    def test_valid_flow_still_accepted(self, tmp_path):
        """Регресс: валидный --flow по-прежнему работает (dry-run ALLOW)."""
        repo = base.make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*prepare_argv(repo, reg, state, tmp_path,
                                      dry_run=True) )
        assert r.returncode == 0
        assert json.loads(r.stdout)["decision"]["status"] == "ALLOW"


# ------------------------------------------------------------------- Н14


class TestN14ProtectedPathsGate:
    def _chore_argv(self, tmp_path, repo, reg, state, **kw):
        return prepare_argv(repo, reg, state, tmp_path, flow=4,
                            change="chore", action="chore_task", task=None,
                            path="scripts/**", **kw)

    def test_chore_task_paths_deploy_denied_j3_without_marker(self, tmp_path):
        """chore_task c --paths deploy/x без [pipeline]-маркера = DENY J3,
        reservation не создается (раньше ворота молча проходили)."""
        repo = make_chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*self._chore_argv(
            tmp_path, repo, reg, state, extra=[["--paths", "deploy/x"]]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["reason"] == "J3_PROTECTED_PATHS"
        assert data["protected_paths"] == ["deploy/x"]
        assert registry_sessions(reg) == []
        assert not state.exists() or json.loads(
            state.read_text(encoding="utf-8"))["runs"] == {}

    def test_chore_task_paths_deploy_with_marker_allowed(self, tmp_path):
        """[pipeline]-маркер снимает J3-отказ — prepare проходит."""
        repo = make_chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*self._chore_argv(
            tmp_path, repo, reg, state,
            extra=[["--paths", "deploy/x"], ["--pipeline-marker"]]))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["prepared"] is True
        assert data["record"]["zones"] == ["scripts/**"]

    def test_chore_task_paths_contracts_denied(self, tmp_path):
        """--paths contracts/api.yaml (защищенный префикс) — тоже DENY J3."""
        repo = make_chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*self._chore_argv(
            tmp_path, repo, reg, state,
            extra=[["--paths", "scripts/a.sh,contracts/api.yaml"]]))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["protected_paths"] == ["contracts/api.yaml"]

    def test_paths_without_protected_hits_passes(self, tmp_path):
        """--paths вне защищенных префиксов ворота J3 не трогает."""
        repo = make_chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = run_flowctl(*self._chore_argv(
            tmp_path, repo, reg, state,
            extra=[["--paths", "scripts/tool.py"]]))
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["prepared"] is True
