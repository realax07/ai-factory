# -*- coding: utf-8 -*-
"""J54: freeze-подтверждение tooling в воротах check_regress_final.

Критерий закрытия J54: tooling-пути (scripts/**, .github/**), тронутые
ПОСЛЕ commit regress-прогона, инвалидируют прогон особо — нота
«freeze tooling: tooling изменился после прогона, повтори
regress-final» (REGRESS_FINAL_STALE). Мета-исключения BUG-023/BUG-024
приоритетны: мета-коммит после прогона по-прежнему PASS (регрессия
BUG-024 не допущена).

Трассировка:
  TC-J54-FRZ-001  scripts/** после прогона → REGRESS_FINAL_STALE +
                  нота «freeze tooling»
  TC-J54-FRZ-002  .github/** после прогона → REGRESS_FINAL_STALE +
                  нота «freeze tooling»
  TC-J54-FRZ-003  только мета-файлы после прогона → PASS (BUG-024
                  не допущена)
  TC-J54-FRZ-004  мета + tooling после прогона → STALE с нотой
                  «freeze tooling» (мета не маскирует tooling)
  TC-J54-FRZ-005  tooling в самом прогоне (до commit артефакта) →
                  PASS — freeze касается только правок ПОСЛЕ прогона
  TC-J54-FRZ-006  продуктовый файл после прогона → STALE со старой
                  нотой, БЕЗ «freeze tooling» (не размывается)
  TC-J54-FRZ-007  прямой вызов _regress_commit_problem: tooling
                  файл в newer → нота «freeze tooling»
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


def feature_branch_with_run(repo: Path) -> str:
    """Ветка feature/x, прогон на c1 (дата коммита возвращается)."""
    git(repo, "checkout", "-q", "-b", "feature/x")
    return commit_all(repo, "change widget",
                      at="2026-10-11T10:00:00 +0000")


def touch_after_run(repo: Path, rel: str, text: str = "X = 2\n") -> None:
    """Файл в диффе PR, закоммиченный ПОСЛЕ regress-прогона."""
    write(repo, rel, text)
    commit_all(repo, f"touch {rel}", at="2026-10-12T10:00:00 +0000")


# ------------------------------------------------- freeze tooling (J54)

class TestToolingFreeze:
    def test_scripts_after_run_stale_with_note(self, tmp_path):
        """TC-J54-FRZ-001: scripts/** после прогона → REGRESS_FINAL_STALE
        с нотой «freeze tooling: tooling изменился после прогона,
        повтори regress-final»."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        touch_after_run(repo, "scripts/pr_validate.py", "X = 2\n")
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert ("freeze tooling: tooling изменился после прогона, "
                "повтори regress-final") in problems[0]
        assert "scripts/pr_validate.py" in problems[0]

    def test_github_after_run_stale_with_note(self, tmp_path):
        """TC-J54-FRZ-002: .github/** (workflow) после прогона →
        REGRESS_FINAL_STALE с нотой «freeze tooling»."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        touch_after_run(repo, ".github/workflows/ci.yml", "on: push\n")
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert ("freeze tooling: tooling изменился после прогона, "
                "повтори regress-final") in problems[0]
        assert ".github/workflows/ci.yml" in problems[0]

    def test_only_meta_after_run_passes(self, tmp_path):
        """TC-J54-FRZ-003: только мета-файлы (BUG-024: code-reviews/**,
        test-model/reviews/**, test-model/regress/**) после прогона →
        PASS — freeze tooling не расширяется на мета-исключения."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "code-reviews/add-widget/review-001.md", "# r\n")
        write(repo, "test-model/reviews/add-widget/cases.md", "# c\n")
        write(repo,
              f"test-model/regress/{OTHER_CHANGE}/regress-1.md", "# old\n")
        commit_all(repo, "meta only", at="2026-10-12T10:00:00 +0000")
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_meta_does_not_mask_tooling(self, tmp_path):
        """TC-J54-FRZ-004: мета-файл И tooling после прогона → STALE с
        нотой «freeze tooling» (мета-исключение не маскирует tooling)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "code-reviews/add-widget/review-001.md", "# r\n")
        touch_after_run(repo, "scripts/gate_runner.py", "X = 2\n")
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert ("freeze tooling: tooling изменился после прогона, "
                "повтори regress-final") in problems[0]
        assert "scripts/gate_runner.py" in problems[0]

    def test_tooling_touched_in_run_commit_itself_passes(self, tmp_path):
        """TC-J54-FRZ-005: tooling-файл в САМОМ commit прогона (правка
        до прогона, входит в удостоверяемый дифф) → PASS — freeze
        касается только правок ПОСЛЕ commit прогона."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        write(repo, "scripts/pr_validate.py", "X = 2\n")
        c1 = commit_all(repo, "change widget + tooling",
                        at="2026-10-11T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_product_file_keeps_plain_note(self, tmp_path):
        """TC-J54-FRZ-006: продуктовый файл после прогона → старая нота
        «старше последнего касания», БЕЗ «freeze tooling» (нота не
        размывается на не-tooling пути)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        touch_after_run(repo, "src/widget.py", "X = 2\n")
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "старше последнего касания измененного файла" in problems[0]
        assert "freeze tooling" not in problems[0]

    def test_direct_tooling_in_newer(self, tmp_path):
        """TC-J54-FRZ-007: прямой вызов _regress_commit_problem —
        tooling-файл новее commit прогона → нота «freeze tooling»."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        touch_after_run(repo, "scripts/flowctl.py", "X = 2\n")
        assert pr_validate._regress_commit_problem(repo, c1, CHANGE) == (
            "freeze tooling: tooling изменился после прогона, повтори "
            "regress-final (scripts/flowctl.py)")
