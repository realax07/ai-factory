# -*- coding: utf-8 -*-
"""Негативные тесты на фиксы review-003 (M1-M5 + minor'ы, поставка 04).

Каждый тест воспроизводит live-пробу ревьюера (code-reviews/
add-deterministic-flow/review-003.md) как регрессионный тест:
- Проба A/A2: rename-эскейп в post-check (M1);
- Пробы B/B2: миграция v1→v2 на check()/reconcile() без backup_registry (M2);
- Пробы C/P2: мертвый лок после crash (M3);
- Пробы D1-D3: zones_overlap FN '**/test/**' vs 'src/**' и FP 'src/**' vs
  'srcx/**' (M4);
- Проба E1: in-repo symlink за пределы зоны без отказа (M5);
- Пробы I/L/m8/m9: minor'ы m6/m7/m8/m9.
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
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "README.md", "# proj\n")
    write(repo, "src/keep.py", "X = 1\n")
    write(repo, "docs/note.md", "note\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m",
        "init")
    return repo, git(repo, "rev-parse", "HEAD")


def make_registry(tmp_path: Path, payload: str = '{"sessions": []}') -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload, encoding="utf-8")
    return p


def v1_registry(reg: Path, delegation_id: str, repo: str = "x") -> None:
    """V1-реестр (только обязательные поля J2, без schema_version)."""
    reg.write_text(json.dumps({"sessions": [{
        "delegation_id": delegation_id, "role": "dev", "project": "proj",
        "owner_pm": "main-session", "status": "reserved", "repo": repo,
        "paths": ["src/**"]}]}), encoding="utf-8")


def reserve(reg: Path, repo: Path, delegation_id: str = "d1",
            paths: list | None = None, **kw) -> dict:
    return sc.reserve({
        "repo": str(repo), "delegation_id": delegation_id, "role": "dev",
        "project": "proj", "owner_pm": "main-session",
        "paths": paths or ["src/**"],
        "policy_version": __import__("role_zone_policy").policy_version(),
        **kw}, reg)


def registry_backup_names(reg: Path) -> list[str]:
    return sorted(p.name for p in reg.parent.iterdir() if ".bck-" in p.name)


# ------------------------------------------- M1: rename-эскейп в post-check


class TestM1RenameEscape:
    def test_committed_rename_into_zone_caught(self, tmp_path):
        """TC-FLW-002: Проба A: файл, созданный вне зоны и переименованный в зону,
        виден по старому пути (git log --no-renames), check отказывает."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "docs/evil.md", "evil\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "evil")
        git(repo, "mv", "docs/evil.md", "src/ok.py")
        git(repo, "commit", "-qm", "rename into zone")
        assert reserve(reg, repo, base_sha=base)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is False
        assert any("docs/evil.md" in v for v in r["violations"])

    def test_porcelain_rename_keeps_old_path(self, tmp_path):
        """TC-FLW-002: Проба A2: staged rename — старый путь (удаление вне зоны)
        попадает в список измененных путей."""
        repo, _ = make_repo(tmp_path)
        write(repo, "docs/hidden.md", "h\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "hidden")
        git(repo, "mv", "docs/hidden.md", "src/hidden.py")
        _, uncommitted = sc.changed_paths(repo, None)
        assert "src/hidden.py" in uncommitted
        assert "docs/hidden.md" in uncommitted

    def test_committed_rename_old_path_in_changed(self, tmp_path):
        """TC-FLW-002: Net-diff пуст по рожденному-и-удаленному пути, но git log
        --no-renames показывает оба пути всех коммитов диапазона."""
        repo, base = make_repo(tmp_path)
        write(repo, "docs/tmp.md", "x\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "tmp")
        git(repo, "mv", "docs/tmp.md", "src/tmp.py")
        git(repo, "commit", "-qm", "mv")
        committed, _ = sc.changed_paths(repo, base)
        assert "docs/tmp.md" in committed
        assert "src/tmp.py" in committed

    def test_in_zone_rename_still_passes(self, tmp_path):
        """TC-FLW-002: Renamе внутри зоны не ломает чистую сессию (нет ложных отказов)."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "src/a.py", "A = 1\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "a")
        git(repo, "mv", "src/a.py", "src/b.py")
        git(repo, "commit", "-qm", "mv in zone")
        assert reserve(reg, repo, base_sha=base)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is True, r["violations"]


# ----------------------- M2: миграция с бэкапом на check/reconcile тоже


class TestM2MigrateWithBackup:
    def test_check_migrates_v1_with_backup(self, tmp_path):
        """TC-FLW-002: Проба B: первый check() на v1-реестре мигрирует с бэкапом."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        v1_registry(reg, "d1", repo=str(repo))
        assert not registry_backup_names(reg)
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is True
        data = json.loads(reg.read_text(encoding="utf-8"))
        assert data["schema_version"] == sc.REGISTRY_SCHEMA
        assert len(registry_backup_names(reg)) == 1

    def test_reconcile_migrates_v1_with_backup(self, tmp_path):
        """TC-FLW-002: Проба B2: reconcile() на v1-реестре мигрирует с бэкапом."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        v1_registry(reg, "d1", repo=str(repo))
        sc.reconcile(reg, repo=repo)
        data = json.loads(reg.read_text(encoding="utf-8"))
        assert data["schema_version"] == sc.REGISTRY_SCHEMA
        assert len(registry_backup_names(reg)) == 1

    def test_reserve_migrates_v1_with_backup(self, tmp_path):
        """TC-FLW-002: Путь reserve не сломан: бэкап по-прежнему создается."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        v1_registry(reg, "d_old")  # чужой repo — конфликт зон не мешает
        assert reserve(reg, repo)["allowed"]
        data = json.loads(reg.read_text(encoding="utf-8"))
        assert data["schema_version"] == sc.REGISTRY_SCHEMA
        assert len(registry_backup_names(reg)) == 1

    def test_v2_registry_no_backup_created(self, tmp_path):
        """TC-FLW-002: На v2-реестре миграции нет — бэкап не создается."""
        repo, base = make_repo(tmp_path)
        p = tmp_path / "state" / "active_sessions.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"schema_version": sc.REGISTRY_SCHEMA, "sessions": []}),
            encoding="utf-8")
        assert reserve(p, repo, base_sha=base)["allowed"]
        assert sc.check({"delegation_id": "d1", "repo": str(repo)}, p)["ok"]
        assert registry_backup_names(p) == []


# -------------------------------- M3: мертвый лок (pid + авто-восстановление)


class TestM3DeadLock:
    def test_lock_contains_pid(self, tmp_path):
        """TC-FLW-002: Проба C: внутрь лока пишется pid владельца."""
        reg = make_registry(tmp_path)
        lock = sc._acquire_lock(reg)
        try:
            assert (lock / "pid").is_file()
            assert (lock / "pid").read_text(encoding="utf-8").strip() \
                == str(os.getpid())
        finally:
            sc._release_lock(lock)

    def test_dead_owner_lock_recovered(self, tmp_path):
        """TC-FLW-002: Проба P2: процесс умер с локом (SIGKILL) → мертвый лок снимается
        автоматически, захват повторяется (не TimeoutError навсегда)."""
        reg = make_registry(tmp_path)
        crash_code = (
            "import sys, signal, threading; sys.path.insert(0, %r); "
            "import session_check as sc; "
            "l = sc._acquire_lock(sc.Path(%r), timeout=2); "
            "print('locked', flush=True); signal.pause() if hasattr(signal, 'pause') "
            "else threading.Event().wait()"
            % (str(SCRIPTS), str(reg)))
        p = subprocess.Popen([sys.executable, "-c", crash_code],
                             stdout=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().strip() == "locked"
            p.kill()
            p.wait()
            lock = sc._acquire_lock(reg, timeout=5)  # снял мертвый лок
            sc._release_lock(lock)
        except TimeoutError:
            pytest.fail("мертвый лок не восстановился после crash владельца")
        finally:
            if p.poll() is None:
                p.terminate()
                p.wait()

    def test_live_owner_lock_times_out_with_pid(self, tmp_path):
        """TC-FLW-002: Живой владелец: TimeoutError, в сообщении pid владельца."""
        reg = make_registry(tmp_path)
        p = subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()"])
        try:
            lock = sc._acquire_lock(reg)
            (lock / "pid").write_text(str(p.pid), encoding="utf-8")
            with pytest.raises(TimeoutError, match=str(p.pid)):
                sc._acquire_lock(reg, timeout=0.2)
            sc._release_lock(lock)
        finally:
            p.terminate()
            p.wait()

    def test_lock_without_pid_reclaimed_after_timeout(self, tmp_path):
        """TC-FLW-002: Лок без pid-файла (оставлен старой версией скрипта) снимается по
        истечении таймаута — admission не блокируется навсегда."""
        reg = make_registry(tmp_path)
        lock = reg.parent / (reg.name + ".lock")
        lock.mkdir()
        acquired = sc._acquire_lock(reg, timeout=0.5)
        assert acquired == lock  # снят и захвачен заново (с pid-файлом)
        assert (lock / "pid").is_file()
        sc._release_lock(acquired)

    def test_release_lock_removes_pid_and_dir(self, tmp_path):
        """TC-FLW-002: _release_lock удаляет pid-файл и каталог (регрессия: rmdir на
        непустом каталоге молча оставлял лок навсегда)."""
        reg = make_registry(tmp_path)
        lock = sc._acquire_lock(reg)
        sc._release_lock(lock)
        assert not lock.exists()
        # лок можно захватить снова
        lock2 = sc._acquire_lock(reg)
        sc._release_lock(lock2)


# ----------------------------------- M4: zones_overlap '**/x/**' и FP


class TestM4ZonesOverlap:
    def test_doublestar_head_tail_vs_prefix(self, tmp_path):
        """TC-FLW-002: Пробы D/J: '**/test/**' vs 'src/**' — пересечение (путь
        src/a/test/x.py принадлежит обеим зонам), ZONE_CONFLICT срабатывает."""
        assert sc.zones_overlap(["**/test/**"], ["src/**"]) is not None
        assert sc.zones_overlap(["src/**"], ["**/test/**"]) is not None

    def test_no_false_positive_neighbor_prefix(self):
        """TC-FLW-002: Проба D: 'src/**' vs 'srcx/**' — общего пути нет, FN недопустим,
        но и FP здесь не нужен."""
        assert sc.zones_overlap(["src/**"], ["srcx/**"]) is None

    def test_star_vs_prefix_overlaps(self):
        """TC-FLW-002: Проба D: '*' (любой один сегмент) пересекается с 'src/**' — путь
        'src/x' матчится обоими."""
        assert sc.zones_overlap(["*"], ["src/**"]) is not None

    def test_disjoint_zones_still_disjoint(self):
        """TC-FLW-002: трассировка кейса (test-model/approved/add-deterministic-flow/)."""
        assert sc.zones_overlap(["src/**"], ["docs/**"]) is None
        assert sc.zones_overlap(["src/main.py"], ["src/other.py"]) is None
        assert sc.zones_overlap(["src/**"], ["tests/**"]) is None

    def test_zone_conflict_fires_for_middir_doublestar(self, tmp_path):
        """TC-FLW-002: Сквозной сценарий: активная сессия с '**/test/**' блокирует
        reserve 'src/**' того же repo (admission не пропускает пересечение)."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert reserve(reg, repo, "d1", paths=["**/test/**"])["allowed"]
        r2 = reserve(reg, repo, "d2", paths=["src/**"])
        assert r2["allowed"] is False
        assert r2["reason"] == sc.ZONE_CONFLICT


# ----------------------------- M5: in-repo symlink за пределы зоны


class TestM5InRepoSymlink:
    def test_symlink_to_in_repo_out_of_zone_target_rejected(self, tmp_path):
        """TC-FLW-002: Проба E1: src/link.py → ../docs (цель в repo, вне зоны src/**)
        → отказ (буква приемки ТЗ 04: symlink за пределы зоны дают отказ)."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        os.symlink("../docs", repo / "src" / "link.py")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "link")
        assert reserve(reg, repo, base_sha=base)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is False
        assert any("src/link.py" in v for v in r["violations"])

    def test_symlink_to_in_zone_target_passes(self, tmp_path):
        """TC-FLW-002: Symlink на цель внутри зоны не дает ложного отказа."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        os.symlink("keep.py", repo / "src" / "link.py")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "link")
        assert reserve(reg, repo, base_sha=base)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is True, r["violations"]

    def test_symlink_outside_repo_still_rejected(self, tmp_path):
        """TC-FLW-002: Регресс: вне-repo symlink по-прежнему отказ (проба E2)."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        os.symlink(outside, repo / "src" / "link.py")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "link")
        assert reserve(reg, repo, base_sha=base)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is False


# --------------------------------------- minor'ы m6/m7/m8/m9


class TestMinors:
    def test_m6_reserve_cli_missing_registry_dir_exit_2(self, tmp_path, capsys):
        """TC-FLW-002: Проба I: reserve с --registry в несуществующий каталог →
        REGISTRY_ERROR + exit 2, не сырой FileNotFoundError-трейсбейс."""
        repo, _ = make_repo(tmp_path)
        rc = sc.main(["reserve", "--registry",
                      str(tmp_path / "nope" / "dir" / "reg.json"),
                      "--repo", str(repo), "--delegation-id", "d1",
                      "--role", "dev", "--project", "proj",
                      "--owner-pm", "pm", "--path", "src/**", "--json"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["reason"] == sc.REGISTRY_ERROR

    def test_m6_registry_dir_created_when_parent_exists(self, tmp_path):
        """TC-FLW-002: Регресс m6: существующий каталог реестра не блокирует reserve —
        файл реестра создастся (это нормальный путь первого reserve)."""
        repo, _ = make_repo(tmp_path)
        reg = tmp_path / "state" / "active_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        assert reserve(reg, repo)["allowed"]

    def test_m7_backup_names_unique_same_second(self, tmp_path):
        """TC-FLW-002: Проба L: два бэкапа в одну секунду не перезаписывают друг друга."""
        reg = make_registry(tmp_path)
        reg.write_text('{"sessions": []}', encoding="utf-8")
        b1 = sc.backup_registry(reg)
        b2 = sc.backup_registry(reg)
        assert b1 is not None and b2 is not None
        assert b1.name != b2.name
        assert b1.exists() and b2.exists()

    def test_m8_migrated_field_separate_from_idempotent(self, tmp_path):
        """TC-FLW-002: Проба m8: fresh reserve на v1-реестре → migrated=true,
        idempotent=false; на v2-реестре — migrated=false."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        v1_registry(reg, "d_old")  # чужой repo — конфликт зон не мешает
        res = reserve(reg, repo, "d1")
        assert res["allowed"] is True
        assert res["migrated"] is True
        assert res["idempotent"] is False
        res2 = reserve(reg, repo, "d2", paths=["docs/**"])  # вне зоны d1
        assert res2["allowed"] is True
        assert res2["migrated"] is False
        assert res2["idempotent"] is False

    def test_m9_reason_reflects_violation_kind(self, tmp_path):
        """TC-FLW-002: Проба m9: при WRONG_WORKTREE top-level reason — WRONG_WORKTREE,
        а не обобщенный OUT_OF_ZONE."""
        repo, base = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert reserve(reg, repo)["allowed"]  # без worktree/branch
        # Подменяем запись: worktree, не совпадающий с фактическим toplevel.
        data, _ = sc.registry_load(reg)
        data["sessions"][0]["worktree"] = str(tmp_path / "elsewhere")
        data["sessions"][0]["branch"] = "no-such-branch"
        others = make_registry(tmp_path / "reg2")
        sc.registry_write(others, data)
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, others)
        assert r["ok"] is False
        assert r["reason"] == sc.WRONG_WORKTREE

    def test_m9_reason_ok_on_clean(self, tmp_path):
        """TC-FLW-002: трассировка кейса (test-model/approved/add-deterministic-flow/)."""
        repo, _ = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        assert reserve(reg, repo)["allowed"]
        r = sc.check({"delegation_id": "d1", "repo": str(repo)}, reg)
        assert r["ok"] is True
        assert r["reason"] == sc.REASON_OK
