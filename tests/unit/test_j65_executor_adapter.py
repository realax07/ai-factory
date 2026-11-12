# -*- coding: utf-8 -*-
"""J65.5 + J64.7: сменный исполнитель агентных стадий.

Решения Заказчика 2026-11-12: «pi + hermes + stub», «Префикс run»
(`run: <исполнитель>:<роль>`), «roles.json + манифест» (модель роли).

Трассировка:
  TC-J65-EXE-001  реестр исполнителей: pi, hermes, stub; неизвестный —
                  KeyError и ошибка манифеста с перечнем; hermes — manual
  TC-J65-EXE-002  новый исполнитель — один модуль: стадия `fake:dev`
                  проходит настоящие ворота раннера (prepare/run/finish,
                  сверка диффа, коммит, закрытие) без правок раннера и ядра
  TC-J65-EXE-003  модель/провайдер: из roles.json; стадия переопределяет;
                  нет ни там, ни там — STOP MODEL_UNRESOLVED; provider/model
                  только у агентной стадии
  TC-J65-EXE-004  roles.json ↔ settings.example.json паков (кроме auditor —
                  модель флагами CLI, pack_note)
  TC-J65-EXE-005  журнал запусков: start/end с исполнителем, делегацией,
                  workdir; исполнитель недоступен — STOP до ворот входа
  TC-J65-EXE-006  вотчдог: процесс исполнителя в проекте конвейера вне живой
                  резервации — BYPASS (с пометкой незакрытого start раннера);
                  в worktree живой резервации и вне проектов конвейера —
                  чисто; ручные исполнители пропускаются; delegate_watchdog
                  сводит находки в общий канал; на настоящем процессе:
                  исполнитель под интерпретатором (shebang `pi` на python)
                  виден через ps/cwd
  TC-J65-EXE-007  hermes: делегации из state.db; активные — list_active;
                  delegate_watchdog читает реестр через исполнитель
  TC-J65-EXE-008  эталонный прогон J65.10 на исполнителе `stub:` — те же
                  ворота, тот же результат
"""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import executors  # noqa: E402
import package_runner as pr  # noqa: E402
import test_package_runner as tpr  # noqa: E402
from test_package_runner import flow_gates_sandbox  # noqa: E402,F401  (autouse)


def test_registry_and_unknown_executor(tmp_path):
    """TC-J65-EXE-001."""
    assert {"pi", "hermes", "stub"} <= set(executors.names())
    assert executors.get("hermes").manual and not executors.get("pi").manual
    with pytest.raises(KeyError):
        executors.get("nosuch")
    with pytest.raises(KeyError):
        executors.get("../pi")
    repo = tpr.make_repo(tmp_path)
    plan = tpr.write_plan(repo, tpr.VALID.replace("run: pi:dev", "run: nosuch:dev"))
    with pytest.raises(pr.ManifestError, match="неизвестный исполнитель.*pi:"):
        pr.parse_manifest(plan)


class FakeExecutor(executors.Executor):
    """Исполнитель «одним файлом»: пишет файл в зону и отвечает."""
    name = "fake"

    def __init__(self, calls):
        self.calls = calls

    def command(self, launch):
        self.calls.append(launch)
        return ["fake-agent", "-p", launch.brief], dict(launch.env)


@pytest.fixture
def fake_executor(monkeypatch):
    calls: list = []
    mod = types.ModuleType("executors.fake")
    mod.EXECUTOR = FakeExecutor(calls)
    monkeypatch.setitem(sys.modules, "executors.fake", mod)
    return calls


@pytest.mark.real_flow_gates
def test_new_executor_is_one_module(tmp_path, monkeypatch, fake_executor):
    """TC-J65-EXE-002."""
    stage = tpr.DEV_STAGE.replace("run: pi:dev", "run: fake:dev")
    repo, plan = tpr.gated_plan(tmp_path, stage)
    wt, pi_calls = tpr.patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    (launch,) = fake_executor
    assert launch.role == "dev" and launch.zones == ["src"]
    assert (launch.provider, launch.model) == ("zai-glm", "glm-5.3")   # из roles.json
    assert pi_calls[0]["args"][0] == "fake-agent"
    assert tpr.branch_files(wt) == ["src/x.py"]
    assert tpr.registry_statuses() == [("dev", "closed")]
    gate = pr.state_load(pr.state_path_for(plan))["flow_gates"]["impl"]
    assert gate["executor"] == "fake" and gate["open"] is False


def test_model_resolution(tmp_path, monkeypatch, capsys):
    """TC-J65-EXE-003."""
    assert pr.role_model({"payload": "code-reviewer"}) == ("zai-glm", "glm-5.3-flash")
    assert pr.role_model({"payload": "dev", "model": "m2"}) == ("zai-glm", "m2")
    assert pr.role_model({"payload": "dev", "provider": "p2", "model": "m2"}) == ("p2", "m2")
    assert pr.role_model({"payload": "auditor"}) == ("kimi", "k3.1-pro")
    assert pr.role_model({"payload": "no-such-pack"}) is None
    repo = tpr.make_repo(tmp_path)
    bad = tpr.VALID.replace("run: check\n", "run: check\n").replace(
        "      run: gate:python3 scripts/flow_check.py\n",
        "      run: gate:python3 scripts/flow_check.py\n      model: x\n")
    with pytest.raises(pr.ManifestError, match="model"):
        pr.parse_manifest(tpr.write_plan(repo, bad))
    ok = tpr.VALID.replace("      task: сделать по спеке\n",
                           "      task: сделать по спеке\n      model: glm-9\n")
    m = pr.parse_manifest(tpr.write_plan(repo, ok))
    assert m["stages"][0]["model"] == "glm-9"
    # роль без модели в реестре и стадии — STOP до запуска
    calls: list = []
    tpr.patch_executors(monkeypatch, repo, calls)
    monkeypatch.setattr(pr, "role_model", lambda stage: None)
    assert pr.cmd_run(tpr.write_plan(repo), dry_run=False) == 2
    assert pr.MODEL_UNRESOLVED in capsys.readouterr().err and calls == []


def test_roles_match_pack_settings():
    """TC-J65-EXE-004."""
    roles = json.loads((FACTORY / "agents/roles.json").read_text(encoding="utf-8"))
    for r in roles["roles"]:
        if not r.get("pack"):
            continue
        assert r.get("provider") and r.get("model"), r["id"]
        st = json.loads((FACTORY / "skills/pm-factory/pi/role-packs" / r["pack"]
                         / "settings.example.json").read_text(encoding="utf-8"))
        if r["id"] == "auditor":
            assert "флагами CLI" in r.get("pack_note", "")
            continue
        assert (st["defaultProvider"], st["defaultModel"]) == (r["provider"], r["model"]), r["id"]


def test_runs_journal_and_unavailable(tmp_path, monkeypatch, capsys):
    """TC-J65-EXE-005."""
    repo, plan = tpr.gated_plan(tmp_path, tpr.DEV_STAGE)
    calls: list = []
    tpr.patch_executors(monkeypatch, repo, calls)
    assert pr.cmd_run(plan, dry_run=False) == 0
    journal = pr.flow_paths()[1].parent / pr.EXECUTOR_RUNS
    events = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["start", "end"]
    assert events[0]["executor"] == "pi" and events[0]["stage"] == "impl"
    assert events[0]["workdir"] == str(repo) and events[0]["delegation_id"]
    # stub без команды — STOP до ворот входа
    (tmp_path / "b").mkdir()
    repo2, plan2 = tpr.gated_plan(tmp_path / "b", tpr.DEV_STAGE.replace("pi:dev", "stub:dev"))
    entered: list = []
    monkeypatch.delenv("AF_EXECUTOR_STUB_CMD", raising=False)
    monkeypatch.setattr(pr, "gate_new", lambda *a: entered.append(a))
    assert pr.cmd_run(plan2, dry_run=False) == 2
    assert "EXECUTOR_UNAVAILABLE" in capsys.readouterr().err and entered == []


class ProcExecutor(executors.Executor):
    name = "procx"

    def __init__(self, runs):
        self.runs = runs

    def list_active(self):
        return self.runs


def test_watchdog_sees_bypass_of_any_executor(tmp_path, monkeypatch):
    """TC-J65-EXE-006."""
    import executor_watchdog as ew
    repo = tmp_path / "proj"
    wts = tmp_path / "proj-worktrees"
    wt_live, wt_gone, stray, alien = (wts / "live", wts / "gone", repo / "sub",
                                      tmp_path / "other-project")
    for d in (wt_live, wt_gone, stray, alien):
        d.mkdir(parents=True)
    reg = tmp_path / "active_sessions.json"
    reg.write_text(json.dumps({"sessions": [
        {"delegation_id": "d1", "status": "running", "repo": str(repo),
         "worktree": str(wt_live)},
        {"delegation_id": "d2", "status": "closed", "repo": str(repo),
         "worktree": str(wt_gone)}]}), encoding="utf-8")
    journal = tmp_path / "executor_runs.jsonl"
    journal.write_text(json.dumps({"event": "start", "executor": "procx",
                                   "workdir": str(wt_gone), "delegation_id": "d2"}) + "\n",
                       encoding="utf-8")
    runs = [executors.ActiveRun("procx", 11, str(wt_live / "sub"), "procx -p x"),
            executors.ActiveRun("procx", 12, str(wt_gone), "procx -p y"),
            executors.ActiveRun("procx", 13, str(stray), "procx -p z"),
            # чужой проект (интерактивный Pi вне конвейера) — не инцидент
            executors.ActiveRun("procx", 14, str(alien), "procx")]
    mod = types.ModuleType("executors.procx")
    mod.EXECUTOR = ProcExecutor(runs)
    monkeypatch.setitem(sys.modules, "executors.procx", mod)
    found = ew.scan(reg, journal, names=["procx", "hermes"])
    assert [f["delegation_id"] for f in found] == ["proc:procx:12", "proc:procx:13"]
    assert found[0]["runner_start"]["delegation_id"] == "d2"   # сбой раннера
    assert found[1]["runner_start"] is None                     # ручной запуск
    # delegate_watchdog сводит находки в общий канал (Hermes на машине нет)
    import delegate_watchdog as dw
    monkeypatch.setattr(dw, "executor_bypasses", lambda: found)
    monkeypatch.setattr(dw, "load_delegations", lambda: None)
    for name in ("INCIDENTS", "PM_NUDGE_STATE", "ACK_STATE", "PM_INSTRUCTION_STATE",
                 "FLOWCTL_STATE", "GATED_MAP_STATE"):
        monkeypatch.setattr(dw, name, tmp_path / "dw" / f"{name}.json")
    monkeypatch.setattr(dw, "_baseline_path", lambda: tmp_path / "dw" / "baseline.json")
    (tmp_path / "dw").mkdir()
    assert dw.main() == 1
    report = json.loads((tmp_path / "dw" / "INCIDENTS.json").read_text(encoding="utf-8"))
    assert [b["delegation_id"] for b in report["bypass"]] == ["proc:procx:12", "proc:procx:13"]


def test_hermes_executor_reads_registry(tmp_path, monkeypatch):
    """TC-J65-EXE-007."""
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE async_delegations (delegation_id TEXT, parent_session_id TEXT,"
                " state TEXT, delivery_state TEXT, dispatched_at REAL, completed_at REAL)")
    con.executemany("INSERT INTO async_delegations VALUES (?,?,?,?,?,?)", [
        ("a1", "s", "running", None, 1.0, None), ("a2", "s", "completed", "delivered", 1.0, 2.0)])
    con.commit()
    con.close()
    h = executors.get("hermes")
    assert [d["delegation_id"] for d in h.delegations(db)] == ["a1", "a2"]
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert [r.ref for r in h.list_active()] == ["a1"]
    import delegate_watchdog as dw
    monkeypatch.setattr(dw, "REGISTRY_DB", db)
    assert [d["state"] for d in dw.load_delegations()] == ["running", "completed"]


def test_reference_run_on_stub_executor(tmp_path):
    """TC-J65-EXE-008."""
    import test_j65_reference_run as ref
    repo = ref.make_project(tmp_path)
    plan = repo / ref.PLAN
    plan.write_text(plan.read_text(encoding="utf-8").replace("run: pi:", "run: stub:"),
                    encoding="utf-8")
    ref._git(repo, "commit", "-qam", "stub executor")
    env = ref.runner_env(tmp_path, AF_EXECUTOR_STUB_CMD=str(ref.FIXTURE / "bin" / "pi"))
    proc = ref.run_runner(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = ref.runner_state(repo)
    assert {k: v["status"] for k, v in state["stages"].items()}["dev-1.2-review"] == "done"
    assert all(g.get("executor") == "stub" for g in state["flow_gates"].values())
    assert ref.registry(env).count(("dev", "closed")) == 2


def test_real_interpreted_process_is_visible(tmp_path, monkeypatch):
    """TC-J65-EXE-006: настоящий процесс `pi` под интерпретатором (как Pi на
    node или stub на python) — виден list_active, его cwd — каталог запуска;
    вне резервации проекта конвейера — BYPASS."""
    import os
    import subprocess
    import time
    import executor_watchdog as ew
    assert executors.runs_binary("node /usr/lib/node_modules/pi/bin/pi -p x", "pi")
    assert executors.runs_binary("/usr/bin/env -S node --x /opt/pi", "pi")
    assert not executors.runs_binary("vim pi", "pi")
    assert not executors.runs_binary("python3 notpi.py", "pi")
    # ревью review-002: код вместо файла — не запуск; флаги со значением и sh -c
    for cmd in ("python3 -m pi", "python3 -c pi", "node -e pi", 'bash -c "vim pi"',
                "node --inspect pi.js"):
        assert not executors.runs_binary(cmd, "pi"), cmd
    for cmd in ("node --require x /opt/pi -p b", "python -X dev /opt/pi", "env -u FOO pi",
                'sh -c "pi -p x"', "node --inspect /opt/pi",
                # ревью review-003: флаги по интерпретатору, звенья sh -c
                "python3 -u /x/pi", "bash -e /x/pi", 'bash -c "cd /x && pi -p y"'):
        assert executors.runs_binary(cmd, "pi"), cmd
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "pi"
    # процесс блокируется на stdin (без пауз в тестах — спека qa-pipeline)
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.read()\n",
                      encoding="utf-8")
    script.chmod(0o755)
    repo = tmp_path / "proj"
    wt = tmp_path / "proj-worktrees" / "x"
    wt.mkdir(parents=True)
    repo.mkdir(exist_ok=True)   # J41-фикстура conftest уже создала proj
    proc = subprocess.Popen([str(script), "-p", "brief"], cwd=wt,
                            stdin=subprocess.PIPE)
    try:
        found = []
        deadline = time.monotonic() + 20
        while not found and time.monotonic() < deadline:   # опрос ps — без пауз
            found = [r for r in executors.get("pi").list_active() if r.pid == proc.pid]
        assert found and found[0].cwd == os.path.realpath(wt), found
        reg = tmp_path / "reg.json"
        reg.write_text(json.dumps({"sessions": [
            {"delegation_id": "old", "status": "released", "repo": str(repo),
             "worktree": str(wt)}]}), encoding="utf-8")
        hits = [f for f in ew.scan(reg, None, names=["pi"]) if f["pid"] == proc.pid]
        assert hits and hits[0]["delegation_id"] == f"proc:pi:{proc.pid}"
        reg.write_text(json.dumps({"sessions": [
            {"delegation_id": "live", "status": "running", "repo": str(repo),
             "worktree": str(wt)}]}), encoding="utf-8")
        assert not [f for f in ew.scan(reg, None, names=["pi"]) if f["pid"] == proc.pid]
    finally:
        proc.kill()
        proc.communicate()


def test_watchdog_paths_follow_runner_env(tmp_path, monkeypatch):
    """TC-J65-EXE-006: реестр и журнал вотчдога — те же, что у раннера
    (PIPELINE_FLOW_REGISTRY / PIPELINE_FLOW_STATE); сломанный исполнитель не
    роняет delegate_watchdog."""
    import executor_watchdog as ew
    import delegate_watchdog as dw
    monkeypatch.setenv("PIPELINE_FLOW_REGISTRY", str(tmp_path / "r.json"))
    monkeypatch.setenv("PIPELINE_FLOW_STATE", str(tmp_path / "s" / "flowctl_state.json"))
    assert ew.default_paths() == (tmp_path / "r.json", tmp_path / "s" / ew.RUNS_JOURNAL)
    assert pr.flow_paths()[1].parent / pr.EXECUTOR_RUNS == ew.default_paths()[1]
    monkeypatch.delenv("PIPELINE_FLOW_STATE")       # только реестр — журнал рядом
    assert pr.flow_paths()[1].parent / pr.EXECUTOR_RUNS == ew.default_paths()[1]

    def boom(*a, **k):
        raise RuntimeError("broken executor")
    monkeypatch.setattr(ew, "scan", boom)
    assert dw.executor_bypasses() == []


def test_watchdog_finds_main_clone_of_runner_worktree(tmp_path, monkeypatch):
    """TC-J65-EXE-006 (ревью review-002): раннер пишет в реестр repo = worktree
    пакета — основной клон и соседние worktree все равно проекты конвейера
    (git --git-common-dir): ручной запуск там — BYPASS."""
    import os
    import subprocess
    import executor_watchdog as ew
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    main = tmp_path / "proj"
    main.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", str(main)], check=True, env=env)
    subprocess.run(["git", "-C", str(main), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "i"], check=True, env=env)
    wt = tmp_path / "proj-worktrees" / "pkg"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(wt)],
                   check=True, env=env)
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"sessions": [
        {"delegation_id": "d", "status": "closed", "repo": str(wt), "worktree": str(wt)}]}),
        encoding="utf-8")
    mod = types.ModuleType("executors.procx")
    mod.EXECUTOR = ProcExecutor([executors.ActiveRun("procx", 21, str(main), "procx")])
    monkeypatch.setitem(sys.modules, "executors.procx", mod)
    found = ew.scan(reg, None, names=["procx"])
    assert [f["delegation_id"] for f in found] == ["proc:procx:21"]
