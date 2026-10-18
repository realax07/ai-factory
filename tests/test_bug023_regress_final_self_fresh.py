# -*- coding: utf-8 -*-
"""BUG-023: свежестная сверка check_regress_final считает «последнее
касание измененных файлов» включая сам артефакт regress-final.md.

Артефакт коммитится ПОСЛЕ прогона (commit прогона — его предок), потому
он ВСЕГДА новее удостоверяемого кода → REGRESS_FINAL_STALE навсегда,
ворота самоубийственны (живое воспроизведение: ekotov-wiki PR 189).

Фикс: сам артефакт и весь test-model/regress/<change-id>/** того же
change исключаются из множества «измененных файлов» при свежестной
сверке (_regress_commit_problem). Regress-артефакты других change и
обычные файлы исключения не получают.

Трассировка:
  TC-BUG-023-001  артефакт закоммичен после прогона (новее) → PASS
  TC-BUG-023-002  нумерованный regress-2.md того же change новее → PASS
  TC-BUG-023-003  чужой файл (src/**) новее прогона → STALE как прежде
  TC-BUG-023-004  regress-артефакт ДРУГОГО change новее → STALE
  TC-BUG-023-005  прямой вызов _regress_commit_problem: только
                  собственные regress-артефакты в диффе → None
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
OTHER_CHANGE = "add-gadget"


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


def regress_artifact(repo: Path, change: str, commit: str) -> Path:
    """Артефакт regress-final.md в формате flowctl regress (J51.2)."""
    date = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    p = repo / "test-model" / "regress" / change / "regress-final.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"# Regress {change} — regress-final.md\n\n"
        f"- change: {change}\n"
        f"- date: {date}\n"
        f"- commit: {commit}\n"
        f"- verdict: PASS\n"
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


# ------------------------------------------------- само-исключение

class TestRegressSelfExclusion:
    def test_artifact_committed_after_run_pass(self, tmp_path):
        """TC-BUG-023-001: прогона на c1, затем артефакт regress-final.md
        закоммичен ПОЗЖЕ (новее c1) → без само-исключения это вечный
        STALE; с фиксом ворота пропускают."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "change widget", at="2026-10-11T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-12T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_numbered_artifact_same_change_newer_pass(self, tmp_path):
        """TC-BUG-023-002: весь test-model/regress/<cid>/ того же change
        исключается — нумерованный regress-2.md, закоммиченный после
        прогона, тоже не протухает ворота."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "change widget", at="2026-10-11T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        write(repo, "test-model/regress/" + CHANGE + "/regress-2.md",
              "# кусок 2\n")
        commit_all(repo, "commit regress artifacts",
                   at="2026-10-12T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_regular_file_newer_still_stale(self, tmp_path):
        """TC-BUG-023-003: обычный измененный файл (src/other.py)
        закоммичен после прогона → REGRESS_FINAL_STALE как прежде
        (само-исключение не маскирует чужие правки)."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "change widget", at="2026-10-11T10:00:00 +0000")
        write(repo, "src/other.py", "Y = 2\n")
        commit_all(repo, "touch other", at="2026-10-12T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "старше последнего касания" in problems[0]
        assert "src/other.py" in problems[0]

    def test_other_change_regress_artifact_still_counts(self, tmp_path):
        """TC-BUG-023-004: regress-артефакт ДРУГОГО change (другой каталог)
        не исключается — новее прогона → REGRESS_FINAL_STALE."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "change widget", at="2026-10-11T10:00:00 +0000")
        regress_artifact(repo, OTHER_CHANGE, c1)
        commit_all(repo, "commit other-change artifact",
                   at="2026-10-12T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit own artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert OTHER_CHANGE in problems[0]

    def test_only_own_artifacts_in_diff_passes(self, tmp_path):
        """TC-BUG-023-005: прямой вызов _regress_commit_problem — в диффе
        ТОЛЬКО собственные regress-артефакты → None (это не «файлы не
        определимы»), прогон удостоверяет весь дифф."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        c1 = commit_all(repo, "change widget", at="2026-10-11T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-12T10:00:00 +0000")
        assert pr_validate._regress_commit_problem(repo, c1, CHANGE) is None
