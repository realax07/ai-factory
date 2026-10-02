# -*- coding: utf-8 -*-
"""Тесты scripts/flow_state.py (поставка 02: read-only снимок FlowSnapshot).

Фикстуры строят временные git-репозитории в tmp_path; реальный
~/.hermes/state/ не трогается — реестр сессий всегда fixture-файл.
Трассировка: TC-FST-001...TC-FST-014 (спека deterministic-flow, Requirement
«Снимок состояния по scope»; ТЗ docs/chatgpt-deterministic-flow/02-flow-state.md).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402


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


REQ_APPROVED = """# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | История: r1\n\n## Описание\n...\n"""
REQ_DRAFT = REQ_APPROVED.replace("УТВЕРЖДЕН", "ЧЕРНОВИК")

TASKS = """# Tasks\n\n- [x] 1.1 готово\n- [ ] 1.2 в работе\n"""


def make_repo(
    tmp_path: Path,
    *,
    req: str | None = REQ_APPROVED,
    with_change: bool = True,
    change_id: str = "add-widget",
    with_tasks: bool = True,
    with_review: bool = False,
) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    if req:
        write(repo, "requirements.md", req)
    if with_change:
        write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
        write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
        if with_tasks:
            write(repo, f"openspec/changes/{change_id}/tasks.md", TASKS)
        write(
            repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
            "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n",
        )
    if with_review:
        write(
            repo, f"code-reviews/{change_id}/review-001-1.1.md",
            "## Вердикт: approve\n",
        )
    write(repo, "sdd.md", "# SDD\n")
    commit_all(repo)
    return repo


def registry_file(tmp_path: Path, payload: str) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text(payload, encoding="utf-8")
    return p


def inspect_json(repo: Path, **kw) -> dict:
    return flow_state.inspect(
        repo_arg=str(repo),
        project=kw.get("project", "proj"),
        flow=kw.get("flow", 1),
        change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"),
        registry=str(kw["registry"]) if kw.get("registry") else None,
    )


def fact(snapshot: dict, key: str) -> dict | None:
    for f in snapshot["facts"]:
        if f["key"] == key:
            return f
    return None


def cli(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_state.py"), "inspect",
         "--repo", str(repo), "--project", "proj", "--flow", "1",
         "--change", "add-widget", "--registry", str(repo.parent / "reg.json"),
         *extra],
        capture_output=True, text=True,
    )


# ----------------------------------------------------------------- tests


class TestSnapshotStructure:
    """TC-FST-001: snapshot содержит все обязательные поля."""

    def test_snapshot_fields(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        for key in ("schema_version", "scope", "repo_head", "dirty_paths",
                    "registry_digest", "facts", "problems", "snapshot_digest"):
            assert key in s, key
        assert s["scope"]["project"] == "proj"
        assert s["scope"]["flow"] == 1
        assert s["repo_head"] == git(repo, "rev-parse", "HEAD")
        for f in s["facts"]:
            for fld in ("key", "value", "source", "observed_at",
                        "fingerprint", "confidence"):
                assert fld in f, fld
            assert f["confidence"] in ("verified", "unknown")


class TestDeterminism:
    """TC-FST-002: двукратный вызов на неизменном вводе = эквивалентный JSON."""

    def test_double_call_equivalent(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": [{"project": "proj"}]}')
        a = inspect_json(repo, registry=reg)
        b = inspect_json(repo, registry=reg)
        # observed_at — временное поле, исключаем из сравнения
        for s in (a, b):
            for f in s["facts"]:
                f["observed_at"] = None
        assert a == b
        assert a["snapshot_digest"] == b["snapshot_digest"]


class TestRegistry:
    """TC-FST-003/004: отсутствующий/битый реестр = unknown, НЕ «нет сессий»."""

    def test_missing_registry_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        s = inspect_json(repo, registry=tmp_path / "nope.json")
        f = fact(s, "sessions.state")
        assert f is not None and f["confidence"] == "unknown"
        assert f["status"] == "unknown"
        assert any(p["code"] == "REGISTRY_MISSING" for p in s["problems"])
        # ценность: значение не «0 сессий»
        assert f["value"] is None

    def test_broken_registry_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, "{not json")
        s = inspect_json(repo, registry=reg)
        f = fact(s, "sessions.state")
        assert f["confidence"] == "unknown" and f["value"] is None
        assert any(p["code"] == "REGISTRY_INVALID_JSON" for p in s["problems"])

    def test_valid_registry(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": [{"project": "proj"}]}')
        s = inspect_json(repo, registry=reg)
        f = fact(s, "sessions.state")
        assert f["confidence"] == "verified"
        assert f["value"]["count"] == 1
        assert s["registry_digest"]  # sha256 от файла реестра


class TestGit:
    """TC-FST-005/006: repo_head, dirty_paths, отсутствующий ref."""

    def test_head_and_dirty(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        assert s["repo_head"] == git(repo, "rev-parse", "HEAD")
        assert s["dirty_paths"] == []
        write(repo, "untracked.txt", "x")
        s2 = inspect_json(repo, registry=reg)
        assert "untracked.txt" in s2["dirty_paths"]

    def test_missing_git_ref(self, tmp_path):
        # пустой репозиторий без коммитов: HEAD — отсутствующий ref
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        assert s["repo_head"] == ""
        assert fact(s, "git.head")["confidence"] == "unknown"
        assert fact(s, "git.head")["status"] == "unknown"


class TestReadonly:
    """TC-FST-007: снимок ничего не пишет; git status не меняется."""

    def test_no_writes(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        before_status = git(repo, "status", "--porcelain")
        before_files = {str(p.relative_to(repo)) for p in repo.rglob("*")
                        if ".git" not in p.parts}
        before_head = git(repo, "rev-parse", "HEAD")
        for _ in range(2):
            inspect_json(repo, registry=reg)
        after_files = {str(p.relative_to(repo)) for p in repo.rglob("*")
                       if ".git" not in p.parts}
        assert git(repo, "status", "--porcelain") == before_status
        assert after_files == before_files
        assert git(repo, "rev-parse", "HEAD") == before_head


class TestMissingInvalidUnknownReady:
    """TC-FST-008: различение missing/invalid/unknown/ready."""

    def test_statuses(self, tmp_path):
        # готовый change
        for sub in ("a", "b", "c", "d"):
            (tmp_path / sub).mkdir()
        repo_ok = make_repo(tmp_path / "a")
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo_ok, registry=reg)
        assert fact(s, "change.package")["status"] == "ready"

        # requirements отсутствует
        repo_no = make_repo(tmp_path / "b", req=None)
        s = inspect_json(repo_no, registry=reg)
        assert fact(s, "requirements.status")["status"] == "missing"

        # requirements есть, но без строки статуса — invalid
        repo_bad = make_repo(tmp_path / "c", req="# ТЗ без статуса\n")
        s = inspect_json(repo_bad, registry=reg)
        f = fact(s, "requirements.status")
        assert f["status"] == "invalid" and f["confidence"] == "unknown"

        # draft — есть факт, но не approved
        repo_draft = make_repo(tmp_path / "d", req=REQ_DRAFT)
        s = inspect_json(repo_draft, registry=reg)
        f = fact(s, "requirements.status")
        assert f["status"] == "ready" and f["value"] == "draft"
        assert f["confidence"] == "unknown"

    def test_change_without_tasks_file(self, tmp_path):
        repo = make_repo(tmp_path, with_tasks=False)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        assert fact(s, "change.tasks")["status"] == "missing"


class TestTaskScopes:
    """TC-FST-009: независимые состояния двух task ID одного change."""

    def test_two_tasks_different_status(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s1 = inspect_json(repo, registry=reg, task_id="1.1")
        s2 = inspect_json(repo, registry=reg, task_id="1.2")
        t1 = fact(s1, "task.1.1.status")
        t2 = fact(s2, "task.1.2.status")
        assert t1["value"] == "closed" and t1["confidence"] == "verified"
        assert t2["value"] == "open" and t2["confidence"] == "verified"
        # digest разные — scope различается
        assert s1["snapshot_digest"] != s2["snapshot_digest"]

    def test_unknown_task_not_ready(self, tmp_path):
        """Готовность не выводится из чекбокса: отсутствующая задача не ready."""
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg, task_id="9.9")
        t = fact(s, "task.9.9.status")
        assert t["status"] == "missing"
        assert t["value"] == "not_found"


class TestReviews:
    """TC-FST-010: review неоднозначен → unknown без ложного разрешения."""

    def test_review_without_verdict_unknown(self, tmp_path):
        repo = make_repo(tmp_path, with_review=False)
        write(repo, "code-reviews/add-widget/review-001-1.1.md", "текст без вердикта\n")
        commit_all(repo)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        f = fact(s, "reviews.approved")
        assert f["confidence"] == "unknown" and f["status"] == "unknown"

    def test_review_approve_verified(self, tmp_path):
        repo = make_repo(tmp_path, with_review=True)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        f = fact(s, "reviews.approved")
        assert f["confidence"] == "verified"
        assert f["value"]["approved"] == ["review-001-1.1.md"]


class TestSymlink:
    """TC-FST-011: symlink за пределы repo не следует (чужой evidence)."""

    def test_symlink_outside_repo(self, tmp_path):
        repo = make_repo(tmp_path)
        # чужой файл вне repo, на который указывает symlink внутри repo
        outside = tmp_path / "outside.md"
        outside.write_text("> Статус: УТВЕРЖДЕН\n", encoding="utf-8")
        link = repo / "requirements.md"
        link.unlink()
        os.symlink(outside, link)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg)
        f = fact(s, "requirements.status")
        assert f["value"] is None  # чужой evidence не нормализован
        assert f["confidence"] == "unknown"
        assert any(p["code"] == "PATH_OUTSIDE_REPO" for p in s["problems"])


class TestFlowIdentifiers:
    """TC-FST-012: обязательный идентификатор выбранного Flow."""

    def test_flow2_requires_bug(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg, flow=2, change_id="add-widget")
        assert any(p["code"] == "FLOW_ID_INVALID" for p in s["problems"])

    def test_flow2_bug_ok(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-001-Описание.md", "# BUG-001\n")
        commit_all(repo)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(
            repo, registry=reg, flow=2, change_id="BUG-001",
        )
        assert not any(p["code"] == "FLOW_ID_INVALID" for p in s["problems"])
        assert fact(s, "test_model.present")["value"]["bugs"] is True

    def test_flow4_requires_chore(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg, flow=4, change_id="add-widget")
        assert any(p["code"] == "FLOW_ID_INVALID" for p in s["problems"])
        s2 = inspect_json(repo, registry=reg, flow=4, change_id="chore")
        assert not any(p["code"] == "FLOW_ID_INVALID" for p in s2["problems"])

    def test_flow5_retro_missing(self, tmp_path):
        repo = make_repo(tmp_path, req=None)
        reg = registry_file(tmp_path, '{"sessions": []}')
        s = inspect_json(repo, registry=reg, flow=5, change_id="quick-fix")
        assert any(p["code"] == "FLOW5_RETRO_MISSING" for p in s["problems"])

    def test_unknown_flow_rejected(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = registry_file(tmp_path, '{"sessions": []}')
        with pytest.raises(ValueError):
            inspect_json(repo, registry=reg, flow=9)


class TestCLI:
    """TC-FST-013/014: CLI --json эквивалентен, читаемый вывод, exit codes."""

    def test_cli_json_ok(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo.parent / "reg.json").write_text('{"sessions": []}', encoding="utf-8")
        r = cli(repo, "--json")
        assert r.returncode == 0, r.stderr
        s = json.loads(r.stdout)
        assert s["schema_version"] == flow_state.SCHEMA_VERSION
        # повторный вызов — эквивалентный JSON
        r2 = cli(repo, "--json")
        s2 = json.loads(r2.stdout)
        for x in (s, s2):
            for f in x["facts"]:
                f["observed_at"] = None
        assert s == s2

    def test_cli_bad_repo_exit2(self, tmp_path):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "flow_state.py"), "inspect",
             "--repo", str(tmp_path / "no-repo"), "--project", "p",
             "--flow", "1", "--change", "a-b"],
            capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "FLOW-STATE-ERROR" in r.stdout

    def test_cli_human_readable(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo.parent / "reg.json").write_text('{"sessions": []}', encoding="utf-8")
        r = cli(repo)
        assert r.returncode == 0, r.stderr
        assert "flow_state:" in r.stdout
        assert "snapshot_digest:" in r.stdout

    def test_cli_read_error_nonzero(self, tmp_path):
        """Ошибка чтения источника → структурированная проблема + exit != 0."""
        repo = make_repo(tmp_path)
        outside = tmp_path / "outside.md"
        outside.write_text("> Статус: УТВЕРЖДЕН\n", encoding="utf-8")
        (repo / "requirements.md").unlink()
        os.symlink(outside, repo / "requirements.md")
        (repo.parent / "reg.json").write_text('{"sessions": []}', encoding="utf-8")
        r = cli(repo, "--json")
        assert r.returncode == 1
        s = json.loads(r.stdout)
        assert any(p["code"] == "PATH_OUTSIDE_REPO" for p in s["problems"])
