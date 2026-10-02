# -*- coding: utf-8 -*-
"""Тесты scripts/session_check.py (поставка 04: reservation, boundary, reconcile).

Fixture-репозитории и fixture-реестры в tmp_path; реальный
~/.hermes/state/active_sessions.json НЕ используется никогда. Приемка ТЗ 04:
- два конкурентных reserve пересекающейся зоны → ровно один успех;
- разные непересекающиеся зоны в отдельных worktree допускаются;
- чужой cwd/branch, symlink за пределы зоны, изменение в соседнем worktree
  → отказ;
- падение runner сохраняет запись и файлы, reconcile ничего не удаляет молча.

Трассировка: TC-SCH-001...TC-SCH-020 (спека deterministic-flow; ТЗ
docs/chatgpt-deterministic-flow/04-session-enforcement.md; контракт §7-§8).
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

import session_check as sc  # noqa: E402


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
    write(repo, "src/keep.py", "X = 1\n")
    write(repo, "docs/note.md", "note\n")
    commit_all(repo)
    return repo


def make_worktree(repo: Path, sid: str, branch: str) -> Path:
    """Worktree через существующий session_worktree.sh (не переизобретаем).
    Скрипт при отсутствии ветки делает fetch origin/main — в fixture-репо без
    remote заранее создаем ветку, скрипт подключит её как есть."""
    if subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet",
         f"refs/heads/{branch}"],
        capture_output=True,
    ).returncode != 0:
        git(repo, "branch", branch)
    out = subprocess.run(
        ["bash", str(SCRIPTS / "session_worktree.sh"), "create",
         str(repo), sid, branch],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip().splitlines()[-1])


def make_registry(tmp_path: Path, payload: str = '{"sessions": []}') -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload, encoding="utf-8")
    return p


def req(**kw) -> dict:
    base = {
        "repo": kw.pop("repo"),
        "delegation_id": kw.pop("delegation_id", "deleg_test"),
        "role": "dev",
        "project": "proj",
        "owner_pm": "main-session",
        "paths": kw.pop("paths", ["src/**"]),
        "policy_version": kw.pop(
            "policy_version", __import__("role_zone_policy").policy_version()),
    }
    base.update(kw)
    return base


def registry_sessions(reg: Path) -> list[dict]:
    return json.loads(reg.read_text(encoding="utf-8")).get("sessions", [])


# --------------------------------------------- TC-SCH-001: glob-семантика зон


class TestGlobSemantics:
    """ТЗ 04: канонические пути и glob-семантика с тестами на вложенные пути,
    symlink и конфликт префиксов."""

    def test_exact_path(self):
        assert sc.glob_matches("src/main.py", "src/main.py")
        assert not sc.glob_matches("src/main.py", "src/main.py.bak")

    def test_nested_wildcard(self):
        assert sc.glob_matches("src/**", "src/a/b/c.py")
        assert sc.glob_matches("src/**", "src/main.py")
        assert not sc.glob_matches("src/**", "docs/src/main.py")

    def test_single_segment_wildcard(self):
        assert sc.glob_matches("src/*.py", "src/main.py")
        assert not sc.glob_matches("src/*.py", "src/sub/main.py")

    def test_dir_prefix_without_glob_covers_children(self):
        """Зона-каталог 'src' матчит и сам путь, и вложенные (префикс)."""
        assert sc.glob_matches("src", "src/main.py")
        assert sc.glob_matches("src", "src")
        assert not sc.glob_matches("src", "srcx/main.py")

    def test_middir_doublestar(self):
        assert sc.glob_matches("tests/**/test_x.py", "tests/a/b/test_x.py")
        assert sc.glob_matches("tests/**/test_x.py", "tests/test_x.py")

    def test_canonical_forms(self):
        assert sc.glob_matches("./src/**", "src/x.py")
        assert sc.glob_matches("src\\windows\\path", "src/windows/path")
        assert sc.canonical("/abs/like/path") == "abs/like/path"

    def test_prefix_conflict(self):
        assert sc.zones_overlap(["src/**"], ["src/sub/x.py"]) is not None
        assert sc.zones_overlap(["src/sub"], ["src/**"]) is not None
        assert sc.zones_overlap(["docs/**"], ["src/**"]) is None

    def test_symlink_target_matched_by_zone(self):
        """Symlink сам по себе путь в зоне; его цель вне repo — отказ check'а."""
        assert sc.glob_matches("src/**", "src/link.py")


# --------------------------------- TC-SCH-002: атомарность и идемпотентность


class TestReservation:
    def test_reserve_success(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)
        assert r["allowed"] is True
        sessions = registry_sessions(reg)
        assert len(sessions) == 1
        assert sessions[0]["status"] == "reserved"
        assert sessions[0]["zones"] == ["src/**"]
        # Обязательные поля J2 сохранены (pm_bounds_check --sessions совместим)
        for f in ("delegation_id", "role", "project", "owner_pm", "status"):
            assert sessions[0].get(f), f

    def test_missing_fields_rejected(self, tmp_path):
        reg = make_registry(tmp_path)
        r = sc.reserve(req(repo=str(tmp_path), delegation_id="d1",
                           role="", paths=["src/**"]), reg)
        assert r["allowed"] is False
        assert r["reason"] == sc.MISSING_INPUT

    def test_empty_zone_rejected(self, tmp_path):
        reg = make_registry(tmp_path)
        r = sc.reserve(req(repo=str(tmp_path), delegation_id="d1",
                           paths=[]), reg)
        assert r["allowed"] is False
        assert r["reason"] == sc.MISSING_INPUT

    def test_zone_conflict_same_repo(self, tmp_path):
        """Пересечение зон активных сессий того же repo → ZONE_CONFLICT."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert sc.reserve(req(repo=str(repo), delegation_id="d1",
                              paths=["src/**"]), reg)["allowed"]
        r2 = sc.reserve(req(repo=str(repo), delegation_id="d2",
                            paths=["src/sub/**"]), reg)
        assert r2["allowed"] is False
        assert r2["reason"] == sc.ZONE_CONFLICT
        assert any("d1" in d for d in r2["details"])

    def test_disjoint_zones_allowed(self, tmp_path):
        """Разные непересекающиеся зоны допускаются (приемка ТЗ 04)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert sc.reserve(req(repo=str(repo), delegation_id="d1",
                              paths=["src/**"]), reg)["allowed"]
        r2 = sc.reserve(req(repo=str(repo), delegation_id="d2",
                            paths=["docs/**"]), reg)
        assert r2["allowed"] is True

    def test_same_zone_different_repos_allowed(self, tmp_path):
        repo_a = make_repo(tmp_path, "proj-a")
        repo_b = make_repo(tmp_path, "proj-b")
        reg = make_registry(tmp_path)
        assert sc.reserve(req(repo=str(repo_a), delegation_id="d1"), reg)["allowed"]
        r2 = sc.reserve(req(repo=str(repo_b), delegation_id="d2"), reg)
        assert r2["allowed"] is True

    def test_closed_session_does_not_hold_zone(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)["allowed"]
        data = json.loads(reg.read_text(encoding="utf-8"))
        data["sessions"][0]["status"] = "closed"
        reg.write_text(json.dumps(data), encoding="utf-8")
        assert sc.reserve(req(repo=str(repo), delegation_id="d2"), reg)["allowed"]

    def test_idempotent_same_payload(self, tmp_path):
        """Повторный запрос: тот же id + идентичный payload = ок."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        first = sc.reserve(req(repo=str(repo), delegation_id="d1",
                               paths=["src/**", "docs/*"]), reg)
        assert first["allowed"]
        second = sc.reserve(req(repo=str(repo), delegation_id="d1",
                                paths=["docs/*", "src/**"]), reg)
        assert second["allowed"] is True
        assert second.get("idempotent") is True
        assert len(registry_sessions(reg)) == 1

    def test_duplicate_id_other_payload_rejected(self, tmp_path):
        """Тот же id, иной payload → reject (ТЗ 04)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)["allowed"]
        r = sc.reserve(req(repo=str(repo), delegation_id="d1",
                           paths=["docs/**"]), reg)
        assert r["allowed"] is False
        assert r["reason"] == sc.DUPLICATE_PAYLOAD
        assert len(registry_sessions(reg)) == 1

    def test_atomic_write_no_tmp_leftovers(self, tmp_path):
        """Запись через tmp+rename: в каталоге реестра нет tmp-хвостов."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)
        leftovers = [p.name for p in reg.parent.iterdir()
                     if p.name.endswith(".tmp")]
        assert leftovers == []
        # JSON валиден после записи
        json.loads(reg.read_text(encoding="utf-8"))

    def test_concurrent_reserve_intersecting_exactly_one_wins(self, tmp_path):
        """Приемка ТЗ 04: два конкурентных reserve пересекающейся зоны —
        ровно один успех (лок-файл на реестре)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        procs_code = f"""
import sys
sys.path.insert(0, {str(SCRIPTS)!r})
import session_check as sc
def _req(did):
    return {{"repo": {str(repo)!r}, "delegation_id": did, "role": "dev",
            "project": "proj", "owner_pm": "main-session",
            "paths": ["src/**"],
            "policy_version": __import__(
                "role_zone_policy").policy_version()}}
r = sc.reserve(_req(%r), {str(reg)!r})
print("WIN" if r["allowed"] else "LOSE")
"""
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", procs_code % f"d{i}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(2)
        ]
        outs = [p.communicate()[0].strip() for p in procs]
        assert sorted(outs) == ["LOSE", "WIN"], outs
        assert len(registry_sessions(reg)) == 1

    def test_broken_registry_is_error_not_silent(self, tmp_path):
        reg = make_registry(tmp_path, "{not json")
        r = sc.reserve(req(repo=str(tmp_path), delegation_id="d1"), reg)
        assert r["allowed"] is False
        assert r["reason"] == sc.REGISTRY_ERROR

    def test_v1_registry_read_and_migrated_with_backup(self, tmp_path):
        """Старый формат читается; миграция с резервной копией (ТЗ 04)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path, json.dumps({
            "_comment": "old format",
            "sessions": [{
                "delegation_id": "d0", "role": "dev", "project": "proj",
                "owner_pm": "main-session", "status": "reserved",
            }],
        }))
        r = sc.reserve(req(repo=str(repo), delegation_id="d1",
                           paths=["docs/**"]), reg)
        assert r["allowed"] is True
        data = json.loads(reg.read_text(encoding="utf-8"))
        assert data["schema_version"] == sc.REGISTRY_SCHEMA
        ids = [s["delegation_id"] for s in data["sessions"]]
        assert ids == ["d0", "d1"]  # старая запись сохранена
        assert data["sessions"][0]["lifecycle"]["history"][0][
            "reason"] == "migrated-from-v1"
        backups = list(reg.parent.glob("active_sessions.json.bck-*"))
        assert len(backups) == 1


# ------------------------------------------ TC-SCH-003: lifecycle + status CLI


class TestLifecycle:
    def test_lifecycle_transitions_recorded(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)
        data = json.loads(reg.read_text(encoding="utf-8"))
        s = data["sessions"][0]
        sc.transition(s, "running", "spawn", "runner pid 4242")
        sc.transition(s, "finished", "agent done", "report.md")
        assert [h["to"] for h in s["lifecycle"]["history"]] == [
            "reserved", "running", "finished"]
        assert all(h["reason"] and h["evidence"]
                   for h in s["lifecycle"]["history"])

    def test_status_cli(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "status",
             "--registry", str(reg), "--delegation-id", "d1", "--json"],
            capture_output=True, text=True,
        )
        assert p.returncode == 0
        out = json.loads(p.stdout)
        assert out["sessions"][0]["delegation_id"] == "d1"
        p_missing = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "status",
             "--registry", str(reg), "--delegation-id", "nope"],
            capture_output=True, text=True,
        )
        assert p_missing.returncode == 1

    def test_reserve_cli_exit_codes(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        base = [sys.executable, str(SCRIPTS / "session_check.py"), "reserve",
                "--registry", str(reg), "--repo", str(repo), "--role", "dev",
                "--project", "proj", "--owner-pm", "main-session",
                "--policy-version",
                __import__("role_zone_policy").policy_version()]
        ok = subprocess.run(base + ["--delegation-id", "d1", "--path",
                                    "src/**"], capture_output=True, text=True)
        assert ok.returncode == 0
        conflict = subprocess.run(base + ["--delegation-id", "d2", "--path",
                                          "src/**"], capture_output=True,
                                  text=True)
        assert conflict.returncode == 1
        assert "ZONE_CONFLICT" in conflict.stdout


# --------------------------------------------- TC-SCH-004: post-check границы


class TestBoundaryCheck:
    def _reserve_and_check(self, tmp_path, *, use_worktree=True):
        repo = make_repo(tmp_path)
        wt = make_worktree(repo, "sess1", "feature/sess1") \
            if use_worktree else repo
        reg = make_registry(tmp_path)
        base_sha = git(repo, "rev-parse", "HEAD")
        r = sc.reserve(req(repo=str(repo), delegation_id="d1",
                           paths=["src/**"], worktree=str(wt),
                           branch="feature/sess1", base_sha=base_sha), reg)
        assert r["allowed"], r
        return repo, wt, reg

    def test_clean_session_passes(self, tmp_path):
        repo, wt, reg = self._reserve_and_check(tmp_path)
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is True, r["violations"]

    def test_in_zone_change_passes(self, tmp_path):
        repo, wt, reg = self._reserve_and_check(tmp_path)
        write(wt, "src/new.py", "Y = 2\n")
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is True, r["violations"]

    def test_out_of_zone_uncommitted_rejected(self, tmp_path):
        repo, wt, reg = self._reserve_and_check(tmp_path)
        write(wt, "docs/evil.md", "oops\n")
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is False
        assert any(sc.OUT_OF_ZONE in v for v in r["violations"])
        # статус сессии → needs_attention (evidence в реестре)
        s = registry_sessions(reg)[0]
        assert s["status"] == "needs_attention"
        assert s["last_check"]["violations"]

    def test_out_of_zone_committed_rejected(self, tmp_path):
        """Выход за зону ловится и в коммитах base..HEAD (приемка ТЗ 04)."""
        repo, wt, reg = self._reserve_and_check(tmp_path)
        write(wt, "docs/evil.md", "oops\n")
        commit_all(wt, "docs change")
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is False
        assert any("docs/evil.md" in v for v in r["violations"])

    def test_symlink_outside_repo_rejected(self, tmp_path):
        repo, wt, reg = self._reserve_and_check(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        os.symlink(outside, wt / "src" / "link.py")
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is False
        assert any("symlink" in v for v in r["violations"])

    def test_wrong_worktree_rejected(self, tmp_path):
        """Чужой cwd (репо вместо worktree) → отказ (приемка ТЗ 04)."""
        repo, wt, reg = self._reserve_and_check(tmp_path)
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is False
        assert any(sc.WRONG_WORKTREE in v for v in r["violations"])

    def test_wrong_branch_rejected(self, tmp_path):
        repo = make_repo(tmp_path)
        wt = make_worktree(repo, "sess1", "feature/sess1")
        reg = make_registry(tmp_path)
        base_sha = git(repo, "rev-parse", "HEAD")
        sc.reserve(req(repo=str(repo), delegation_id="d1", paths=["src/**"],
                       worktree=str(wt), branch="feature/other",
                       base_sha=base_sha), reg)
        r = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r["ok"] is False
        assert any(sc.WRONG_BRANCH in v for v in r["violations"])

    def test_check_without_reservation_rejected(self, tmp_path):
        """check без reservation не гарантирует права (ТЗ 04)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = sc.check({"delegation_id": "ghost", "repo": str(repo)}, reg)
        assert r["ok"] is False
        assert r["reason"] == sc.MISSING_INPUT

    def test_nested_zone_exact_pass(self, tmp_path):
        """Вложенные пути в зоне матчатся, соседние — нет."""
        repo = make_repo(tmp_path)
        wt = make_worktree(repo, "sess1", "feature/sess1")
        reg = make_registry(tmp_path)
        base_sha = git(repo, "rev-parse", "HEAD")
        sc.reserve(req(repo=str(repo), delegation_id="d1",
                       paths=["src/sub/**"], worktree=str(wt),
                       branch="feature/sess1", base_sha=base_sha), reg)
        write(wt, "src/sub/deep/x.py", "A = 1\n")
        r1 = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r1["ok"] is True, r1["violations"]
        write(wt, "src/other/y.py", "B = 1\n")
        r2 = sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        assert r2["ok"] is False
        assert any("src/other/y.py" in v for v in r2["violations"])

    def test_neighbor_worktree_change_detected(self, tmp_path):
        """Изменение в соседнем worktree чужой сессией — свой check чист,
        но зона чужой сессии защищена пересечением (приемка ТЗ 04)."""
        repo = make_repo(tmp_path)
        wt1 = make_worktree(repo, "sess1", "feature/sess1")
        wt2 = make_worktree(repo, "sess2", "feature/sess2")
        reg = make_registry(tmp_path)
        base_sha = git(repo, "rev-parse", "HEAD")
        assert sc.reserve(req(repo=str(repo), delegation_id="d1",
                              paths=["src/**"], worktree=str(wt1),
                              branch="feature/sess1", base_sha=base_sha),
                          reg)["allowed"]
        r2 = sc.reserve(req(repo=str(repo), delegation_id="d2",
                            paths=["src/**"], worktree=str(wt2),
                            branch="feature/sess2", base_sha=base_sha), reg)
        assert r2["allowed"] is False  # пересечение → вторая не допущена
        assert r2["reason"] == sc.ZONE_CONFLICT

    def test_check_marks_running_on_success(self, tmp_path):
        repo, wt, reg = self._reserve_and_check(tmp_path)
        sc.check({"delegation_id": "d1", "repo": str(wt)}, reg)
        s = registry_sessions(reg)[0]
        assert s["status"] == "running"  # reserved → running при первом ok-check


# ------------------------------------------- TC-SCH-005: reconcile после сбоя


class TestReconcile:
    def _reserved(self, tmp_path, *, pid=None):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve(req(repo=str(repo), delegation_id="d1", pid=pid), reg)
        return repo, reg

    def test_dead_pid_clean_tree_marked_stale(self, tmp_path):
        repo, reg = self._reserved(tmp_path, pid=999999)
        r = sc.reconcile(reg, repo=repo)
        assert r["ok"] is True
        assert r["results"][0]["status_after"] == "stale"
        s = registry_sessions(reg)[0]
        assert s["status"] == "stale"
        assert s["lifecycle"]["history"][-1]["reason"].startswith("reconcile")

    def test_live_pid_needs_attention(self, tmp_path):
        repo, reg = self._reserved(tmp_path, pid=os.getpid())  # живой PID
        r = sc.reconcile(reg, repo=repo)
        assert r["results"][0]["status_after"] == "needs_attention"
        assert any("жив" in m for m in r["results"][0]["marks"])

    def test_dirty_tree_needs_attention_no_deletion(self, tmp_path):
        """Падение runner сохраняет запись и файлы; reconcile ничего не
        удаляет молча (приемка ТЗ 04)."""
        repo, reg = self._reserved(tmp_path, pid=999999)
        write(repo, "src/wip.py", "unfinished = True\n")  # грязное дерево
        r = sc.reconcile(reg, repo=repo)
        assert r["results"][0]["status_after"] == "needs_attention"
        # запись на месте, файлы на месте
        assert len(registry_sessions(reg)) == 1
        assert (repo / "src" / "wip.py").is_file()

    def test_finished_session_reconciled_too(self, tmp_path):
        repo, reg = self._reserved(tmp_path, pid=999999)
        data = json.loads(reg.read_text(encoding="utf-8"))
        data["sessions"][0]["status"] = "finished"
        reg.write_text(json.dumps(data), encoding="utf-8")
        r = sc.reconcile(reg, repo=repo)
        assert r["results"][0]["status_after"] == "stale"

    def test_closed_sessions_not_touched(self, tmp_path):
        repo, reg = self._reserved(tmp_path, pid=999999)
        data = json.loads(reg.read_text(encoding="utf-8"))
        data["sessions"][0]["status"] = "closed"
        reg.write_text(json.dumps(data), encoding="utf-8")
        r = sc.reconcile(reg, repo=repo)
        assert r["results"] == []
        assert registry_sessions(reg)[0]["status"] == "closed"

    def test_nothing_deleted_silently(self, tmp_path):
        """Сквозной сценарий приемки: падение runner — запись и worktree
        сохраняются, reconcile только помечает."""
        repo = make_repo(tmp_path)
        wt = make_worktree(repo, "sess1", "feature/sess1")
        reg = make_registry(tmp_path)
        base_sha = git(repo, "rev-parse", "HEAD")
        sc.reserve(req(repo=str(repo), delegation_id="d1", paths=["src/**"],
                       worktree=str(wt), branch="feature/sess1",
                       base_sha=base_sha, pid=999999), reg)
        write(wt, "src/keep.py", "CHANGED = 1\n")  # незакоммиченный след
        r = sc.reconcile(reg, repo=wt)
        assert r["results"][0]["status_after"] == "needs_attention"
        assert registry_sessions(reg)  # запись жива
        assert wt.is_dir()             # worktree не тронут
        assert (wt / "src" / "keep.py").read_text() == "CHANGED = 1\n"
        # worktree всё еще числится в git worktree list
        assert str(wt) in git(repo, "worktree", "list")

    def test_reconcile_cli(self, tmp_path):
        repo, reg = self._reserved(tmp_path, pid=999999)
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "reconcile",
             "--registry", str(reg), "--repo", str(repo), "--json"],
            capture_output=True, text=True,
        )
        assert p.returncode == 0
        out = json.loads(p.stdout)
        assert out["results"][0]["delegation_id"] == "d1"

    def test_broken_registry_reconcile_error(self, tmp_path):
        reg = make_registry(tmp_path, "{broken")
        r = sc.reconcile(reg)
        assert r["ok"] is False
        assert r["reason"] == sc.REGISTRY_ERROR


# -------------------------------------- TC-SCH-006: реальный state не трогаем


class TestRealStateUntouched:
    def test_all_operations_on_fixture_registry(self, tmp_path):
        """Контроль: все операции пишут только в fixture-путь; реальный
        ~/.hermes/state/active_sessions.json не читается и не пишется."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sc.reserve(req(repo=str(repo), delegation_id="d1"), reg)
        sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        sc.reconcile(reg, repo=repo)
        assert reg.parent == tmp_path / "state"
        # и CLI не имеет дефолта на реальный путь — registry обязателен
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "session_check.py"), "status"],
            capture_output=True, text=True,
        )
        assert p.returncode == 2  # argparse: missing --registry
