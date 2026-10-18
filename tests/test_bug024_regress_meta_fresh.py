# -*- coding: utf-8 -*-
"""BUG-024: мета-файлы в свежестной сверке check_regress_final.

Третье проявление того же класса (ekotov-wiki PR 191): свежестная
сверка _regress_commit_problem считает «последнее касание измененных
файлов» ВКЛЮЧАЯ мета-файлы, не влияющие на поведение тестов:

  - code-reviews/**            — мета Reviewer-Delegation;
  - test-model/regress/**      — сам артефакт и ПРЕДЫДУЩИЕ прогоны
                                 (BUG-023 исключал только свой change);
  - test-model/reviews/**      — ревью-мета.

Любой мета-коммит после regress-прогона → ложный REGRESS_FINAL_STALE →
обязательный лишний полный перегон.

Фикс: из множества «измененных файлов» при свежестной сверке исключены
мета-пути code-reviews/**, test-model/regress/**, test-model/reviews/**.
Продуктовые и тестовые файлы (services/**, backend/**, frontend/**,
tests/**, openspec/**) — как прежде: правка после прогона = STALE.

Трассировка:
  TC-BUG-024-001  мета-коммит code-reviews/** после прогона → PASS
  TC-BUG-024-002  мета-коммит test-model/reviews/** после прогона → PASS
  TC-BUG-024-003  regress-артефакт ДРУГОГО change (предыдущий прогон)
                  после прогона → PASS (расширение BUG-023)
  TC-BUG-024-004  продуктовый тест-файл (tests/**) после прогона →
                  REGRESS_FINAL_STALE как прежде
  TC-BUG-024-005  продуктовый файл (services/**) после прогона → STALE
  TC-BUG-024-006  в диффе ТОЛЬКО мета-файлы (все три префикса) →
                  _regress_commit_problem = None (не «не определимы»)
  TC-BUG-024-007  мета-файл + продуктовый файл после прогона → STALE
                  по продуктовому файлу, мета-файл не маскирует
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


# ------------------------------------------------- исключение мета-файлов

class TestMetaFreshExclusion:
    def test_code_reviews_meta_commit_passes(self, tmp_path):
        """TC-BUG-024-001: мета-коммит code-reviews/** (Reviewer-Delegation)
        после regress-прогона → НЕ STALE, ворота пропускают."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "code-reviews/add-widget/review-001.md",
              "# review-001\n- вердикт: approve\n")
        commit_all(repo, "commit review meta",
                   at="2026-10-12T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_test_model_reviews_meta_commit_passes(self, tmp_path):
        """TC-BUG-024-002: мета-коммит test-model/reviews/** после
        regress-прогона → НЕ STALE, ворота пропускают."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "test-model/reviews/add-widget/review-001.md",
              "# ревью кейсов\n")
        commit_all(repo, "commit review meta",
                   at="2026-10-12T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_previous_run_artifact_passes(self, tmp_path):
        """TC-BUG-024-003: regress-артефакт ДРУГОГО change (предыдущий
        прогон) закоммичен после текущего прогона → PASS (BUG-023
        исключал только свой change, BUG-024 — весь regress/**)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, OTHER_CHANGE, c1)
        commit_all(repo, "commit previous run artifact",
                   at="2026-10-12T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit own artifact",
                   at="2026-10-13T10:00:00 +0000")
        assert pr_validate.check_regress_final(repo, CHANGE) == []

    def test_product_test_file_newer_still_stale(self, tmp_path):
        """TC-BUG-024-004: продуктовый ТЕСТ-файл (tests/**) закоммичен
        после прогона → REGRESS_FINAL_STALE как прежде (исключение
        мета-файлов не маскирует поведенческие правки)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        write(repo, "tests/api/test_widget.py", "def test_x(): pass\n")
        commit_all(repo, "touch product test", at="2026-10-12T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "tests/api/test_widget.py" in problems[0]

    def test_services_file_newer_still_stale(self, tmp_path):
        """TC-BUG-024-005: продуктовый файл (services/**) закоммичен
        после прогона → REGRESS_FINAL_STALE как прежде."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        write(repo, "services/wiki/main.py", "X = 1\n")
        commit_all(repo, "touch service", at="2026-10-12T10:00:00 +0000")
        regress_artifact(repo, CHANGE, c1)
        commit_all(repo, "commit regress artifact",
                   at="2026-10-13T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "services/wiki/main.py" in problems[0]

    def test_only_meta_files_in_diff_passes(self, tmp_path):
        """TC-BUG-024-006: прямой вызов _regress_commit_problem — в диффе
        ТОЛЬКО мета-файлы всех трех префиксов → None (прогон удостоверяет
        весь поведенческий дифф; это НЕ «файлы не определимы»)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "code-reviews/add-widget/review-001.md", "# r\n")
        write(repo, "test-model/reviews/add-widget/cases.md", "# c\n")
        write(repo,
              f"test-model/regress/{OTHER_CHANGE}/regress-1.md", "# old\n")
        commit_all(repo, "meta only", at="2026-10-12T10:00:00 +0000")
        assert pr_validate._regress_commit_problem(repo, c1, CHANGE) is None

    def test_meta_commit_does_not_mask_product_change(self, tmp_path):
        """TC-BUG-024-007: мета-файл И продуктовый файл после прогона →
        STALE по продуктовому файлу (мета-исключение не расширяется на
        соседние поведенческие правки)."""
        repo = make_repo(tmp_path)
        c1 = feature_branch_with_run(repo)
        regress_artifact(repo, CHANGE, c1)
        write(repo, "code-reviews/add-widget/review-001.md", "# r\n")
        write(repo, "backend/api.py", "X = 1\n")
        commit_all(repo, "meta + product", at="2026-10-12T10:00:00 +0000")
        problems = pr_validate.check_regress_final(repo, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "backend/api.py" in problems[0]
