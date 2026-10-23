# -*- coding: utf-8 -*-
"""АУД-4: scope-чек «коммиты ветки vs change-id маркера» (Н21,
scripts/flow_scope_check.py).

Инцидент-класс: зеркальный IR-02 коммит ушел в чужую ветку (chore/
p23-fastline-dev с p12-линейкой) незамеченным.

Трассировка:
  TC-SC-001  свои коммиты ([change-id] в каждом subject) — OK
  TC-SC-002  чужой change-id в subject — WARN
  TC-SC-003  subject без маркера — WARN
  TC-SC-004  conventional-форма `chore(id):` засчитывается — OK
  TC-SC-005  generic-маркер [chore] против заявленного [chore] — OK
  TC-SC-006  generic PR: чужой конкретный id в subject — WARN
  TC-SC-007  BUG-NNN: свой — OK; чужой BUG — WARN
  TC-SC-008  merge-коммиты не участвуют
  TC-SC-009  --strict: WARN → exit 1; без --strict → exit 0
  TC-SC-010  --pr-text: id выводится из маркера текста PR
  TC-SC-011  невалидный change-id → ERROR exit 2
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_scope_check as fsc  # noqa: E402


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/ (PLAN-fixture)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "init")
    git(repo, "checkout", "-q", "-b", "feature/add-widget")
    return repo


def commit(repo: Path, rel: str, msg: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{rel}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", msg)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_scope_check.py"), *args],
        capture_output=True, text=True)


def test_sc_own_commits_ok(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[add-widget] первая часть")
    commit(repo, "b.py", "[add-widget] вторая часть")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "add-widget")
    assert res == []


def test_sc_foreign_change_id_warn(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[p12-fastline] чужая линейка (инцидент Н21)")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "add-widget")
    assert len(res) == 1
    assert "чужой id" in res[0]["reason"] and "p12-fastline" in res[0]["reason"]


def test_sc_no_marker_warn(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "правки без маркера")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "add-widget")
    assert len(res) == 1 and "нет маркера" in res[0]["reason"]


def test_sc_conventional_form_ok(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "chore(add-widget): часть пакета")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "add-widget")
    assert res == []


def test_sc_generic_chore_ok(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[chore] обслуживание скриптов")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "chore")
    assert res == []


def test_sc_generic_with_foreign_id_warn(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[chore] [p12-fastline] чужой id в chore-ветке")
    res = fsc.check_scope(fsc.branch_commits(repo, fsc.merge_base(repo)),
                          "chore")
    assert len(res) == 1 and "чужой id" in res[0]["reason"]


def test_sc_bug_ids(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[BUG-042] фикс")
    commits = fsc.branch_commits(repo, fsc.merge_base(repo))
    assert fsc.check_scope(commits, "BUG-042") == []
    res = fsc.check_scope(commits, "BUG-043")
    assert len(res) == 1 and "BUG-042" in res[0]["reason"]


def test_sc_merge_commits_skipped(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[add-widget] часть")
    git(repo, "checkout", "-q", "main")
    commit(repo, "base.py", "base")
    git(repo, "checkout", "-q", "feature/add-widget")
    git(repo, "merge", "-q", "--no-edit", "main")  # merge-коммит
    commits = fsc.branch_commits(repo, fsc.merge_base(repo))
    assert all("[add-widget]" in s or "base" in s
               for _, s in commits)
    assert not any(s.startswith("Merge") for _, s in commits)
    assert fsc.check_scope(commits, "add-widget") == []


def test_sc_cli_strict_exit_codes(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[p12-fastline] чужой")
    good = run_cli("--repo", str(repo), "--change-id", "add-widget")
    assert good.returncode == 0
    assert json.loads(good.stdout)["status"] == "WARN"
    strict = run_cli("--repo", str(repo), "--change-id", "add-widget",
                     "--strict")
    assert strict.returncode == 1


def test_sc_cli_pr_text_marker(tmp_path):
    repo = init_repo(tmp_path)
    commit(repo, "a.py", "[add-widget] работа")
    marker = tmp_path / "pr.txt"
    marker.write_text("Add widget\n\n[add-widget]\n", encoding="utf-8")
    p = run_cli("--repo", str(repo), "--pr-text", str(marker))
    assert p.returncode == 0
    assert json.loads(p.stdout)["change_id"] == "add-widget"


def test_sc_cli_invalid_change_id(tmp_path):
    repo = init_repo(tmp_path)
    p = run_cli("--repo", str(repo), "--change-id", "../evil")
    assert p.returncode == 2
    assert json.loads(p.stdout)["status"] == "ERROR"
