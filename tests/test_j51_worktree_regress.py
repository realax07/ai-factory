# -*- coding: utf-8 -*-
"""J51.1 + J51.2: worktree-per-delegation в prepare и flowctl regress.

J51.1 (worktree-per-delegation):
  - prepare --create-worktree при ALLOW создает выделенный worktree через
    session_worktree.sh, путь — в ALLOW-объекте (record/reservation);
  - деградация: git worktree недоступен → WARN в ALLOW (exit 0, warnings в
    payload/записи), не FAIL;
  - энфорсер: другая активная делегация того же repo без выделенного worktree
    (или несколько активных в одном worktree) → block WORKTREE_MISSING;
    выключается FLOW_ENFORCER_WORKTREE=0; нечитаемый реестр — WARNING, не блок.

J51.2 (flowctl regress --change C):
  - дифф (base...HEAD, иначе staged) детерминированно маппится в тестовые
    домены: frontend/** → tests/web, backend/** → tests/api, остальное
    (в т.ч. scripts/) → tests/;
  - гоняются только затронутые существующие домены (pytest <пути> -q);
  - артефакт test-model/regress/<C>/regress-<N>.md: PASS/FAIL, commit hash,
    список сьютов, дата, хвост лога ≤50 строк; повторный прогон НЕ перезаписывает
    (номер растет); --final пишет regress-final.md (перезапись — по месту).

Трассировка:
  TC-J51-001  prepare --create-worktree: worktree создан, путь в ALLOW
  TC-J51-002  worktree недоступен → ALLOW + WARN (деградация, не FAIL)
  TC-J51-003  энфорсер: активная делегация repo без worktree → WORKTREE_MISSING
  TC-J51-004  энфорсер: активные с разными worktree → пропускает
  TC-J51-005  энфорсер: две активные в одном worktree → WORKTREE_MISSING
  TC-J51-006  энфорсер: ворота выключаются FLOW_ENFORCER_WORKTREE=0
  TC-J51-007  энфорсер: нечитаемый реестр → WARNING, не блок
  TC-J51-008  энфорсер: чужая активная делегация (другой repo) — не блок
  TC-J51-009  энфорсер: Worktree-строка чужого формата — ворота не ломаются
  TC-J51-010  regress: маппинг дифф → домены (unit)
  TC-J51-011  regress: источник диффа — staged при недоступном/пустом base
  TC-J51-012  regress: PASS end-to-end, формат артефакта (commit/дата/сьюты/лог)
  TC-J51-013  regress: FAIL → exit 1, вердикт FAIL, хвост лога с FAILED
  TC-J51-014  regress: повторный прогон → regress-2.md, regress-1.md не тронут
  TC-J51-015  regress --final → regress-final.md, без нумерованного; повтор —
              перезапись того же файла (идемпотентно)
  TC-J51-016  regress: дифф base...HEAD (коммиченная ветка) — источник в артефакте
  TC-J51-017  regress: пустой дифф → PASS без прогона, note в артефакте
  TC-J51-018  regress: не git-репозиторий → exit 2
  TC-J51-019  regress: change с ../ → exit 2, ничего не записано (traversal)
  TC-J51-020  regress: домен затронут, каталога тестов нет → WARN, exit 0
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
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
for p in (str(SCRIPTS), str(PLUGIN_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import flowctl  # noqa: E402
import enforcer  # noqa: E402


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")


def make_repo(tmp_path: Path) -> Path:
    """Fixture-репозиторий Флоу 1 (готов к dev_task) + домен tests/web."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    write(repo, "requirements.md", REQ_APPROVED)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "openspec/changes/add-widget/design.md", "# d\n")
    write(repo, "openspec/changes/add-widget/tasks.md",
          "# Tasks\n\n- [ ] 1.1 реализовать виджет\n")
    write(repo, "openspec/changes/add-widget/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n"
          "- THEN c\n")
    write(repo, "code-reviews/add-widget/review-001-1.1.md",
          "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "src/widget.py", "X = 1\n")
    write(repo, "tests/web/test_ok.py", "def test_ok():\n    assert True\n")
    commit_all(repo)
    return repo


def stage(repo: Path, rel: str, text: str) -> None:
    """Добавить файл и положить дифф в индекс (staged-дифф для regress)."""
    write(repo, rel, text)
    git(repo, "add", rel.replace("\\", "/"))


def flowctl_cmd(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
        capture_output=True, text=True,
    )


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "state" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"schema_version": "active-sessions/2", "sessions": []}',
                 encoding="utf-8")
    return p


def prepare_argv(repo: Path, registry: Path, state: Path, tmp_path: Path,
                 **kw) -> list[str]:
    return [
        "prepare",
        "--repo", str(repo), "--project", "proj", "--flow", "1",
        "--change", "add-widget", "--task", "1.1",
        "--action", kw.get("action", "dev_task"),
        "--role", "dev",
        "--path", "src/**",
        "--owner-pm", "pm-main",
        "--registry", str(registry), "--state", str(state),
        "--correlation-id", kw.get("cid", "corr0001"),
        "--json",
    ]


@pytest.fixture()
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда энфорсера: логи/реестр в tmp (как в test_j43)."""
    state = tmp_path / "enforcer-state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(tmp_path / "state" / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_WORKTREE", raising=False)
    yield state


def install_fake_run(monkeypatch, rc: int, out: str) -> None:
    """Мок subprocess.run внутри энфорсера (prepare ALLOW без side effects)."""
    def _fake(argv, **kw):
        return subprocess.CompletedProcess([], rc, out, "")
    monkeypatch.setattr(enforcer.subprocess, "run", _fake)


def flow4_goal(repo: Path) -> str:
    return ("flow: flow=4 role=dev repo={} scope=j51-demo "
            "paths=scripts/x.py\nЗадача: фабричный chore.\n").format(repo)


def session(delegation_id: str, repo: Path, status: str = "running",
            worktree: str | None = None) -> dict:
    return {
        "delegation_id": delegation_id, "role": "dev", "project": "proj",
        "owner_pm": "pm", "status": status, "repo": str(repo),
        "zones": ["scripts/**"], "worktree": worktree, "branch": None,
    }


def write_sessions(registry: Path, sessions: list[dict]) -> None:
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"schema_version": "active-sessions/2",
                    "sessions": sessions}, ensure_ascii=False),
        encoding="utf-8")


# ------------------------------------------------- J51.1: prepare/worktree

class TestPrepareWorktree:
    def test_prepare_create_worktree_path_in_allow(self, tmp_path):
        """TC-J51-001: prepare --create-worktree при ALLOW создает выделенный
        worktree (session_worktree.sh), путь — в ALLOW-объекте."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv += ["--create-worktree", "--branch", "w51"]
        r = flowctl_cmd(*argv)
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["prepared"] is True
        assert data["warnings"] == []
        wt = Path(data["record"]["worktree"])
        assert wt.is_dir()
        assert (wt / "SESSION.md").is_file()
        assert "proj-worktrees" in str(wt)
        # путь продублирован в reservation реестра:
        sessions = json.loads(
            reg.read_text(encoding="utf-8"))["sessions"]
        assert sessions[0]["worktree"] == str(wt)

    def test_prepare_worktree_unavailable_warns_not_fails(self, tmp_path):
        """TC-J51-002: деградация J51.1 — git worktree недоступен (ветка уже
        checked out) → ALLOW с WARN (warnings в payload/записи), exit 0,
        worktree в записи None, делегация не проваливается."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")  # checked out
        argv = prepare_argv(repo, reg, state, tmp_path)
        argv += ["--create-worktree", "--branch", branch]
        r = flowctl_cmd(*argv)
        assert r.returncode == 0, \
            "деградация J51.1: недоступный worktree — не FAIL"
        data = json.loads(r.stdout)
        assert data["prepared"] is True
        assert data["warnings"], "WARN обязан быть в ALLOW-объекте"
        assert "WORKTREE_UNAVAILABLE" in data["warnings"][0]
        assert data["record"]["worktree"] is None
        assert data["record"]["warnings"] == data["warnings"]
        # WARN виден и в текстовом выводе, и в goal-файле:
        assert "WORKTREE_UNAVAILABLE" in r.stderr
        goal = Path(data["record"]["goal_path"])
        assert goal.is_file()


# ------------------------------------------------- J51.1: энфорсер

class TestEnforcerWorktreeGate:
    def test_other_active_without_worktree_blocks(self, tmp_path,
                                                  plugin_env, monkeypatch):
        """TC-J51-003: активная делегация того же repo без worktree →
        block WORKTREE_MISSING."""
        repo = make_repo(tmp_path)
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]),
                       [session("deleg-aaa", repo, worktree=None)])
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-003")
        assert res is not None and res["action"] == "block"
        assert "WORKTREE_MISSING" in res["message"]

    def test_active_with_distinct_worktrees_passes(self, tmp_path,
                                                   plugin_env, monkeypatch):
        """TC-J51-004: активные делегации repo с выделенными (разными)
        worktree — ворота пропускают."""
        repo = make_repo(tmp_path)
        wts = tmp_path / "wts"
        (wts / "a").mkdir(parents=True)
        (wts / "b").mkdir(parents=True)
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]), [
            session("deleg-aaa", repo, worktree=str(wts / "a")),
            session("deleg-bbb", repo, worktree=str(wts / "b")),
        ])
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-004")
        assert res is None

    def test_two_active_in_same_worktree_blocks(self, tmp_path,
                                                plugin_env, monkeypatch):
        """TC-J51-005: две активные делегации одного repo в ОДНОМ worktree →
        block WORKTREE_MISSING (разные деревья обязательны)."""
        repo = make_repo(tmp_path)
        wt = str(tmp_path / "wts" / "shared")
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]), [
            session("deleg-aaa", repo, worktree=wt),
            session("deleg-bbb", repo, worktree=wt),
        ])
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-005")
        assert res is not None and res["action"] == "block"
        assert "WORKTREE_MISSING" in res["message"]

    def test_gate_disabled_by_env(self, tmp_path, plugin_env, monkeypatch):
        """TC-J51-006: FLOW_ENFORCER_WORKTREE=0 выключает ворота (escape для
        одиночной деградировавшей делегации)."""
        repo = make_repo(tmp_path)
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]),
                       [session("deleg-aaa", repo, worktree=None)])
        monkeypatch.setenv("FLOW_ENFORCER_WORKTREE", "0")
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-006")
        assert res is None

    def test_unreadable_registry_warns_not_blocks(self, tmp_path, plugin_env,
                                                  monkeypatch):
        """TC-J51-007: нечитаемый реестр — WARNING (worktree_gate_unavailable),
        не блок: проверка best-effort поверх ворот prepare."""
        repo = make_repo(tmp_path)
        reg = Path(os.environ["FLOW_ENFORCER_REGISTRY"])
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text("{битый json", encoding="utf-8")
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-007")
        assert res is None
        log = (plugin_env / "flow-enforcer.log").read_text(encoding="utf-8")
        assert "worktree_gate_unavailable" in log

    def test_other_repo_active_not_blocking(self, tmp_path, plugin_env,
                                            monkeypatch):
        """TC-J51-008: активная делегация ДРУГОГО repo без worktree — не блок
        (ворота просят параллельность только внутри одного repo)."""
        repo = make_repo(tmp_path)
        other = tmp_path / "other-proj"
        other.mkdir()
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]),
                       [session("deleg-aaa", other, worktree=None)])
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-008")
        assert res is None

    def test_foreign_format_worktree_string(self, tmp_path, plugin_env,
                                            monkeypatch):
        """TC-J51-009: Worktree-строка чужого формата в реестре (не путь)
        не ломает ворота и не блокирует — трактуется как отдельное дерево
        (негатив по парсингу worktree-поля)."""
        repo = make_repo(tmp_path)
        write_sessions(Path(os.environ["FLOW_ENFORCER_REGISTRY"]), [
            session("deleg-aaa", repo, worktree="wt:odd-format:007"),
        ])
        install_fake_run(monkeypatch, 0, '{"decision": {"status": "ALLOW"}}')
        res = enforcer.flow_enforce(
            "delegate_task", {"goal": flow4_goal(repo)}, "t-j51-009")
        assert res is None


# ------------------------------------------------- J51.2: regress

class TestRegressMapping:
    def test_domain_mapping_rules(self):
        """TC-J51-010: детерминированный маппинг дифф → домены."""
        assert flowctl.regress_domains(["frontend/a.js", "frontend/b.css"]) \
            == ["tests/web"]
        assert flowctl.regress_domains(["backend/x.py"]) == ["tests/api"]
        assert flowctl.regress_domains(["scripts/s.py"]) == ["tests"]
        assert flowctl.regress_domains(["docs/x.md", "src/widget.py"]) \
            == ["tests"]
        # микс: порядок файлов, без дублей
        assert flowctl.regress_domains(
            ["backend/x.py", "scripts/s.py", "frontend/a.js"]) \
            == ["tests/api", "tests/web", "tests"]
        assert flowctl.regress_domains([]) == []

    def test_diff_source_staged_fallback(self, tmp_path):
        """TC-J51-011: base...HEAD пуст/недоступен → staged-дифф."""
        repo = make_repo(tmp_path)  # HEAD == main, диффа нет
        stage(repo, "scripts/new.py", "Q = 1\n")
        files, source = flowctl.regress_diff_files(repo, "main")
        assert files == ["scripts/new.py"]
        assert "staged" in source
        # недоступный base → тоже staged
        files2, source2 = flowctl.regress_diff_files(repo, "no-such-base")
        assert files2 == ["scripts/new.py"]
        assert "staged" in source2


class TestRegressCommand:
    def test_regress_pass_artifact_format(self, tmp_path):
        """TC-J51-012: PASS end-to-end; артефакт regress-1.md с вердиктом,
        commit hash, сьютами, датой и хвостом лога."""
        repo = make_repo(tmp_path)
        stage(repo, "scripts/x.py", "A = 1\n")  # дифф → tests/
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j51-demo", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["suites"] == ["tests"]
        art = Path(data["artifact"])
        assert art == repo / "test-model" / "regress" / "j51-demo" \
            / "regress-1.md"
        text = art.read_text(encoding="utf-8")
        assert "verdict: PASS" in text
        assert f"commit: {git(repo, 'rev-parse', 'HEAD')}" in text
        assert "date: " in text
        assert "suites: tests" in text
        assert "1 passed" in text  # хвост лога с фактом прогона
        assert "diff source:" in text

    def test_regress_fail_verdict_and_tail(self, tmp_path):
        """TC-J51-013: упавший тест → verdict FAIL, exit 1, хвост лога
        содержит FAILED."""
        repo = make_repo(tmp_path)
        stage(repo, "tests/web/test_bad.py",
              "def test_bad():\n    assert False\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j51-demo", "--json")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "FAIL"
        assert data["pytest_exit"] == 1
        # tests/web/test_bad.py — не frontend/backend-префикс → домен tests/
        assert data["suites"] == ["tests"]
        text = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "verdict: FAIL" in text
        assert "FAILED" in text

    def test_regress_rerun_does_not_overwrite(self, tmp_path):
        """TC-J51-014: повторный regress — regress-2.md; regress-1.md не
        изменен (идемпотентность артефактов)."""
        repo = make_repo(tmp_path)
        stage(repo, "scripts/x.py", "A = 1\n")
        r1 = flowctl_cmd("regress", "--repo", str(repo),
                         "--change", "j51-demo", "--json")
        assert r1.returncode == 0
        first = Path(json.loads(r1.stdout)["artifact"]).read_text(
            encoding="utf-8")
        r2 = flowctl_cmd("regress", "--repo", str(repo),
                         "--change", "j51-demo", "--json")
        assert r2.returncode == 0
        arts = sorted(p.name for p in
                      (repo / "test-model" / "regress" / "j51-demo").iterdir())
        assert arts == ["regress-1.md", "regress-2.md"]
        assert Path(json.loads(r1.stdout)["artifact"]).read_text(
            encoding="utf-8") == first

    def test_regress_final_artifact(self, tmp_path):
        """TC-J51-015: --final → regress-final.md (не нумерованный); повторный
        --final перезаписывает тот же файл (идемпотентно)."""
        repo = make_repo(tmp_path)
        stage(repo, "scripts/x.py", "A = 1\n")
        r1 = flowctl_cmd("regress", "--repo", str(repo),
                         "--change", "j51-demo", "--final", "--json")
        assert r1.returncode == 0
        data1 = json.loads(r1.stdout)
        assert data1["final"] is True
        art = repo / "test-model" / "regress" / "j51-demo" / "regress-final.md"
        assert data1["artifact"] == str(art)
        assert art.is_file()
        arts1 = [p.name for p in
                 (repo / "test-model" / "regress" / "j51-demo").iterdir()]
        assert arts1 == ["regress-final.md"]
        r2 = flowctl_cmd("regress", "--repo", str(repo),
                         "--change", "j51-demo", "--final", "--json")
        assert r2.returncode == 0
        arts = [p.name for p in
                (repo / "test-model" / "regress" / "j51-demo").iterdir()]
        assert arts == ["regress-final.md"]

    def test_regress_uses_merge_base_diff(self, tmp_path):
        """TC-J51-016: коммиченная ветка — дифф main...HEAD (источник в
        артефакте), staged пуст."""
        repo = make_repo(tmp_path)
        git(repo, "checkout", "-q", "-b", "feature/x")
        write(repo, "backend/api.py", "B = 1\n")
        write(repo, "tests/api/test_api.py", "def test_api():\n"
              "    assert True\n")
        commit_all(repo, "feature")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j51-demo", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["diff_source"] == "git diff main...HEAD"
        # backend/api.py → tests/api; tests/api/test_api.py → tests/
        assert data["suites"] == ["tests/api", "tests"]
        text = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "diff source: git diff main...HEAD" in text

    def test_regress_empty_diff_pass_without_run(self, tmp_path):
        """TC-J51-017: пустой дифф — прогон не выполняется, PASS с note."""
        repo = make_repo(tmp_path)
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j51-demo", "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["pytest_exit"] is None
        assert data["suites"] == []
        text = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "прогон не выполнялся" in text

    def test_regress_not_a_git_repo(self, tmp_path):
        """TC-J51-018: не git-репозиторий → exit 2."""
        bare = tmp_path / "notrepo"
        bare.mkdir()
        r = flowctl_cmd("regress", "--repo", str(bare),
                        "--change", "j51-demo")
        assert r.returncode == 2

    def test_regress_rejects_traversal_change(self, tmp_path):
        """TC-J51-019: change с ../ → exit 2 с FLOWCTL-ERROR, НИЧЕГО не
        записано ни вне репозитория, ни внутри (path traversal,
        review-001 #1)."""
        repo = make_repo(tmp_path)
        probe = tmp_path / "escaped" / "probe"  # куда старый код писал бы
        bad_ids = [
            "../../../escaped/probe",  # escape за пределы репозитория
            "..",
            "a/b",
            "a..b",
            "",
        ]
        for bad in bad_ids:
            r = flowctl_cmd("regress", "--repo", str(repo),
                            "--change", bad)
            assert r.returncode == 2, bad
            assert "FLOWCTL-ERROR" in r.stderr, bad
        # вне репозитория не записано ничего
        assert not probe.exists()
        assert not (tmp_path / "escaped").exists()
        # и внутри репозитория тоже (валидация — до mkdir)
        assert not (repo / "test-model" / "regress").exists()
        # легитимный id со всеми разрешенными знаками по-прежнему проходит
        stage(repo, "scripts/x.py", "A = 1\n")
        ok = flowctl_cmd("regress", "--repo", str(repo),
                         "--change", "RC-1.2_x", "--json")
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert (repo / "test-model" / "regress" / "RC-1.2_x"
                / "regress-1.md").is_file()

    def test_regress_domain_without_tests_is_warn(self, tmp_path):
        """TC-J51-020: дифф затронул frontend/**, но каталога tests/web нет
        → вердикт WARN (не молчаливый PASS), exit 0, пометка «домен без
        тестов» в артефакте (review-001 #2)."""
        repo = tmp_path / "proj-fe"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"],
                       cwd=repo, check=True)
        write(repo, "README.md", "# r\n")
        commit_all(repo)
        stage(repo, "frontend/app.js", "console.log(1);\n")
        r = flowctl_cmd("regress", "--repo", str(repo),
                        "--change", "j51-demo", "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["domains"] == ["tests/web"]
        assert data["suites"] == []
        assert data["suites_skipped"] == ["tests/web"]
        assert data["verdict"] == "WARN"
        assert data["pytest_exit"] is None
        text = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "verdict: WARN" in text
        assert "домен(ы) без тестов: tests/web" in text
