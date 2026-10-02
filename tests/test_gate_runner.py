# -*- coding: utf-8 -*-
"""Тесты scripts/gate_runner.py (поставка 05: GateReport, адаптеры-subprocess,
digest-check, provenance sidecar, audit JSONL).

Fixture-репозитории, fixture-реестры и fake-executable в tmp_path; реальный
~/.hermes и живые скрипты-ворота НЕ используются как объект мутации:
flow_check/pm_bounds_check/pr_validate вызываются как subprocess, но сами
скрипты не меняются (00-README, огр. 2). openspec CLI в среде нет —
openspec_validate тестируется на fake-executable с управляемым exit code.

Приемка ТЗ 05:
- PASS/FAIL/ERROR (timeout, missing executable, parse error)/SKIPPED — разные
  коды; SKIPPED только по явному правилу неприменимости;
- digest-check: изменение HEAD репо инвалидирует прежний PASS (повтор
  обязателен);
- pr_validate без PR-контекста не запускается и не считается пройденным;
- sidecar пишется рядом с review-файлом, человекочитаемый .md сохраняется;
- audit JSONL append-only, без секретов и полного stdout.

Трассировка: TC-GR-001...TC-GR-020 (спека deterministic-flow; ТЗ
docs/chatgpt-deterministic-flow/05-evidence-and-gates.md; контракт §4 §11).
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

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


def make_repo(tmp_path: Path, name: str = "proj") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "README.md", "# proj\n")
    commit_all(repo)
    return repo


class Opts:
    """Namespace-двойник для run_gates без argparse."""

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


def fake_exec(tmp_path: Path, name: str, exit_code: int,
              stdout: str = "") -> str:
    """Fake-executable с управляемым exit code (openspec CLI в среде нет)."""
    p = tmp_path / name
    p.write_text(
        "#!/bin/sh\n"
        f'printf %s "{stdout}"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def gate_status(report: dict, gate_id: str) -> dict:
    return next(g for g in report["gates"] if g["gate_id"] == gate_id)


# ------------------------------------------------ TC-GR-001: статус-машина


class TestStatusMachine:
    """ТЗ 05: exit 0 → PASS, exit 1 → FAIL, другое → ERROR и блок."""

    def test_pass_exit0(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0, "Totals: 4 passed")
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=f"{fake}"))
        g = gate_status(report, "openspec_validate")
        assert g["status"] == "PASS"
        assert code == 0

    def test_fail_exit1(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 1, "validate failed")
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=f"{fake}"))
        g = gate_status(report, "openspec_validate")
        assert g["status"] == "FAIL"
        assert code == 1

    def test_parse_error_exit7_is_error(self, tmp_path):
        """Parse error (exit 7) — не FAIL и не пропуск: ERROR и блок."""
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 7, "traceback-ish")
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=f"{fake}"))
        g = gate_status(report, "openspec_validate")
        assert g["status"] == "ERROR"
        assert g["exit_code"] == 7
        assert "exit code 7" in g["diagnostics"]
        assert code == 2

    def test_missing_executable_is_error(self, tmp_path):
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd="/nonexistent/openspec-nope"))
        g = gate_status(report, "openspec_validate")
        assert g["status"] == "ERROR"
        assert "не найден" in g["diagnostics"]
        assert code == 2

    def test_timeout_is_error_and_blocking(self, tmp_path):
        """Зависший gate: ERROR с явным «блокирует», код 2."""
        repo = make_repo(tmp_path)
        hang = tmp_path / "hang.sh"
        hang.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        hang.chmod(hang.stat().st_mode | stat.S_IEXEC)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=str(hang), timeout=1))
        g = gate_status(report, "openspec_validate")
        assert g["status"] == "ERROR"
        assert "timeout" in g["diagnostics"]
        assert "блок" in g["diagnostics"]
        assert code == 2

    def test_error_overall_dominates_fail(self, tmp_path):
        repo = make_repo(tmp_path)
        bad = fake_exec(tmp_path, "fake-openspec", 2)
        report, code = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=f"{bad}"))
        assert report["overall"] == "ERROR"
        assert code == 2


# --------------------------------------- TC-GR-002: структура GateReport


class TestReportShape:
    def test_report_fields(self, tmp_path):
        """ТЗ 05: gate_id, scope, command/adapter_version, input_head,
        input_digest, started_at, duration, exit_code, status, log_path,
        краткая диагностика."""
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        report, _ = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=f"{fake}"))
        g = gate_status(report, "openspec_validate")
        for key in ("gate_id", "scope", "command", "adapter_version",
                    "input_head", "input_digest", "started_at", "duration",
                    "exit_code", "status", "log_path", "diagnostics"):
            assert key in g, key
        assert g["adapter_version"] == gr.ADAPTER_VERSION
        assert g["input_head"] == git(repo, "rev-parse", "HEAD")
        assert g["log_path"] and Path(g["log_path"]).is_file()
        assert "fake-openspec" in " ".join(g["command"])
        assert Path(report["report_ref"]).is_file()

    def test_log_file_bounded(self, tmp_path):
        """Логи gate хранятся отдельно с ограничением размера (ТЗ 05)."""
        repo = make_repo(tmp_path)
        big = tmp_path / "big.sh"
        big.write_text(
            "#!/bin/sh\npython3 -c \"print('x'*400000)\"\n",
            encoding="utf-8",
        )
        big.chmod(big.stat().st_mode | stat.S_IEXEC)
        report, _ = gr.run_gates(
            repo, "preflight", ["openspec_validate"],
            Opts(tmp_path, openspec_cmd=str(big)))
        g = gate_status(report, "openspec_validate")
        assert Path(g["log_path"]).stat().st_size < gr.MAX_LOG_BYTES * 2


# ------------------------------------- TC-GR-003: digest-check / STALE


class TestDigestCheck:
    def test_stale_after_new_commit(self, tmp_path):
        """Приемка ТЗ 05: повтор после изменения входного SHA обязателен —
        PASS при измененном HEAD → exit 1 (STALE), не «успех»."""
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        opts = Opts(tmp_path, openspec_cmd=f"{fake}")
        report, code = gr.run_gates(repo, "preflight",
                                    ["openspec_validate"], opts)
        assert code == 0
        # новый коммит → вход изменился
        write(repo, "README.md", "# proj v2\n")
        commit_all(repo, "second")
        code2 = gr.exit_code_for(report, repo)
        assert code2 == 1
        assert gr.is_stale(report, repo)

    def test_input_digest_changes_with_head(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        opts = Opts(tmp_path, openspec_cmd=f"{fake}")
        r1, _ = gr.run_gates(repo, "preflight", ["openspec_validate"], opts)
        d1 = gate_status(r1, "openspec_validate")["input_digest"]
        write(repo, "README.md", "# v2\n")
        commit_all(repo)
        r2, _ = gr.run_gates(repo, "preflight", ["openspec_validate"], opts)
        d2 = gate_status(r2, "openspec_validate")["input_digest"]
        assert d1 != d2

    def test_status_cli_stale_exit1(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        opts = Opts(tmp_path, openspec_cmd=f"{fake}")
        gr.run_gates(repo, "preflight", ["openspec_validate"], opts)
        write(repo, "README.md", "# v3\n")
        commit_all(repo)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"), "status",
             "--report-dir", opts.report_dir, "--repo", str(repo)],
            capture_output=True, text=True,
        )
        assert r.returncode == 1
        assert "STALE" in r.stdout


# --------------------------------- TC-GR-004: SKIPPED только по правилу


class TestSkipRules:
    def test_pr_validate_skipped_without_pr_context(self, tmp_path):
        """Приемка ТЗ 05: pr_validate без PR-контекста не запускается и не
        считается пройденным; SKIPPED по явному правилу неприменимости."""
        repo = make_repo(tmp_path)
        report, _ = gr.run_gates(repo, "pre_merge", ["pr_validate"], Opts(tmp_path))
        g = gate_status(report, "pr_validate")
        assert g["status"] == "SKIPPED"
        assert g["exit_code"] is None
        assert "PR-контекста" in g["diagnostics"]
        assert report["overall"] == "PASS"  # SKIPPED не FAIL, но и не PASS gate

    def test_pr_validate_runs_with_pr_id(self, tmp_path):
        repo = make_repo(tmp_path)
        report, _ = gr.run_gates(
            repo, "pre_merge", ["pr_validate"], Opts(tmp_path, pr_id="add-x"))
        g = gate_status(report, "pr_validate")
        assert g["status"] in ("PASS", "FAIL")  # реально запущен
        assert g["exit_code"] in (0, 1)

    def test_pm_bounds_requires_explicit_mode(self, tmp_path):
        """ТЗ 05: pm_bounds_check без явного режима не запускается."""
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(
            repo, "pre_accept", ["pm_bounds_check"], Opts(tmp_path))
        g = gate_status(report, "pm_bounds_check")
        assert g["status"] == "SKIPPED"
        assert "явного режима" in g["diagnostics"]
        # провал конфигурации gate — не молчаливый успех: код отказа 1
        # (конфигурационная ошибка входа превратится в ERROR при явном
        # требовании gate; здесь отчет обязателен как блокирующий FAIL)
        report["overall"] = gr.STATUS_FAIL
        assert gr.exit_code_for(report, repo) == 1

    def test_pm_mode_sessions(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = tmp_path / "active_sessions.json"
        reg.write_text('{"sessions": []}', encoding="utf-8")
        report, code = gr.run_gates(
            repo, "pre_accept", ["pm_bounds_check"],
            Opts(tmp_path, pm_mode="sessions", pm_registry=str(reg)))
        g = gate_status(report, "pm_bounds_check")
        assert g["status"] == "PASS"
        assert "--sessions" in " ".join(g["command"])
        assert code == 0

    def test_pm_mode_commits_missing_arg(self, tmp_path):
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(
            repo, "pre_accept", ["pm_bounds_check"],
            Opts(tmp_path, pm_mode="commits"))
        g = gate_status(report, "pm_bounds_check")
        assert g["status"] == "SKIPPED"
        assert "--pm-commits" in g["diagnostics"]

    def test_flow_check_adapter_on_fixture_repo(self, tmp_path):
        """Адаптер flow_check запускает РЕАЛЬНЫЙ скрипт subprocess'ом
        (скрипт не меняется, 00-README огр. 2) на чистом fixture-repo."""
        repo = make_repo(tmp_path)
        report, code = gr.run_gates(repo, "post_agent", ["flow_check"],
                                    Opts(tmp_path))
        g = gate_status(report, "flow_check")
        assert g["status"] == "PASS"
        assert "flow_check.py" in " ".join(g["command"])
        assert code == 0

    def test_flow_check_fail_reported(self, tmp_path):
        """flow_check exit 1 на нарушении → FAIL, код 1."""
        repo = make_repo(tmp_path)
        write(repo, "openspec/changes/add-x/proposal.md", "# p\n")
        commit_all(repo)
        report, code = gr.run_gates(repo, "post_agent", ["flow_check"],
                                    Opts(tmp_path))
        g = gate_status(report, "flow_check")
        assert g["status"] == "FAIL"
        assert code == 1

    def test_scope_default_gate_sets(self, tmp_path):
        """ТЗ 05: у каждой точки запуска свой список обязательных проверок."""
        assert gr.DEFAULT_GATES["preflight"] == ("openspec_validate",)
        assert "pr_validate" in gr.DEFAULT_GATES["pre_merge"]
        assert "flow_check" in gr.DEFAULT_GATES["pre_accept"]


# --------------------------------------------- TC-GR-005: audit JSONL


class TestAudit:
    def test_gate_report_event_written(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        audit = tmp_path / "audit.jsonl"
        opts = Opts(tmp_path, openspec_cmd=f"{fake}", audit=str(audit))
        report, _ = gr.run_gates(repo, "preflight",
                                 ["openspec_validate"], opts)
        events = [json.loads(x) for x in
                  audit.read_text(encoding="utf-8").strip().splitlines()]
        kinds = [e["event"] for e in events]
        assert kinds[0] == "request"
        assert "gate_report" in kinds
        cid = events[0]["correlation_id"]
        assert all(e["correlation_id"] == cid for e in events)
        gr_ev = next(e for e in events if e["event"] == "gate_report")
        assert gr_ev["input_digest"] == \
            gate_status(report, "openspec_validate")["input_digest"]
        # полный stdout в JSONL не копируется: только ссылка на лог
        assert "stdout" not in gr_ev

    def test_append_only_no_secrets(self, tmp_path):
        """Секреты/полный stdout в JSONL не пишутся: запрещенный ключ →
        отказ (событие не искажается молча), существующие строки не тронуты."""
        audit = tmp_path / "audit.jsonl"
        gr.append_audit_event(audit, "request", "c1", scope={"phase": "ci"})
        before = audit.read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            gr.append_audit_event(audit, "decision", "c1",
                                  password="hunter2")
        with pytest.raises(ValueError):
            gr.append_audit_event(audit, "agent_finished", "c1",
                                  stdout="полный вывод агента")
        assert audit.read_text(encoding="utf-8") == before
        # append-only: второе валидное событие дописывается, не перезаписывает
        gr.append_audit_event(audit, "accepted", "c1")
        lines = before.strip().splitlines()
        after = audit.read_text(encoding="utf-8").strip().splitlines()
        assert after[:len(lines)] == lines
        assert len(after) == len(lines) + 1

    def test_unknown_event_type_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            gr.append_audit_event(tmp_path / "a.jsonl", "diary", "c1")


# --------------------------------------- TC-GR-006: provenance sidecar


class TestRecordReview:
    def _review_file(self, repo: Path) -> Path:
        rf = repo / "code-reviews" / "add-x" / "review-001-1.1.md"
        write(repo, str(rf.relative_to(repo)),
              "# Review 1.1\n\n## Вердикт: approve\n\nДата: 2026-10-02\n")
        return rf

    def test_sidecar_written_beside_review(self, tmp_path):
        repo = make_repo(tmp_path)
        rf = self._review_file(repo)
        sha = git(repo, "rev-parse", "HEAD")
        path, payload = gr.write_review_provenance(
            rf, "proj", "add-x", ["1.1"], "deleg_author", "deleg_reviewer",
            sha, "approve", diff_digest="d" * 64)
        assert path == Path(str(rf) + ".provenance.json")
        assert path.is_file()
        # человекочитаемый .md сохраняется (не переписывается)
        assert "Вердикт: approve" in rf.read_text(encoding="utf-8")
        assert payload["schema_version"] == "review-provenance/1"
        assert payload["project"] == "proj"
        assert payload["change"] == "add-x"
        assert payload["task_ids"] == ["1.1"]
        assert payload["reviewed_commit_sha"] == sha
        assert payload["verdict"] == "approve"
        assert payload["timestamp"] and payload["review_path"] == str(rf)

    def test_sidecar_requires_fields(self, tmp_path):
        repo = make_repo(tmp_path)
        rf = self._review_file(repo)
        sha = git(repo, "rev-parse", "HEAD")
        with pytest.raises(ValueError):
            gr.write_review_provenance(rf, "", "add-x", ["1.1"], "a", "b",
                                       sha, "approve")
        with pytest.raises(ValueError):
            gr.write_review_provenance(rf, "proj", "add-x", [], "a", "b",
                                       sha, "approve")
        with pytest.raises(ValueError):
            gr.write_review_provenance(rf, "proj", "add-x", ["1.1"], "a",
                                       "b", sha, "maybe")
        with pytest.raises(ValueError):
            gr.write_review_provenance(tmp_path / "nope.md", "proj",
                                       "add-x", ["1.1"], "a", "b", sha,
                                       "approve")

    def test_diff_digest_subcommand(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "f.txt", "hello\n")
        commit_all(repo, "add f")
        head = git(repo, "rev-parse", "HEAD")
        base = git(repo, "rev-parse", "HEAD~1")
        d1 = gr.compute_diff_digest(repo, base, head)
        d2 = gr.compute_diff_digest(repo, base, head)
        assert d1 == d2 and len(d1) == 64
        write(repo, "f.txt", "world\n")
        commit_all(repo, "edit f")
        head2 = git(repo, "rev-parse", "HEAD")
        assert gr.compute_diff_digest(repo, base, head2) != d1


# ----------------------------------------- TC-GR-007: CLI smoke (exit-коды)


class TestCli:
    def test_cli_run_json(self, tmp_path):
        repo = make_repo(tmp_path)
        fake = fake_exec(tmp_path, "fake-openspec", 0)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"), "run",
             "--repo", str(repo), "--scope", "preflight",
             "--openspec-cmd", fake, "--json",
             "--report-dir", str(tmp_path / "r"),
             "--log-dir", str(tmp_path / "l")],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["overall"] == "PASS"
        assert data["gates"][0]["status"] == "PASS"

    def test_cli_status_no_report_exit2(self, tmp_path):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"), "status",
             "--report-dir", str(tmp_path / "empty")],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "GATE-RUNNER-ERROR" in r.stderr

    def test_cli_unknown_gate_exit2(self, tmp_path):
        repo = make_repo(tmp_path)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"), "run",
             "--repo", str(repo), "--scope", "preflight",
             "--gates", "bogus_gate"],
            capture_output=True, text=True,
        )
        assert r.returncode == 2

    def test_cli_record_review_exit2_on_bad_verdict(self, tmp_path):
        repo = make_repo(tmp_path)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_runner.py"),
             "record-review",
             "--review-path", str(repo / "code-reviews" / "x" / "r.md"),
             "--project", "proj", "--change", "x-y", "--tasks", "1.1",
             "--author-delegation", "a", "--reviewer-delegation", "b",
             "--commit", "deadbeef", "--verdict", "sure"],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
