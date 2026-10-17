# -*- coding: utf-8 -*-
"""J51.3 + J51.4: ворота merge «regress-final» и роль regress_runner.

J51.3 (pr_validate.check_regress_final, вызывается из check_change):
  - для change-пакетов обязателен артефакт
    test-model/regress/<change-id>/regress-final.md с verdict PASS,
    commit == HEAD ветки PR (или предок HEAD не старше измененных файлов)
    и свежестью ≤ 7 дней;
  - нет артефакта / не-PASS → REGRESS_FINAL_MISSING; протух по времени или
    commit не совпадает → REGRESS_FINAL_STALE;
  - нумерованные regress-<N>.md финальными НЕ считаются;
  - [chore]/[docs]/[ops] ворота не касаются (gate живет в check_change).

J51.4 (роль regress_runner):
  - промпт agents/regress_runner_agent.md существует (шапка-версия +
    yaml-комментарий) и зарегистрирован в agents/README.md.

Трассировка:
  TC-J51-021  ворота: артефакта нет → REGRESS_FINAL_MISSING (в check_change)
  TC-J51-022  ворота: только regress-1.md — финальным не считается → MISSING
  TC-J51-023  ворота: verdict FAIL → REGRESS_FINAL_MISSING
  TC-J51-024  ворота: артефакт старше 7 дней → REGRESS_FINAL_STALE
  TC-J51-025  ворота: commit не совпадает и не предок → REGRESS_FINAL_STALE
  TC-J51-026  ворота: предок HEAD старше касания измененного файла → STALE
  TC-J51-027  ворота: предок HEAD не старше измененных файлов → PASS
  TC-J51-028  e2e: flowctl regress --final → ворота пропускают
  TC-J51-029  regress_runner-промпт существует, шапка-версия + yaml-комментарий
  TC-J51-030  regress_runner зарегистрирован в agents/README.md
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import pr_validate  # noqa: E402

CHANGE = "add-widget"


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str, env_dates: tuple[str, str] | None = None) -> str:
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if env_dates:
        env["GIT_AUTHOR_DATE"], env["GIT_COMMITTER_DATE"] = env_dates
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True, env=env)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init",
               at: str | None = None) -> str:
    git(repo, "add", "-A")
    if at:
        git(repo, "commit", "--allow-empty", "-m", msg,
            env_dates=(at, at))
    else:
        git(repo, "commit", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> Path:
    """Git-репо с каркасом change-пакета (ветка main, чистое дерево)."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "src/widget.py", "X = 1\n")
    commit_all(repo, "init", at="2026-10-10T10:00:00 +0000")
    return repo


def write_final(repo: Path, *, verdict: str = "PASS", commit: str | None = None,
                date: str | None = None) -> Path:
    """Артефакт regress-final.md в формате flowctl regress (J51.2)."""
    commit = commit or git(repo, "rev-parse", "HEAD")
    date = date or datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    p = repo / "test-model" / "regress" / CHANGE / "regress-final.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"# Regress {CHANGE} — regress-final.md\n\n"
        f"- change: {CHANGE}\n"
        f"- date: {date}\n"
        f"- commit: {commit}\n"
        f"- verdict: {verdict}\n"
        f"- diff source: git diff main...HEAD\n"
        f"- changed files: 1\n"
        f"- suites: tests\n"
        f"- pytest exit code: 0\n",
        encoding="utf-8")
    return p


def days_ago_iso(days: int) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) \
        - datetime.timedelta(days=days)
    return dt.isoformat(timespec="seconds")


# ------------------------------------------------- J51.3: ворота

class TestRegressFinalGate:
    def test_missing_artifact(self, tmp_path):
        """TC-J51-021: артефакта нет → REGRESS_FINAL_MISSING и в
        check_regress_final, и в общем missing списка check_change."""
        repo = make_repo(tmp_path)
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_MISSING" in problems[0]
        assert "regress-final.md" in problems[0]
        missing = pr_validate.check_change(repo, CHANGE, f"[{CHANGE}] Merge 1.1")
        assert any("REGRESS_FINAL_MISSING" in m for m in missing)

    def test_numbered_artifact_is_not_final(self, tmp_path):
        """TC-J51-022: нумерованный regress-1.md (даже PASS и свежий)
        финальным не считается → REGRESS_FINAL_MISSING."""
        repo = make_repo(tmp_path)
        num = repo / "test-model" / "regress" / CHANGE / "regress-1.md"
        num.parent.mkdir(parents=True, exist_ok=True)
        num.write_text(
            f"# Regress {CHANGE} — regress-1.md\n\n"
            f"- change: {CHANGE}\n- date: {days_ago_iso(0)}\n"
            f"- commit: {git(repo, 'rev-parse', 'HEAD')}\n- verdict: PASS\n",
            encoding="utf-8")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert problems and all("REGRESS_FINAL_MISSING" in p for p in problems)

    def test_fail_verdict_not_accepted(self, tmp_path):
        """TC-J51-023: вердикт FAIL → артефакт не засчитан
        (REGRESS_FINAL_MISSING), merge закрыт."""
        repo = make_repo(tmp_path)
        write_final(repo, verdict="FAIL", date=days_ago_iso(0))
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_MISSING" in problems[0]
        assert "FAIL" in problems[0]

    def test_stale_artifact_older_than_7_days(self, tmp_path):
        """TC-J51-024: свежесть > 7 дней → REGRESS_FINAL_STALE
        (commit при этом совпадает с HEAD)."""
        repo = make_repo(tmp_path)
        write_final(repo, date=days_ago_iso(8))
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]

    def test_fresh_artifact_within_7_days_ok(self, tmp_path):
        """TC-J51-024-позитив: 6 дней — свежесть проходит (не STALE)."""
        repo = make_repo(tmp_path)
        write_final(repo, date=days_ago_iso(6))
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_hash_mismatch_not_ancestor(self, tmp_path):
        """TC-J51-025: commit артефакта не совпадает с HEAD и не является
        его предком → REGRESS_FINAL_STALE."""
        repo = make_repo(tmp_path)
        write_final(repo, commit="deadbeef" * 5, date=days_ago_iso(0))
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "не совпадает" in problems[0]

    def test_ancestor_older_than_changed_files(self, tmp_path):
        """TC-J51-026: commit — предок HEAD, но старше последнего касания
        измененного файла → REGRESS_FINAL_STALE («более свежий, чем
        измененные файлы» — не выполнено)."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "touch a", at="2026-10-11T10:00:00 +0000")
        write(repo, "src/other.py", "Y = 2\n")
        commit_all(repo, "touch other", at="2026-10-12T10:00:00 +0000")
        write_final(repo, commit=c1, date=days_ago_iso(0))
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "старше последнего касания" in problems[0]

    def test_ancestor_fresher_than_changed_files_ok(self, tmp_path):
        """TC-J51-027: commit — предок HEAD и не старше измененных файлов
        (после прогона были коммиты без касания этих файлов) → ворота
        пропускают."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        write(repo, "src/widget.py", "X = 2\n")
        c2 = commit_all(repo, "change widget", at="2026-10-12T10:00:00 +0000")
        git(repo, "commit", "-q", "--allow-empty", "-m", "docs only",
            env_dates=("2026-10-13T10:00:00 +0000",
                       "2026-10-13T10:00:00 +0000"))
        write_final(repo, commit=c2, date=days_ago_iso(0))
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_pass_e2e_flowctl_final(self, tmp_path):
        """TC-J51-028: e2e — `flowctl regress --final` пишет артефакт
        (PASS, commit HEAD) → ворота пропускают (проблем нет)."""
        repo = make_repo(tmp_path)
        # пустой дифф → flowctl пишет PASS без прогона; commit = HEAD
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "flowctl.py"), "regress",
             "--repo", str(repo), "--change", CHANGE, "--final", "--json"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert (repo / "test-model" / "regress" / CHANGE
                / "regress-final.md").is_file()
        # после прогона коммит не менялся → артефакт валиден
        assert pr_validate.check_regress_final(repo, CHANGE) == []


# ------------------------------------------------- J51.4: роль

class TestRegressRunnerRole:
    def test_prompt_exists_with_header(self):
        """TC-J51-029: промпт regress_runner существует, со шапкой-версией
        и yaml-комментарием (режим/зона)."""
        p = FACTORY / "agents" / "regress_runner_agent.md"
        assert p.is_file()
        text = p.read_text(encoding="utf-8")
        assert "Версия:" in text  # шапка-версия
        assert "<!--" in text and "role: regress_runner" in text
        assert "mode: auto-edit" in text
        assert "test-model/regress/" in text
        # узкий бриф и различение баг/флак — в промпте
        assert "flowctl regress" in text
        assert "флак" in text
        assert "REGRESS_FINAL" in text or "--final" in text

    def test_prompt_registered_in_readme(self):
        """TC-J51-030: роль в реестре agents/README.md (таблица зон +
        секция со ссылкой на промпт)."""
        readme = (FACTORY / "agents" / "README.md").read_text(encoding="utf-8")
        assert "regress_runner_agent.md" in readme
        assert "test-model/regress/" in readme
        assert "J51.4" in readme or "regress_runner" in readme
