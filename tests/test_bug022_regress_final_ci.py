# -*- coding: utf-8 -*-
"""BUG-022: check_regress_final в CI дает ложный REGRESS_FINAL_STALE.

Воспроизведение на ekotov-wiki PR 189 — две причины:
  1. worktree в артефакте — локальный путь машины прогона; в CI-клоне он
     не читается как git-дерево и трактовался как STALE, хотя commit-предок
     проверяем. Фикс: нечитаемый worktree → неблокирующий FLOW-WARNING в
     stderr; STALE — только если дерево читается и HEAD ≠ commit.
  2. shallow-клон (actions/checkout fetch-depth 1): merge-base не может
     верифицировать предка. Фикс: тихий `git fetch --unshallow origin`
     (с таймаутом); если не помог и есть GITHUB_TOKEN+GITHUB_REPOSITORY —
     ancestry через GitHub API compare (base=HEAD...commit, статусы
     'behind'/'identical' = предок); иначе — явный FAIL UNKNOWN_ANCESTRY
     с человеческим объяснением (не молчаливый STALE).

Трассировка:
  TC-BUG-022-001  shallow-клон: unshallow помогает → предок верифицирован, ворота пропускают
  TC-BUG-022-002  shallow-клон: unshallow не удался, API недоступен → UNKNOWN_ANCESTRY (не STALE)
  TC-BUG-022-003  shallow-клон: API compare 'behind' (мок) → ворота пропускают
  TC-BUG-022-004  shallow-клон: API compare 'divergent' (мок) → REGRESS_FINAL_STALE
  TC-BUG-022-005  _github_compare_ancestor: статусы behind/identical → True; ahead/divergent → False
  TC-BUG-022-006  нечитаемый worktree (путь машины прогона) → WARNING, ворота пропускают
  TC-BUG-022-007  worktree читается, HEAD уехал → по-прежнему STALE
  TC-BUG-022-008  не-shallow репо с чужим commit → прежний STALE (без shallow-ветки и API)
"""
from __future__ import annotations

import datetime
import io
import json
import os
import subprocess
import sys
import urllib.request
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


def commit_all(repo: Path, msg: str = "init", at: str | None = None) -> str:
    git(repo, "add", "-A")
    if at:
        git(repo, "commit", "--allow-empty", "-m", msg, env_dates=(at, at))
    else:
        git(repo, "commit", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_origin(tmp_path: Path) -> tuple[Path, str]:
    """Origin: main (init) + ветка feature с прогонным коммитом A (трогает
    измененный файл) и пустым HEAD-коммитом B — предок A старше B, но не
    старше касания измененного файла (ворота должны пропускать)."""
    repo = tmp_path / "origin"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    write(repo, "README.md", "# p\n")
    commit_all(repo, "init", at="2026-10-10T10:00:00 +0000")
    git(repo, "checkout", "-q", "-b", "feature/x")
    write(repo, "src/widget.py", "X = 1\n")
    c_run = commit_all(repo, "touch widget", at="2026-10-11T10:00:00 +0000")
    git(repo, "commit", "-q", "--allow-empty", "-m", "empty after run",
        env_dates=("2026-10-12T10:00:00 +0000", "2026-10-12T10:00:00 +0000"))
    return repo, c_run


def shallow_clone(origin: Path, dest: Path) -> Path:
    r = subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "-b", "feature/x",
         f"file://{origin}", str(dest)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert pr_validate._is_shallow(dest)
    return dest


def write_final(repo: Path, *, commit: str, verdict: str = "PASS",
                worktree: str | None = None) -> Path:
    date = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    lines = [
        f"# Regress {CHANGE} — regress-final.md\n",
        f"- change: {CHANGE}",
        f"- date: {date}",
        f"- commit: {commit}",
        f"- verdict: {verdict}",
    ]
    if worktree:
        lines.append(f"- worktree: {worktree}")
    p = repo / "test-model" / "regress" / CHANGE / "regress-final.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def scrub_ci_env(monkeypatch) -> None:
    for var in ("GITHUB_TOKEN", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(var, raising=False)


# ------------------------------------------------- BUG-022: shallow-клон

class TestShallowAncestry:
    def test_shallow_unshallow_verifies_ancestor(self, tmp_path, monkeypatch):
        """TC-BUG-022-001: shallow-клон CI, commit артефакта — предок HEAD,
        которого нет в урезанной истории → тихий unshallow восстанавливает
        историю, merge-base верифицирует предка, ворота пропускают."""
        scrub_ci_env(monkeypatch)
        origin, c_run = make_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "ci-clone")
        assert pr_validate._git(clone, "cat-file", "-e", c_run) is None
        write_final(clone, commit=c_run)
        problems = pr_validate.check_regress_final(clone, CHANGE)
        assert problems == []
        # unshallow реально отработал — история полная
        assert not pr_validate._is_shallow(clone)

    def test_shallow_unshallow_fails_no_api_unknown_ancestry(
            self, tmp_path, monkeypatch):
        """TC-BUG-022-002: shallow-клон, unshallow не удался, токена нет →
        явный FAIL UNKNOWN_ANCESTRY с объяснением (не молчаливый STALE)."""
        scrub_ci_env(monkeypatch)
        monkeypatch.setattr(pr_validate, "_try_unshallow", lambda repo: False)
        origin, c_run = make_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "ci-clone")
        write_final(clone, commit=c_run)
        problems = pr_validate.check_regress_final(clone, CHANGE)
        assert len(problems) == 1
        assert "UNKNOWN_ANCESTRY" in problems[0]
        assert "shallow" in problems[0]
        assert "GITHUB_TOKEN" in problems[0]
        assert "REGRESS_FINAL_STALE" not in problems[0]

    def test_shallow_api_behind_passes(self, tmp_path, monkeypatch):
        """TC-BUG-022-003: shallow-клон, unshallow не удался, API доступен и
        compare HEAD...commit = 'behind' (commit — предок) → ворота
        пропускают (API-ветка, мок)."""
        monkeypatch.setattr(pr_validate, "_try_unshallow", lambda repo: False)
        monkeypatch.setenv("GITHUB_TOKEN", "t0k")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setattr(pr_validate, "_github_compare_ancestor",
                            lambda head, commit: True)
        origin, c_run = make_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "ci-clone")
        write_final(clone, commit=c_run)
        assert pr_validate.check_regress_final(clone, CHANGE) == []

    def test_shallow_api_divergent_stales(self, tmp_path, monkeypatch):
        """TC-BUG-022-004: API compare = 'divergent' (commit НЕ предок) →
        REGRESS_FINAL_STALE (API-ветка честно отклоняет)."""
        monkeypatch.setattr(pr_validate, "_try_unshallow", lambda repo: False)
        monkeypatch.setenv("GITHUB_TOKEN", "t0k")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setattr(pr_validate, "_github_compare_ancestor",
                            lambda head, commit: False)
        origin, c_run = make_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "ci-clone")
        write_final(clone, commit=c_run)
        problems = pr_validate.check_regress_final(clone, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "GitHub API compare" in problems[0]

    def test_github_compare_ancestor_statuses(self, tmp_path, monkeypatch):
        """TC-BUG-022-005: парсинг GitHub compare — 'behind'/'identical' =
        предок (True), 'ahead'/'divergent' = не предок (False), без
        GITHUB_TOKEN/GITHUB_REPOSITORY = None."""

        def fake_urlopen(payload):
            body = json.dumps(payload).encode("utf-8")

            class R:
                def __enter__(self):
                    return io.BytesIO(body)

                def __exit__(self, *a):
                    return False

            return R()

        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        assert pr_validate._github_compare_ancestor("h", "c") is None
        monkeypatch.setenv("GITHUB_TOKEN", "t0k")
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        for status, expected in (("behind", True), ("identical", True),
                                 ("ahead", False), ("divergent", False)):
            monkeypatch.setattr(urllib.request, "urlopen",
                                lambda req, timeout=None, s=status:
                                fake_urlopen({"status": s}))
            assert pr_validate._github_compare_ancestor("h", "c") is expected, \
                status

    def test_not_shallow_foreign_commit_still_stale(self, tmp_path):
        """TC-BUG-022-008: полный клон с чужим commit (не shallow) — прежний
        REGRESS_FINAL_STALE, shallow/API-ветки не трогаются."""
        origin, _ = make_origin(tmp_path)
        foreign = "d" * 40
        write_final(origin, commit=foreign)
        problems = pr_validate.check_regress_final(origin, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        assert "не является его предком" in problems[0]


# --------------------------------------------- BUG-022: worktree в CI

class TestWorktreeCi:
    def test_local_worktree_path_warns_not_stales(self, tmp_path, capsys):
        """TC-BUG-022-006: worktree в артефакте — локальный путь машины
        прогона (в CI-клоне нечитаем) → FLOW-WARNING в stderr, ворота
        пропускают при проверяемом commit; ложного STALE нет."""
        origin, c_run = make_origin(tmp_path)
        clone = shallow_clone(origin, tmp_path / "ci-clone")
        write_final(clone, commit=pr_validate._git(clone, "rev-parse", "HEAD"),
                    worktree="/home/pm/proj-worktrees/deleg_x")
        problems = pr_validate.check_regress_final(clone, CHANGE)
        assert problems == []
        err = capsys.readouterr().err
        assert "FLOW-WARNING" in err
        assert "/home/pm/proj-worktrees/deleg_x" in err

    def test_readable_worktree_ahead_still_stales(self, tmp_path, capsys):
        """TC-BUG-022-007: worktree читается как git-дерево и HEAD уехал
        вперед после прогона → по-прежнему REGRESS_FINAL_STALE."""
        origin, c_run = make_origin(tmp_path)
        write_final(origin, commit=c_run, worktree=str(origin))
        git(origin, "commit", "-q", "--allow-empty", "-m", "advance")
        problems = pr_validate.check_regress_final(origin, CHANGE)
        assert len(problems) == 1
        assert "REGRESS_FINAL_STALE" in problems[0]
        err = capsys.readouterr().err
        assert "FLOW-WARNING" not in err
