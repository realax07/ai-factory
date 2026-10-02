# -*- coding: utf-8 -*-
"""Тесты подключения flow_mode к компонентам (решение Заказчика 2026-10-02).

Инфраструктура scripts/flow_mode.py (get_mode/blocks_on, FLOW_MODE_FILE)
подключена к: flowctl (run/prepare/finish), gate_runner (run/status),
session_check (mode в ответах). Проверяется семантика blocks_on:

- shadow (файла нет / битый файл / mode=shadow): решения вычисляются,
  но не блокируют запуск — run разрешен при DENY-решении prepare;
- enforcing: DENY и UNKNOWN блокируют (отказ с кодом причины, no-op);
  переключение режима в live-процессе меняет поведение;
- gate_runner: enforcing + overall!=PASS → exit 1; shadow → exit как
  раньше (FAIL=1, ERROR=2, PASS=0);
- session_check: reserve строгий в обоих режимах (конфликт зон → отказ);
  mode присутствует в ответах reserve/check/reconcile/status (кроме
  ошибок входа).

Fixture-репозитории/реестры в tmp_path; режим — через FLOW_MODE_FILE,
реальный ~/.hermes/state/flow_mode.json не используется.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_mode  # noqa: E402
import gate_runner as gr  # noqa: E402

# --------------------------------------------------------------- helpers


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")
TASKS = "# Tasks\n\n- [ ] 1.1 реализовать виджет\n"


def make_repo(tmp_path: Path, *, req: str | None = REQ_APPROVED) -> Path:
    """Fixture-репозиторий Флоу 1 (как в test_flowctl.make_repo)."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    if req:
        write(repo, "requirements.md", req)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "openspec/changes/add-widget/design.md", "# d\n")
    write(repo, "openspec/changes/add-widget/tasks.md", TASKS)
    write(repo, "openspec/changes/add-widget/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "code-reviews/add-widget/review-001-1.1.md", "## Вердикт: approve\n")
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "src/widget.py", "X = 1\n")
    commit_all(repo)
    return repo


def make_repo_deny(tmp_path: Path) -> Path:
    """Полный ALLOW-репозиторий, где задача 1.1 уже закрыта → dev_task
    DENY (задача не открыта)."""
    repo = make_repo(tmp_path)
    write(repo, "openspec/changes/add-widget/tasks.md",
          "# Tasks\n\n- [x] 1.1 реализовать виджет\n")
    commit_all(repo, "task done")
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def flowctl_cmd(*argv: str, env_mode_file: Path | None = None):
    env = dict(os.environ)
    if env_mode_file is not None:
        env["FLOW_MODE_FILE"] = str(env_mode_file)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
        capture_output=True, text=True, env=env,
    )


def prepare_argv(repo: Path, registry: Path, state: Path, tmp_path: Path,
                 **kw) -> list[str]:
    argv = [
        "prepare",
        "--repo", str(repo), "--project", "proj", "--flow", "1",
        "--change", "add-widget", "--task", "1.1",
        "--action", kw.get("action", "dev_task"),
        "--role", kw.get("role", "dev"),
        "--path", "src/**",
        "--owner-pm", "pm-main",
        "--registry", str(registry), "--state", str(state),
        "--correlation-id", kw.get("cid", "corr0001"),
        "--json",
    ]
    if kw.get("dry_run"):
        argv.append("--dry-run")
    return argv


def set_mode_file(path: Path, mode: str | None) -> Path:
    """mode=None → файла нет (fail-soft shadow); иначе {'mode': mode}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        if path.exists():
            path.unlink()
    else:
        path.write_text(json.dumps({"mode": mode}), encoding="utf-8")
    return path


def session_check_cmd(*argv: str, env_mode_file: Path | None = None):
    env = dict(os.environ)
    if env_mode_file is not None:
        env["FLOW_MODE_FILE"] = str(env_mode_file)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "session_check.py"), *argv],
        capture_output=True, text=True, env=env,
    )


# --------------------------------------------- blocks_on: модульный уровень


class TestBlocksOnUnit:
    def test_shadow_missing_file_never_blocks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(tmp_path / "nope.json"))
        assert flow_mode.get_mode() == "shadow"
        assert flow_mode.blocks_on(True) is False

    def test_shadow_mode_blocks_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "shadow")))
        assert flow_mode.blocks_on(True) is False
        assert flow_mode.blocks_on(False) is False

    def test_enforcing_blocks_deny_and_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        assert flow_mode.blocks_on(True) is True   # DENY/UNKNOWN
        assert flow_mode.blocks_on(False) is False  # ALLOW

    def test_corrupt_file_fails_soft_to_shadow(self, tmp_path, monkeypatch):
        mf = tmp_path / "m.json"
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("FLOW_MODE_FILE", str(mf))
        assert flow_mode.get_mode() == "shadow"
        assert flow_mode.blocks_on(True) is False


# ------------------------------------- flowctl run: enforcing блокирует DENY


class TestFlowctlRunEnforcement:
    def _cycle(self, tmp_path, *, mode):
        """prepare в shadow c DENY-решением (запись создается, исполнение
        нет), затем run при заданном режиме."""
        repo = make_repo_deny(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = tmp_path / "flow_mode.json"
        set_mode_file(mf, "shadow")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        assert r.returncode == 1  # prepare: DENY → 1, запись с decision есть
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "prepared"
        assert rec["decision"]["status"] == "DENY"
        data = json.loads(r.stdout)
        assert data["record"]["decision"]["status"] == "DENY"
        # prepare при DENY reservation не создает (честный отказ): делаем
        # резервацию сами — тот же payload, что создал бы ALLOW-prepare,
        # чтобы run имел реальную reservation для перевода в running.
        import session_check as sc
        res = sc.reserve({
            "repo": str(repo),
            "delegation_id": rec["delegation_id"],
            "role": "dev",
            "project": "proj",
            "owner_pm": "pm-main",
            "paths": rec["zones"],
            "policy_version": rec["policy_version"],
            "worktree": None,
            "branch": None,
            "base_sha": git(repo, "rev-parse", "HEAD"),
            "snapshot_digest": rec["prepared_digest"],
        }, reg)
        assert res["allowed"] is True, res
        # registry_digest входит в snapshot digest: осевший снимок prepare
        # делается ПОСЛЕ reservation. Снимаем так же, как flowctl (п.7),
        # и записываем digest в state — иначе run увидит STALE_SNAPSHOT.
        import flow_state as fs
        snap2 = fs.inspect(
            repo_arg=str(repo), project="proj", flow=1,
            change_id="add-widget", task_id="1.1", registry=str(reg))
        def _resnap(st: dict) -> None:
            st["runs"]["corr0001"]["prepared_digest"] = snap2["snapshot_digest"]
        from flowctl import state_write_locked  # тот же механизм записи
        state_write_locked(state, json.loads(state.read_text(encoding="utf-8")),
                           _resnap)
        # run при заданном режиме:
        set_mode_file(mf, mode)
        return flowctl_cmd("run", "--correlation-id", "corr0001",
                           "--registry", str(reg), "--state", str(state),
                           "--json", env_mode_file=mf), state

    def test_shadow_run_allowed_after_deny_prepare(self, tmp_path):
        r, state = self._cycle(tmp_path, mode="shadow")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["started"] is True
        assert json.loads(
            state.read_text(encoding="utf-8"))["runs"]["corr0001"]["status"] \
            == "running"

    def test_enforcing_run_blocked_on_deny(self, tmp_path):
        r, _ = self._cycle(tmp_path, mode="enforcing")
        assert r.returncode == 1  # DENY-код причины
        data = json.loads(r.stdout)
        assert data["started"] is False
        assert data["reason"] == "DENY"
        assert data["mode"] == "enforcing"
        assert data["decision_status"] == "DENY"

    def test_enforcing_run_blocked_on_unknown(self, tmp_path):
        """UNKNOWN-решение (requirements.md без статуса — критерий не
        проверяем): shadow — run работает, enforcing — отказ UNKNOWN."""
        repo = make_repo(tmp_path, req="# ТЗ\n\nнет статуса тут\n")
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = tmp_path / "flow_mode.json"
        set_mode_file(mf, "shadow")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        rec = json.loads(
            state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["decision"]["status"] == "UNKNOWN"
        assert rec["status"] == "prepared"
        set_mode_file(mf, "enforcing")
        r2 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", str(reg), "--state", str(state),
                         "--json", env_mode_file=mf)
        assert r2.returncode == 2  # UNKNOWN → код 2
        d2 = json.loads(r2.stdout)
        assert d2["started"] is False
        assert d2["reason"] == "UNKNOWN"

    def test_mode_switch_live_changes_run_behavior(self, tmp_path):
        """Тот же run: enforcing отказывает, shadow (файл удален) — работает."""
        r, state = self._cycle(tmp_path, mode="enforcing")
        assert r.returncode == 1
        reg = json.loads(state.read_text(encoding="utf-8"))["runs"][
            "corr0001"]["registry"]
        # Переключение режима live: enforcing → shadow (файл удален).
        # FLOW_MODE_FILE указывает на tmp-файл ЯВНО: без этого flowctl прочитает
        # дефолт машины (~/.hermes/state/flow_mode.json), чей режим не зависит
        # от теста (изоляция теста от реального состояния машины).
        mf = set_mode_file(tmp_path / "flow_mode.json", None)
        r2 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", reg, "--state", str(state), "--json",
                         env_mode_file=mf)
        assert r2.returncode == 0
        assert json.loads(r2.stdout)["started"] is True

    def test_enforcing_run_allowed_after_allow_prepare(self, tmp_path):
        """Enforcing не блокирует валидный цикл: ALLOW-prepare → run ок."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = set_mode_file(tmp_path / "flow_mode.json", "enforcing")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        assert r.returncode == 0
        r2 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", str(reg), "--state", str(state),
                         "--json", env_mode_file=mf)
        assert r2.returncode == 0
        assert json.loads(r2.stdout)["started"] is True


# --------------------------------- flowctl prepare: enforcing требует ALLOW


class TestFlowctlPrepareEnforcement:
    def test_enforcing_deny_prepare_refused_no_side_effects(self, tmp_path):
        """Enforcing: DENY запрещает подготовку (reservation/worktree/goal
        не создаются); запись цикла с decision — источник blocks_on для run."""
        repo = make_repo_deny(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = set_mode_file(tmp_path / "flow_mode.json", "enforcing")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["prepared"] is False
        assert data["reason"] == "DENY"
        assert data["mode"] == "enforcing"
        # Никаких side effects: reservation нет, goal нет.
        assert json.loads(reg.read_text(encoding="utf-8"))["sessions"] == []
        assert not list((tmp_path / "state").glob("goal-*"))
        # Запись цикла (state) создана и содержит DENY-решение.
        rec = json.loads(
            state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["decision"]["status"] == "DENY"

    def test_shadow_deny_prepare_state_written(self, tmp_path):
        """Shadow: прежний отказ prepare (exit 1, без reservation), но
        решение сохранено в state-записи — run при включении enforcing
        сможет его заблокировать (blocks_on)."""
        repo = make_repo_deny(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = set_mode_file(tmp_path / "flow_mode.json", "shadow")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        assert r.returncode == 1  # DENY (как раньше)
        assert json.loads(
            reg.read_text(encoding="utf-8"))["sessions"] == []
        rec = json.loads(
            state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "prepared"
        assert rec["decision"]["status"] == "DENY"

    def test_enforcing_unknown_prepare_refused(self, tmp_path):
        repo = make_repo(tmp_path, req="# ТЗ\n\nнет статуса тут\n")
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        mf = set_mode_file(tmp_path / "flow_mode.json", "enforcing")
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path),
                        env_mode_file=mf)
        assert r.returncode == 2  # UNKNOWN
        data = json.loads(r.stdout)
        assert data["prepared"] is False
        assert data["reason"] == "UNKNOWN"


# ---------------------------------------------- gate_runner: enforcing gate


class TestGateRunnerEnforcement:
    def test_enforcing_fail_overall_exit_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        report, code = gr.run_gates(
            make_repo(tmp_path), "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=str(
                fake_exec(tmp_path, "fake-fail", 1, "validate failed"))))
        assert report["overall"] == "FAIL"
        assert code == 1

    def test_enforcing_skip_overall_exit_1(self, tmp_path, monkeypatch):
        """Enforcing закрывает m11: SKIPPED-отчет больше не «зеленый» exit 0."""
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(
            repo, "pre_merge", ["flow_check", "pr_validate"],
            Opts(tmp_path, pm_mode="commits", pm_commits="h1"))
        assert report["overall"] == "SKIPPED"
        assert code == 1

    def test_enforcing_error_overall_exit_2(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        report, code = gr.run_gates(
            make_repo(tmp_path), "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd="/nonexistent/openspec-nope"))
        assert report["overall"] == "ERROR"
        assert code == 2

    def test_enforcing_pass_exit_0(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        report, code = gr.run_gates(
            make_repo(tmp_path), "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=str(
                fake_exec(tmp_path, "fake-pass", 0, "Totals: 4 passed"))))
        assert report["overall"] == "PASS"
        assert code == 0

    def test_shadow_fail_overall_exit_1_unchanged(self, tmp_path, monkeypatch):
        """Shadow: прежняя семантика — FAIL остался exit 1 (не 0)."""
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "shadow")))
        report, code = gr.run_gates(
            make_repo(tmp_path), "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=str(
                fake_exec(tmp_path, "fake-fail", 1, "validate failed"))))
        assert report["overall"] == "FAIL"
        assert code == 1

    def test_status_enforcing_skip_exit_1(self, tmp_path, monkeypatch):
        """`gate_runner.py status` при enforcing на SKIPPED-отчете: exit 1."""
        monkeypatch.setenv("FLOW_MODE_FILE", str(set_mode_file(
            tmp_path / "m.json", "enforcing")))
        repo = make_repo(tmp_path)
        report, _ = gr.run_gates(
            repo, "pre_merge", ["flow_check", "pr_validate"],
            Opts(tmp_path, pm_mode="commits", pm_commits="h1"))
        assert gr.exit_code_for(report, repo) == 1


# -------------------------------- session_check: резервация строгая + mode


class TestSessionCheckReserve:
    def test_reserve_strict_in_both_modes(self, tmp_path, monkeypatch):
        """Резервация всегда строгая: конфликт зон — отказ и в shadow."""
        mf = set_mode_file(tmp_path / "m.json", "shadow")
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        base = ["reserve", "--registry", str(reg), "--repo", str(repo),
                "--role", "dev", "--project", "proj", "--owner-pm",
                "pm-main", "--policy-version",
                __import__("role_zone_policy").policy_version()]
        r1 = session_check_cmd(*base, "--delegation-id", "deleg-a",
                               "--path", "src/**", "--json",
                               env_mode_file=mf)
        assert r1.returncode == 0
        r2 = session_check_cmd(*base, "--delegation-id", "deleg-b",
                               "--path", "src/other.py", "--json",
                               env_mode_file=mf)
        assert r2.returncode == 1  # отказ и в shadow: резервация строгая
        assert json.loads(r2.stdout)["reason"] == "ZONE_CONFLICT"

    def test_reserve_output_contains_mode(self, tmp_path, monkeypatch):
        mf = set_mode_file(tmp_path / "m.json", "enforcing")
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = session_check_cmd(
            "reserve", "--registry", str(reg), "--repo", str(repo),
            "--delegation-id", "deleg-a", "--role", "dev",
            "--project", "proj", "--owner-pm", "pm-main",
            "--policy-version",
            __import__("role_zone_policy").policy_version(),
            "--path", "src/**", "--json", env_mode_file=mf)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["mode"] == "enforcing"

    def test_check_output_contains_mode(self, tmp_path, monkeypatch):
        mf = set_mode_file(tmp_path / "m.json", "enforcing")
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        session_check_cmd(
            "reserve", "--registry", str(reg), "--repo", str(repo),
            "--delegation-id", "deleg-a", "--role", "dev",
            "--project", "proj", "--owner-pm", "pm-main",
            "--policy-version",
            __import__("role_zone_policy").policy_version(),
            "--path", "src/**", "--json", env_mode_file=mf)
        r = session_check_cmd(
            "check", "--registry", str(reg), "--repo", str(repo),
            "--delegation-id", "deleg-a", "--json", env_mode_file=mf)
        assert r.returncode == 0
        assert json.loads(r.stdout)["mode"] == "enforcing"


# ------------------------------------------------------------- helpers 2


def fake_exec(tmp_path: Path, name: str, exit_code: int, out: str) -> Path:
    p = tmp_path / name
    p.write_text(f"#!/bin/sh\necho '{out}'\nexit {exit_code}\n",
                 encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class Opts:
    """Namespace-двойник для run_gates (как в test_gate_runner)."""

    def __init__(self, tmp_path: Path, **kw):
        self.openspec_cmd = kw.get("openspec_cmd", "openspec")
        self.timeout = kw.get("timeout", 10)
        self.pm_mode = kw.get("pm_mode")
        self.pm_commits = kw.get("pm_commits")
        self.pm_range = kw.get("pm_range")
        self.pm_registry = kw.get("pm_registry")
        self.pm_require_review = kw.get("pm_require_review", False)
        self.pr_id = kw.get("pr_id")
        self.log_dir = str(tmp_path / "logs")
        self.report_dir = str(tmp_path / "reports")
        self.audit = kw.get("audit", str(tmp_path / "audit.jsonl"))
        self.correlation_id = kw.get("correlation_id")
