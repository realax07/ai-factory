# -*- coding: utf-8 -*-
"""Тесты scripts/flowctl.py (поставка 06: локальный оркестратор, adapter=manual).

Fixture-репозитории, fixture-реестры и fixture-state в tmp_path; реальный
~/.hermes/state/ и пользовательские проекты НЕ используются. openspec CLI в
среде нет — fake-executable с управляемым exit code (как в test_gate_runner).

Приемка ТЗ 06:
- prepare --dry-run показывает роль/входы/worktree/gates/human gate без
  side effects (нет записи в реестре/state, нет worktree/goal);
- run разрешен только после явного решения (ALLOW) и реальной reservation;
- идемпотентность: повтор run с тем же correlation ID не создает вторую
  сессию и не повторяет делегацию; повтор prepare с тем же payload — OK;
- timeout/crash не продвигают на следующий шаг: finish на prepared/
  needs_attention → blocked; worktree не удаляется;
- после завершения вердикт по фактам: diff/зона/gates → accepted/returned/
  blocked (отчет агента — указатель, не доказательство);
- НИКАКОГО авто-push/merge/deploy и авто-старта фаз; adapter=manual:
  подготовленный goal НЕ выдается за факт запуска;
- STALE_SNAPSHOT при несовпадении digest между prepare и run.

Трассировка: TC-FC-001... (спека deterministic-flow; ТЗ
docs/chatgpt-deterministic-flow/06-local-orchestrator.md; контракт §4–§13).
"""
from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402
import flowctl  # noqa: E402


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


def make_repo(tmp_path: Path, *, change_id: str = "add-widget",
              req: str | None = REQ_APPROVED, tasks: str | None = TASKS,
              with_review: bool = True, with_sdd: bool = True,
              with_deltas: bool = True) -> Path:
    """Fixture-репозиторий Флоу 1, готовый к dev_task (как в test_flow_transition)."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    if req:
        write(repo, "requirements.md", req)
    write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
    write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
    if tasks:
        write(repo, f"openspec/changes/{change_id}/tasks.md", tasks)
    if with_deltas:
        write(repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
              "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    if with_review:
        write(repo, f"code-reviews/{change_id}/review-001-1.1.md",
              "## Вердикт: approve\n")
    if with_sdd:
        write(repo, "sdd.md", "# SDD\n")
    write(repo, "src/widget.py", "X = 1\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def flowctl_cmd(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
        capture_output=True, text=True,
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
        "--audit", str(tmp_path / "audit.jsonl"),
        "--correlation-id", kw.get("cid", "corr0001"),
        "--json",
    ]
    if kw.get("dry_run"):
        argv.append("--dry-run")
    return argv


def registry_sessions(reg: Path) -> list[dict]:
    return json.loads(reg.read_text(encoding="utf-8")).get("sessions", [])


def fake_openspec(tmp_path: Path, exit_code: int = 0) -> str:
    p = tmp_path / f"fake-openspec-{exit_code}"
    p.write_text("#!/bin/sh\nexit " + str(exit_code) + "\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


# ------------------------------------------ TC-FC-001: прокси inspect/check/next


class TestProxyCommands:
    def test_inspect_proxy_json(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = flowctl_cmd("inspect", "--repo", str(repo), "--project", "proj",
                        "--flow", "1", "--change", "add-widget",
                        "--registry", str(reg), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["schema_version"] == "flow-snapshot/1"
        assert data["scope"]["change"] == "add-widget"

    def test_check_proxy_allow_and_deny_exit(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = flowctl_cmd("check", "--repo", str(repo), "--project", "proj",
                        "--flow", "1", "--change", "add-widget",
                        "--task", "1.1", "--action", "dev_task",
                        "--role", "dev", "--registry", str(reg), "--json")
        assert r.returncode == 0  # ALLOW
        # Чужая роль → DENY, exit 1 (exit codes поставки 03 сохранены)
        r2 = flowctl_cmd("check", "--repo", str(repo), "--project", "proj",
                         "--flow", "1", "--change", "add-widget",
                         "--task", "1.1", "--action", "dev_task",
                         "--role", "pm", "--registry", str(reg))
        assert r2.returncode == 1
        assert "WRONG_ROLE" in r2.stdout

    def test_next_proxy(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = flowctl_cmd("next", "--repo", str(repo), "--project", "proj",
                        "--flow", "1", "--change", "add-widget",
                        "--registry", str(reg), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert any(c["action"] == "dev_task" for c in data["candidates"])


# ------------------------------------------------ TC-FC-002: prepare --dry-run


class TestPrepareDryRun:
    def test_dry_run_no_side_effects(self, tmp_path):
        """Приемка ТЗ 06: dry-run показывает роль/входы/worktree/gates/human
        gate, но ничего не пишет: реестр пуст, state нет, goal нет."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path,
                                      dry_run=True))
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["dry_run"] is True
        assert data["prepared"] is True
        assert data["role"] == "dev"
        assert data["action"] == "dev_task"
        assert data["zones"] == ["src/**"]
        assert data["gates"]  # план gates из decision
        assert data["decision"]["status"] == "ALLOW"
        assert "dry-run" in data["note"]
        # Side effects отсутствуют:
        assert registry_sessions(reg) == []
        assert not state.exists()
        assert not list((tmp_path / "state").glob("goal-*"))

    def test_dry_run_denied_action_shows_reasons(self, tmp_path):
        repo = make_repo(tmp_path, req="# ТЗ\n\n> Статус: ЧЕРНОВИК\n")
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path,
                                      dry_run=True))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["decision"]["status"] == "DENY"
        assert data["decision"]["blocking_reasons"]
        assert registry_sessions(reg) == []


# ------------------------------------------------------ TC-FC-003: prepare→run


class TestPrepareRun:
    def test_prepare_then_run_manual_adapter(self, tmp_path):
        """prepare готовит session/worktree/goal; run отмечает старт; goal —
        НЕ факт запуска (adapter=manual, ТЗ 06)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["prepared"] is True
        assert data["adapter"] == "manual"
        rec = data["record"]
        assert rec["status"] == "prepared"
        assert "ЗАПУСКА НЕТ" in data["note"]
        # Reservation реальна (в реестре):
        sessions = registry_sessions(reg)
        assert len(sessions) == 1
        assert sessions[0]["delegation_id"] == rec["delegation_id"]
        assert sessions[0]["status"] == "reserved"
        # Резервация фиксирует снимок момента резервации; prepared_digest —
        # переснимок ПОСЛЕ reservation (реестр изменился) — он для run:
        assert sessions[0]["snapshot_digest"]
        # Goal записан и не пуст:
        goal = Path(rec["goal_path"])
        assert goal.is_file()
        assert "dev_task" in goal.read_text(encoding="utf-8")

    def test_run_only_after_prepare(self, tmp_path):
        """run без prepare: отказ, никакой сессии (ТЗ 06: run только после
        явного решения и реальной reservation)."""
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd("run", "--correlation-id", "noprep",
                        "--registry", str(reg), "--state", str(state),
                        "--json")
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["started"] is False
        assert registry_sessions(reg) == []

    def test_run_idempotent_no_second_session(self, tmp_path):
        """Приемка ТЗ 06: повтор run с тем же correlation ID не создает
        вторую сессию и не повторяет вызов."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        r1 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", str(reg), "--state", str(state),
                         "--json")
        assert r1.returncode == 0
        assert json.loads(r1.stdout)["started"] is True
        n_sessions = len(registry_sessions(reg))
        # Повтор run:
        r2 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", str(reg), "--state", str(state),
                         "--json")
        assert r2.returncode == 0
        data2 = json.loads(r2.stdout)
        assert data2["started"] is False
        assert data2["idempotent"] is True
        assert len(registry_sessions(reg)) == n_sessions  # не выросло
        # Состояние реестра — по-прежнему ровно одна running:
        assert sum(
            1 for s in registry_sessions(reg) if s["status"] == "running") == 1

    def test_run_stale_snapshot_after_new_commit(self, tmp_path):
        """Приемка ТЗ 06: снимок переснимается перед стартом; несовпадение
        digest → STALE_SNAPSHOT, статус не меняется."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        write(repo, "src/widget.py", "X = 2\n")
        commit_all(repo, "unrelated change")
        r = flowctl_cmd("run", "--correlation-id", "corr0001",
                        "--registry", str(reg), "--state", str(state),
                        "--json")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["started"] is False
        assert data["reason"] == "STALE_SNAPSHOT"
        sessions = registry_sessions(reg)
        assert sessions[0]["status"] == "reserved"  # не продвинут
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "prepared"  # статус не менялся

    def test_prepare_idempotent_same_payload(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        r2 = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        assert r2.returncode == 0
        data = json.loads(r2.stdout)
        assert data["idempotent"] is True
        assert len(registry_sessions(reg)) == 1

    def test_prepare_duplicate_payload_rejected(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        # Тот же correlation ID, другой payload (другая зона; action/role те
        # же, чтобы отказ пришел от идемпотентности, а не от wrong-role):
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv[argv.index("--path") + 1] = "docs/**"
        r = flowctl_cmd(*argv)
        assert r.returncode == 1
        assert "DUPLICATE_PAYLOAD" in r.stdout

    def test_prepare_zone_conflict_denied(self, tmp_path):
        """Пересечение зон двух активных сессий — вторая reservation отклонена."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path, cid="corrA"))
        r = flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path, cid="corrB"))
        assert r.returncode == 1
        assert "ZONE_CONFLICT" in r.stdout

    def test_prepare_human_gate_blocked(self, tmp_path):
        """Запрет из-за human gate (приемка ТЗ 06): create_change без решения
        Заказчика → HUMAN_APPROVAL_REQUIRED, сессия не создается."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = [
            "prepare", "--repo", str(repo), "--project", "proj", "--flow", "1",
            "--change", "add-widget", "--action", "create_change",
            "--role", "sa", "--registry", str(reg), "--state", str(state),
            "--json", "--correlation-id", "corrHG",
        ]
        r = flowctl_cmd(*argv)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        # prepare при запрете пишет запись цикла: decision внутри record
        assert "HUMAN_APPROVAL_REQUIRED" in \
            data["record"]["decision"]["blocking_reasons"]
        assert registry_sessions(reg) == []


# ------------------------------------------------- TC-FC-004: finish-вердикты


class TestFinish:
    def _prepare_and_run(self, tmp_path, repo, reg, state,
                         openspec_cmd=None):
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        flowctl_cmd("run", "--correlation-id", "corr0001",
                    "--registry", str(reg), "--state", str(state))
        # «Работа агента»: изменение в своей зоне + коммит (report = указатель).
        write(repo, "src/widget.py", "X = 42\n")
        sha = commit_all(repo, "dev: widget")
        report = tmp_path / "agent-report.md"
        report.write_text(f"# Отчет\nизменено: src/widget.py ({sha})\n",
                          encoding="utf-8")
        return report

    def _finish_argv(self, tmp_path, reg, state, report,
                     openspec_cmd=None):
        argv = [
            "finish", "--correlation-id", "corr0001",
            "--report", str(report),
            "--gate-scope", "preflight",
            "--gates", "flow_check",
            "--registry", str(reg), "--state", str(state),
            "--audit", str(tmp_path / "audit.jsonl"),
            "--log-dir", str(tmp_path / "logs"),
            "--report-dir", str(tmp_path / "greports"),
            "--json",
        ]
        if openspec_cmd:
            argv += ["--openspec-cmd", openspec_cmd]
        return argv

    def test_finish_accepted_in_zone_gates_pass(self, tmp_path):
        """Полный цикл dev task: diff в зоне, gates PASS → accepted; никакого
        merge/push (запись не уходит из ветки, вердикт — локальный)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = self._prepare_and_run(tmp_path, repo, reg, state)
        r = flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "accepted"
        assert data["defects"] == []
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "accepted"
        # Реестр: finished; worktree/repo не тронуты автоматически:
        sessions = registry_sessions(reg)
        assert sessions[0]["status"] == "finished"
        # flow_check остался независимым gate: его отчет лежит на диске
        assert (tmp_path / "greports").is_dir()

    def test_finish_returned_on_out_of_zone(self, tmp_path):
        """Изменение вне зоны → returned со структурированным списком дефектов."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        flowctl_cmd("run", "--correlation-id", "corr0001",
                    "--registry", str(reg), "--state", str(state))
        write(repo, "docs/outside-zone.md", "чужой файл\n")
        commit_all(repo, "out of zone")
        report = tmp_path / "agent-report.md"
        report.write_text("# Отчет\nтрогал docs/outside-zone.md\n",
                          encoding="utf-8")
        r = flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "returned"
        assert any(d["source"] == "zone" and d["code"] == "OUT_OF_ZONE"
                   for d in data["defects"])

    def test_finish_returned_on_gate_fail(self, tmp_path):
        """Приемка ТЗ 06: gate failure → не accepted."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = self._prepare_and_run(tmp_path, repo, reg, state)
        # Ломаем инвариант flow_check: change-пакет без tasks.md
        (repo / "openspec/changes/add-widget/tasks.md").unlink()
        commit_all(repo, "break contract 2")
        r = flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "returned"
        assert any(d["source"] == "gate" for d in data["defects"])

    def test_finish_blocked_on_gate_error(self, tmp_path):
        """Gate ERROR (нет исполняемого) → blocked (приемка ТЗ 06: gate
        failure/missing блокирует, не продвигает)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = self._prepare_and_run(tmp_path, repo, reg, state)
        argv = self._finish_argv(tmp_path, reg, state, report)
        argv[argv.index("--gates") + 1] = "openspec_validate"
        argv += ["--openspec-cmd", "/nonexistent/openspec-nope"]
        r = flowctl_cmd(*argv)
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["verdict"] == "blocked"
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "blocked"

    def test_finish_requires_report(self, tmp_path):
        """После завершения отчет обязателен (ТЗ 06)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        flowctl_cmd("run", "--correlation-id", "corr0001",
                    "--registry", str(reg), "--state", str(state))
        r = flowctl_cmd("finish", "--correlation-id", "corr0001",
                        "--report", str(tmp_path / "missing.md"),
                        "--gates", "flow_check",
                        "--registry", str(reg), "--state", str(state),
                        "--json")
        assert r.returncode == 2
        assert json.loads(r.stdout)["verdict"] == "blocked"

    def test_finish_blocked_before_run_no_promotion(self, tmp_path):
        """Timeout/crash до run: finish на prepared → blocked, шаг НЕ
        продвигается, reservation жива (приемка ТЗ 06: падение агента)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        report = tmp_path / "agent-report.md"
        report.write_text("# Отчет\n", encoding="utf-8")
        r = flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["verdict"] == "blocked"
        assert registry_sessions(reg)[0]["status"] == "reserved"

    def test_finish_idempotent_after_verdict(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        report = self._prepare_and_run(tmp_path, repo, reg, state)
        flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        r2 = flowctl_cmd(*self._finish_argv(tmp_path, reg, state, report))
        assert r2.returncode == 0
        data = json.loads(r2.stdout)
        assert data["verdict"] == "accepted"
        assert data["idempotent"] is True


# ------------------------------------------ TC-FC-005: crash/timeout recovery


class TestRecovery:
    def test_crash_after_reservation_reconcile_no_redelegation(
            self, tmp_path):
        """Приемка ТЗ 06: restart процесса без повторной делегации. Runner
        «умер» после reservation (prepared) и после записи файлов: reconcile
        помечает needs_attention/stale, ничего не удаляет, повторная делегация
        не стартует (run на needs_attention — отказ)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        # «Падение» после записи файлов агентом:
        write(repo, "src/widget.py", "X = crash\n")
        r = flowctl_cmd("reconcile", "--repo", str(repo),
                        "--registry", str(reg), "--state", str(state),
                        "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["results"], "reservation должна попасть в сверку"
        assert data["touched_runs"] == ["corr0001"]
        rec = json.loads(state.read_text(encoding="utf-8"))["runs"]["corr0001"]
        assert rec["status"] == "needs_attention"
        # Файлы агента сохранены; worktree не удален:
        assert "X = crash" in (repo / "src/widget.py").read_text(encoding="utf-8")
        # Повторный run НЕ повторяет делегацию:
        r2 = flowctl_cmd("run", "--correlation-id", "corr0001",
                         "--registry", str(reg), "--state", str(state),
                         "--json")
        assert r2.returncode == 1
        assert json.loads(r2.stdout)["started"] is False

    def test_reconcile_stale_marks_registry(self, tmp_path):
        """Мертвый PID + чистое дерево → stale, запись сохраняется (не «сессий
        нет»), решение ПМ обязательно."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        sessions = registry_sessions(reg)
        sessions[0]["pid"] = 999999  # мертвый pid
        payload = json.loads(reg.read_text(encoding="utf-8"))
        payload["sessions"] = sessions
        reg.write_text(json.dumps(payload), encoding="utf-8")
        r = flowctl_cmd("reconcile", "--registry", str(reg),
                        "--state", str(state), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["results"][0]["status_after"] == "stale"
        assert registry_sessions(reg), "запись сохраняется, не удаляется"

    def test_worktree_survives_crash(self, tmp_path):
        """Timeout/crash: worktree не удаляется (ТЗ 06)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv += ["--create-worktree"]
        r = flowctl_cmd(*argv)
        assert r.returncode == 0, r.stdout + r.stderr
        rec = json.loads(r.stdout)["record"]
        wt = Path(rec["worktree"])
        assert wt.is_dir()
        assert (wt / "SESSION.md").is_file()
        # crash: reconcile
        flowctl_cmd("reconcile", "--registry", str(reg),
                    "--state", str(state), "--json")
        assert wt.is_dir(), "worktree переживает сбой"
        assert (wt / "SESSION.md").is_file()


# --------------------------------------------------- TC-FC-006: status/audit


class TestStatusAudit:
    def test_status_shows_runs_and_sessions(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        r = flowctl_cmd("status", "--registry", str(reg),
                        "--state", str(state), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data["runs"]) == 1
        assert data["runs"][0]["status"] == "prepared"
        assert len(data["sessions"]) == 1

    def test_status_unknown_correlation_exit1(self, tmp_path):
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd("status", "--correlation-id", "nope",
                        "--registry", str(reg), "--state", str(state))
        assert r.returncode == 1

    def test_audit_events_no_secrets(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        audit = tmp_path / "audit.jsonl"
        flowctl_cmd(*prepare_argv(repo, reg, state, tmp_path))
        flowctl_cmd("run", "--correlation-id", "corr0001",
                    "--registry", str(reg), "--state", str(state),
                    "--audit", str(audit))
        events = [json.loads(x) for x in
                  audit.read_text(encoding="utf-8").strip().splitlines()]
        kinds = [e["event"] for e in events]
        assert kinds[0] == "reservation"
        assert "agent_started" in kinds
        assert all(e["correlation_id"] == "corr0001" for e in events)
        # без секретов: нет запрещенных ключей (gate_runner фильтрует)
        for e in events:
            assert "stdout" not in e and "password" not in e

    def test_json_output_schema_stable(self, tmp_path):
        """Выход --json стабилен: schema_version обязателен (ТЗ 06)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        for argv in (
            prepare_argv(repo, reg, state, tmp_path, dry_run=True),
            prepare_argv(repo, reg, state, tmp_path),
            ["run", "--correlation-id", "corr0001", "--registry", str(reg),
             "--state", str(state), "--json"],
            ["status", "--registry", str(reg), "--state", str(state),
             "--json"],
        ):
            r = flowctl_cmd(*argv)
            data = json.loads(r.stdout)
            assert data["schema_version"] == "flowctl-output/1"


# ------------------------------------- TC-FC-007: unit-функции (без subprocess)


class TestUnits:
    def test_goal_text_manual_disclaimer(self, tmp_path):
        """Подготовленный goal НЕ выдается за факт запуска (ТЗ 06)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        record = {
            "correlation_id": "c1", "delegation_id": "deleg-c1",
            "actor_role": "dev", "action": "dev_task", "task_id": "1.1",
            "scope": {"repo": str(repo), "project": "proj", "flow": 1,
                      "change": "add-widget", "task": "1.1"},
            "zones": ["src/**"], "worktree": None, "branch": None,
            "goal_path": "g.md", "prepared_digest": "d" * 64,
            "approval_ref": None,
        }
        snapshot = flow_state.inspect(str(repo), "proj", 1, "add-widget",
                                      "1.1", str(reg))
        decision = flowctl.ft.check_action(
            snapshot, flowctl.ft.ActionRequest(
                actor_role="dev", requested_action="dev_task", task_id="1.1"))
        text = flowctl.build_goal_text(record, decision, reg)
        assert "adapter=manual" in text
        assert "не является фактом" in text or "НЕ" in text
        assert "push НЕТ" in text
        assert "эскалация" in text

    def test_state_corrupt_is_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            flowctl.state_load(bad)
        worse = tmp_path / "worse.json"
        worse.write_text('{"no_runs": 1}', encoding="utf-8")
        with pytest.raises(ValueError):
            flowctl.state_load(worse)

    def test_default_state_path_next_to_registry(self, tmp_path):
        reg = tmp_path / "x" / "active_sessions.json"
        p = flowctl.default_state_path(str(reg))
        assert p == reg.parent / "flowctl_state.json"
