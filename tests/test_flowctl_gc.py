# -*- coding: utf-8 -*-
"""Тесты scripts/flowctl.py gc (J55: чистка веток/worktrees/стендов/tmp).

Механика J55 (backlog/J55-gc-этап-архивации-2026-10-19.md): dry-run по
умолчанию, --apply исполняет. Фикстуры — tmp_path (git-репо с bare-ремоутом,
реестр сессий, /tmp-записи, canned docker-факты); реальный docker и /tmp НЕ
трогаются (коллекторы monkeypatch'атся).

Негативы границ (J55):
- незакрытая ветка (уникальные коммиты) — вне досягаемости (--merged only);
- свежий (<24ч) Exited-контейнер — skip;
- бэкапы в /tmp — НЕ трогаются никогда.

Трассировка: TC-GC-001... (спека J55; принцип J51 — механика в скрипте).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flowctl  # noqa: E402


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo_with_remote(tmp_path: Path) -> Path:
    """Репо с bare-ремоутом origin: merged-ветка feat/merged (в main),
    НЕсмердженная feat/unmerged (уникальный коммит), main."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # proj уже создан autouse j41-фикстурой
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "f.txt").write_text("1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", "init")
    git(repo, "branch", "-M", "main")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    # merged-ветка: ответвление от main, коммит, вливание в main, пуш обоих
    git(repo, "checkout", "-q", "-b", "feat/merged")
    (repo / "m.txt").write_text("merged\n", encoding="utf-8")
    commit_all(repo, "feat merged")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "feat/merged", "-m", "merge feat")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "push", "-q", "origin", "feat/merged")
    # незакрытая ветка: уникальный коммит, НЕ в main
    git(repo, "checkout", "-q", "-b", "feat/unmerged")
    (repo / "u.txt").write_text("unmerged\n", encoding="utf-8")
    commit_all(repo, "wip unmerged")
    git(repo, "push", "-q", "origin", "feat/unmerged")
    git(repo, "checkout", "-q", "main")
    git(repo, "fetch", "-q", "origin")
    return repo


# ------------------------------------------- TC-GC-001: ветки (--merged only)


class TestBranchCandidates:
    def test_merged_only_and_main_excluded(self):
        """TC-GC-001: кандидаты — только смерженные удаленные ветки; main/
        master/HEAD исключаются всегда."""
        branches = ["origin/main", "origin/HEAD", "origin/feat/a",
                    "origin/chore/x", "upstream/main"]
        merged = {"origin/main", "origin/HEAD", "origin/feat/a",
                  "upstream/main", "origin/chore/x"}
        assert flowctl.gc_branch_candidates(branches, merged) == [
            "origin/chore/x", "origin/feat/a"]

    def test_unmerged_branch_out_of_reach(self):
        """TC-GC-002 (негатив границы): незакрытая ветка (уникальные коммиты)
        не входит в merged — вне досягаемости по построению."""
        branches = ["origin/main", "origin/wip"]
        merged = {"origin/main"}
        assert flowctl.gc_branch_candidates(branches, merged) == []

    def test_symbolic_head_ref_not_a_branch(self):
        """TC-GC-002a: символическое сокращение origin/HEAD («origin») — не
        ветка, кандидатом не становится (даже если попало в merged)."""
        branches = ["origin", "origin/main", "origin/feat/merged"]
        merged = {"origin", "origin/main", "origin/feat/merged"}
        assert flowctl.gc_branch_candidates(branches, merged) == \
            ["origin/feat/merged"]

    def test_collect_branches_real_repo(self, repo_with_remote):
        """TC-GC-003: сборщик фактов на реальном репо с ремоутом — merged
        содержит feat/merged и НЕ feat/unmerged."""
        branches, merged, src = flowctl.gc_collect_branches(repo_with_remote)
        assert "origin/feat/merged" in merged
        assert "origin/feat/unmerged" not in merged
        assert src == "origin/main"
        cand = flowctl.gc_branch_candidates(branches, merged)
        assert cand == ["origin/feat/merged"]


# ------------------------------------------ TC-GC-010: worktrees (реестр)


class TestWorktreeClassify:
    def test_done_statuses_remove(self):
        """TC-GC-010: done/closed (completed/finished/released) → remove."""
        for status in ("completed", "finished", "released"):
            cat, reason = flowctl.gc_classify_worktree(
                {"status": status, "worktree": "/x/wt"}, True)
            assert cat == "remove", (status, reason)

    def test_open_statuses_list_only(self):
        """TC-GC-011: незакрытые сессии — только список, решает ПМ."""
        for status in ("running", "needs_attention", "reserved", "stale"):
            cat, _ = flowctl.gc_classify_worktree(
                {"status": status, "worktree": "/x/wt"}, True)
            assert cat == "list_only"

    def test_gone_and_missing_worktree(self):
        """TC-GC-012: пути нет → gone (не remove); worktree в записи нет →
        skip."""
        assert flowctl.gc_classify_worktree(
            {"status": "completed", "worktree": "/x/wt"}, False)[0] == "gone"
        assert flowctl.gc_classify_worktree({"status": "completed"}, True)[0] \
            == "skip"


# ------------------------------------------ TC-GC-020: docker (границы 24ч)


class TestDockerClassify:
    def test_old_exited_prefixed_removed(self):
        """TC-GC-020: test-префикс + Exited > 24ч → remove."""
        cat, reason = flowctl.gc_classify_container(
            "test-stand-app-1", "exited", 30.0)
        assert cat == "remove" and "30" in reason
        cat, _ = flowctl.gc_classify_container("stand-db-1", "exited", 25.0)
        assert cat == "remove"

    def test_fresh_exited_skipped(self):
        """TC-GC-021 (негатив границы): свежий Exited (<24ч) — skip."""
        cat, reason = flowctl.gc_classify_container(
            "test-stand-app-1", "exited", 16.0)
        assert cat == "skip" and "16" in reason

    def test_running_and_prod_skipped(self):
        """TC-GC-022: живой контейнер — skip; прод-имя вне префиксов — skip
        (прод-стек вне досягаемости)."""
        assert flowctl.gc_classify_container(
            "test-stand-app-1", "running", 999.0)[0] == "skip"
        cat, _ = flowctl.gc_classify_container(
            "ekotov-wiki-par-app-1", "exited", 999.0)
        assert cat == "skip"
        cat, _ = flowctl.gc_classify_container("3x-ui", "exited", 999.0)
        assert cat == "skip"

    def test_unknown_age_skipped(self):
        """TC-GC-023: возраст неизвестен — не кандидат (не молчаливый снос)."""
        assert flowctl.gc_classify_container(
            "test-x", "exited", None)[0] == "skip"

    def test_network_rules(self):
        """TC-GC-024: сеть — префикс + пустая + старше 24ч; занятая/свежая/
        прод — skip."""
        assert flowctl.gc_classify_network("test-net", 30.0, 0)[0] == "remove"
        assert flowctl.gc_classify_network("test-net", 30.0, 2)[0] == "skip"
        assert flowctl.gc_classify_network("test-net", 1.0, 0)[0] == "skip"
        assert flowctl.gc_classify_network(
            "ekotov-wiki-par_default", 999.0, 0)[0] == "skip"

    def test_volume_only_candidate_and_prefix(self):
        """TC-GC-025: том — кандидат только по префиксу; снос только --deep
        (решает gc_apply/флаг, классификатор не удаляет)."""
        assert flowctl.gc_classify_volume("test-data")[0] == "candidate"
        assert flowctl.gc_classify_volume("ekotov-wiki-par-data")[0] == "skip"

    def test_iso_age_parse(self):
        """TC-GC-026: ISO c Z парсится; «0001-01-01…»/мусор → None."""
        old = "2026-10-01T00:00:00Z"
        now = time.mktime(time.strptime(
            "2026-10-02T00:00:00+0000", "%Y-%m-%dT%H:%M:%S%z"))
        age = flowctl._gc_iso_age_hours(old, now=now)
        assert age == pytest.approx(24.0, abs=0.1)
        assert flowctl._gc_iso_age_hours("0001-01-01T00:00:00Z") is None
        assert flowctl._gc_iso_age_hours("мусор") is None
        assert flowctl._gc_iso_age_hours(None) is None


# ------------------------------------------------ TC-GC-030: /tmp и бэкапы


class TestTmpClassify:
    def test_old_prefixed_removed(self):
        """TC-GC-030: deleg-*/стенды/пробы старше 24ч → remove."""
        for name in ("deleg-abc123", "bug013-stand-data", "j25-stand",
                     "bug015-probe", "p12rev-probes"):
            cat, reason = flowctl.gc_classify_tmp(name, 48.0)
            assert cat == "remove", (name, reason)

    def test_fresh_skipped(self):
        """TC-GC-031 (негатив границы): свежая (<24ч) запись — skip."""
        cat, reason = flowctl.gc_classify_tmp("deleg-abc", 2.0)
        assert cat == "skip" and "2" in reason

    def test_backups_never_touched(self):
        """TC-GC-032 (негатив границы): бэкапы НЕ трогаются никогда — даже
        старые и даже совпадающие с gc-признаками."""
        for name in ("p15-wiki-8-backups", "p12-rich-1-backups",
                     "my-stand-backup", "release-backups"):
            cat, reason = flowctl.gc_classify_tmp(name, 10_000.0)
            assert cat == "keep", (name, reason)
            assert "никогда" in reason

    def test_unrelated_skipped(self):
        """TC-GC-033: имя без gc-признаков — skip."""
        assert flowctl.gc_classify_tmp("hsperfdata_root", 999.0)[0] == "skip"
        assert flowctl.gc_classify_tmp("systemd-private-xxx", 999.0)[0] \
            == "skip"


# ----------------------------------- TC-GC-040: cmd_gc dry-run/apply (e2e)


def canned_docker() -> tuple[dict, str]:
    """Canned docker-факты: старый Exited test-контейнер, свежий Exited,
    живой, прод-контейнер; старая пустая test-сеть и занятая; тома."""
    return ({
        "containers": [
            {"name": "test-stand-app-1", "state": "exited", "age_h": 30.0},
            {"name": "test-fresh-1", "state": "exited", "age_h": 3.0},
            {"name": "test-live-1", "state": "running", "age_h": None},
            {"name": "ekotov-wiki-par-app-1", "state": "running",
             "age_h": None},
        ],
        "networks": [
            {"name": "test-net-old", "age_h": 48.0, "attached": 0},
            {"name": "test-net-busy", "age_h": 48.0, "attached": 2},
            {"name": "bridge", "age_h": 1000.0, "attached": 3},
        ],
        "volumes": [
            {"name": "test-data"},
            {"name": "ekotov-wiki-par-data"},
        ],
    }, "docker ok")


@pytest.fixture
def gc_env(tmp_path, monkeypatch):
    """Среда cmd_gc: репо с ремоутом, реестр (closed + needs_attention),
    worktree closed-сессии, /tmp-записи в tmp_path, canned docker."""
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # proj уже создан autouse j41-фикстурой
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo,
                   check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "f.txt").write_text("1\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "branch", "-M", "main")
    git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
    subprocess.run(["git", "init", "-q", "--bare",
                    str(tmp_path / "origin.git")], check=True)
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "feat/merged")
    (repo / "m.txt").write_text("m\n", encoding="utf-8")
    commit_all(repo, "feat")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "feat/merged", "-m", "merge")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "push", "-q", "origin", "feat/merged")
    git(repo, "fetch", "-q", "origin")

    # worktree closed-сессии (реальный git worktree):
    wt_closed = tmp_path / "wt-closed"
    git(repo, "worktree", "add", "-q", str(wt_closed), "-b", "flow/closed")
    wt_open = tmp_path / "wt-open"
    git(repo, "worktree", "add", "-q", str(wt_open), "-b", "flow/open")

    reg = tmp_path / "state" / "active_sessions.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"sessions": [
        {"delegation_id": "deleg-closed", "status": "completed",
         "repo": str(repo), "worktree": str(wt_closed)},
        {"delegation_id": "deleg-open", "status": "needs_attention",
         "repo": str(repo), "worktree": str(wt_open)},
    ]}), encoding="utf-8")

    # /tmp-записи (в tmp_path, коллектор патчится на этот корень):
    old = tmp_path / "sandbox" / "deleg-old123"
    old.mkdir(parents=True)
    backup = tmp_path / "sandbox" / "release-backups"
    backup.mkdir(parents=True)
    fresh = tmp_path / "sandbox" / "probe-fresh"
    fresh.mkdir(parents=True)
    os.utime(old, (time.time() - 48 * 3600,) * 2)
    os.utime(backup, (time.time() - 48 * 3600,) * 2)
    # fresh — свежая (mtime по умолчанию = сейчас)

    monkeypatch.setattr(flowctl, "gc_collect_docker", canned_docker)
    _orig_collect_tmp = flowctl.gc_collect_tmp
    sandbox = str(tmp_path / "sandbox")
    monkeypatch.setattr(flowctl, "gc_collect_tmp",
                        lambda root="/tmp", now=None:
                        _orig_collect_tmp(sandbox))
    return {"repo": repo, "registry": reg, "wt_closed": wt_closed,
            "wt_open": wt_open, "old": old, "backup": backup,
            "fresh": fresh}


def gc_run(gc_env, *extra: str):
    argv = ["gc", "--repo", str(gc_env["repo"]),
            "--registry", str(gc_env["registry"]), "--json", *extra]
    rc = flowctl.main(argv)
    return rc


class TestCmdGc:
    def test_dry_run_default_no_side_effects(self, gc_env, capsys):
        """TC-GC-040: dry-run по умолчанию — план печатается, НИЧЕГО не
        удалено (ветки/worktree/бэкапы/свежее на месте)."""
        rc = gc_run(gc_env)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["schema_version"] == "flowctl-gc/1"
        assert data["dry_run"] is True
        plan = data["plan"]
        # Ветки: только merged:
        assert plan["branches"]["remove"] == ["origin/feat/merged"]
        # Worktrees: closed → remove, needs_attention → list_only:
        assert [r["delegation_id"]
                for r in plan["worktrees"]["remove"]] == ["deleg-closed"]
        assert [r["delegation_id"]
                for r in plan["worktrees"]["list_only"]] == ["deleg-open"]
        # Docker: границы 24ч и префиксы:
        assert [c["name"] for c
                in plan["docker"]["containers"]["remove"]] == \
            ["test-stand-app-1"]
        assert [n["name"] for n
                in plan["docker"]["networks"]["remove"]] == ["test-net-old"]
        assert [v["name"] for v
                in plan["docker"]["volumes"]["candidates"]] == ["test-data"]
        assert data["counts"]["docker_volumes"] == 1
        # /tmp: старый deleg → remove; бэкап → keep; свежий → skip:
        assert [t["name"] for t in plan["tmp"]["remove"]] == ["deleg-old123"]
        assert [t["name"] for t in plan["tmp"]["keep"]] == ["release-backups"]
        assert [t["name"] for t in plan["tmp"]["skipped"]] == ["probe-fresh"]
        # Side effects отсутствуют:
        assert gc_env["wt_closed"].is_dir()
        assert gc_env["old"].is_dir()
        assert gc_env["backup"].is_dir()
        out = subprocess.run(
            ["git", "-C", str(gc_env["repo"]), "branch", "-r"],
            capture_output=True, text=True).stdout
        assert "feat/merged" in out

    def test_apply_removes_plan_and_respects_boundaries(
            self, gc_env, capsys, monkeypatch):
        """TC-GC-041: --apply исполняет план: merged-ветка удалена с ремоута,
        worktree closed-сессии снесен, старый deleg-каталог удален; бэкапы,
        свежие записи, needs_attention-worktree НЕ тронуты."""
        # docker-команды перехват (реальный docker не трогаем):
        docker_calls: list[list[str]] = []
        _orig_run = subprocess.run

        def fake_run(cmd, **kw):
            if cmd and cmd[0] == "docker":
                docker_calls.append(cmd)

                class P:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return P()

            return _orig_run(cmd, **kw)

        monkeypatch.setattr(flowctl.subprocess, "run", fake_run)
        rc = gc_run(gc_env, "--apply")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["dry_run"] is False
        joined = "\n".join(data["applied"])
        # Ветки: push origin --delete:
        assert "branch: origin/feat/merged" in joined
        # Worktree closed снесен, open НЕ тронут:
        assert "wt-closed" in joined
        assert not gc_env["wt_closed"].exists()
        assert gc_env["wt_open"].is_dir()
        # /tmp: старый удален, бэкап/свежий на месте:
        assert "deleg-old123" in joined
        assert not gc_env["old"].exists()
        assert gc_env["backup"].is_dir()
        assert gc_env["fresh"].is_dir()
        # Docker: только remove-кандидаты, тома НЕТ (нужен --deep):
        assert ["docker", "rm", "test-stand-app-1"] in docker_calls
        assert ["docker", "network", "rm", "test-net-old"] in docker_calls
        assert not any("volume" in c for c in docker_calls)
        assert "test-fresh-1" not in "\n".join(map(str, docker_calls))
        assert "ekotov-wiki-par-app-1" not in "\n".join(
            map(str, docker_calls))

    def test_apply_deep_removes_volumes(self, gc_env, capsys, monkeypatch):
        """TC-GC-042: --deep разрешает снос ТОМОВ gc-префиксов (и только их)."""
        docker_calls: list[list[str]] = []
        _orig_run = subprocess.run

        def fake_run(cmd, **kw):
            if cmd and cmd[0] == "docker":
                docker_calls.append(cmd)

                class P:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return P()

            return _orig_run(cmd, **kw)

        monkeypatch.setattr(flowctl.subprocess, "run", fake_run)
        rc = gc_run(gc_env, "--apply", "--deep")
        assert rc == 0
        assert ["docker", "volume", "rm", "test-data"] in docker_calls
        assert not any(
            "ekotov-wiki-par-data" in " ".join(c) for c in docker_calls)

    def test_registry_unreadable_degrades_not_silent(self, tmp_path, capsys):
        """TC-GC-043: реестр нечитаем — категория worktrees честно пропущена
        с диагностикой (не молчаливый пустой план), exit 0 в dry-run."""
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        rc = flowctl.main(["gc", "--registry", str(bad), "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "нечитаем" in data["plan"]["worktrees"]["note"]

    def test_docker_unavailable_degrades_not_silent(self, gc_env, capsys,
                                                    monkeypatch):
        """TC-GC-044: docker недоступен — категория пропущена с причиной,
        остальные категории работают, exit 0 в dry-run."""
        monkeypatch.setattr(
            flowctl, "gc_collect_docker",
            lambda: (None, "docker ps недоступен — категория пропущена"))
        rc = gc_run(gc_env)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["plan"]["docker"]["unavailable"] is True
        assert data["counts"]["docker_containers"] == 0
        assert data["plan"]["branches"]["remove"] == ["origin/feat/merged"]
