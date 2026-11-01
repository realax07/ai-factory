# -*- coding: utf-8 -*-
"""Тесты раннера v0 конвейера пакетов (слои 1–2 диспетчера, J28-развитие).

Скрипт: scripts/package_runner.py; формат манифеста:
docs/guides/pipeline-manifest.md. Pi в тестах НЕ вызывается — subprocess
подменяется на уровне точек run_pi/run_shell/ensure_worktree (monkeypatch,
сам скрипт строит команду/env/brief, мок проверяет).

Кейсы:
  (а) парсер манифеста: валидный / кривой (нет секции, пустые поля,
      неизвестный вид run, pi без zones, дубль id);
  (б) depends вне порядка → WARNING, не STOP;
  (в) state/resume: выполненные stage пропускаются, повтор не повторяет pi;
  (г) STOP-семантика hermes-шага: exit 0, «ЖДУ ПМ», stage не завершен,
      resume после ПМ докатывает;
  (д) STOP gate-fail: exit 2, диагностика, следующий stage не исполняется,
      повтор (без правки) снова STOP — ретрая нет; pi-fail; таймаут;
  (е) e2e на реальном worktree (session_worktree.sh): role-agents.md →
      AGENTS.md, PI_ZONE_WRITE из stage.zones, бриф несет inputs/task.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import package_runner as pr  # noqa: E402

VALID = """\
# PLAN-demo: тестовый пакет

**Флоу: 4**. Описание плана (текст вне YAML-блока раннер игнорирует).

```yaml
pipeline:
  package: demo-pkg
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [backend/**, tests/**]
      inputs: [openspec/changes/demo/spec.md]
      task: сделать по спеке
    - id: check
      run: gate:python3 scripts/flow_check.py
    - id: review-plan
      run: hermes:pm
```
"""


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # autouse-фикстура J41 уже создала каталог
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"],
                   check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"],
                   check=True)
    (repo / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"],
                   check=True)
    return repo


def write_plan(repo: Path, text: str = VALID,
               name: str = "PLAN-demo.md") -> Path:
    plan = repo / name
    plan.write_text(text, encoding="utf-8")
    return plan


def write_tmp_plan(text: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write(text)
        return Path(f.name)


def fake_pi(calls: list, rc: int = 0):
    def _run_pi(args, cwd, env, timeout):
        calls.append({"args": args, "cwd": cwd, "env": env})
        return rc, "pi stdout ok", ""
    return _run_pi


def patch_executors(monkeypatch, repo: Path, pi_calls: list,
                    shell_fn=None, worktree: Path | None = None):
    """Подмена pi/shell/worktree; pi пишет вызовы в pi_calls (pi в тестах
    не вызывается)."""
    def fake_pi(args, cwd, env, timeout):
        pi_calls.append({"args": args, "cwd": cwd, "env": env})
        return 0, "pi stdout ok", ""
    monkeypatch.setattr(pr, "run_pi", fake_pi)
    if shell_fn is not None:
        monkeypatch.setattr(pr, "run_shell", shell_fn)
    else:
        monkeypatch.setattr(pr, "run_shell",
                            lambda cmd, cwd, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree",
                        lambda repo_, sid, br: worktree or repo_)


# ------------------------------------------------------- (а) парсер


def test_a1_valid_manifest_parsed():
    m = pr.parse_manifest(write_tmp_plan(VALID))
    assert m["package"] == "demo-pkg"
    assert m["flow"] == 4
    kinds = [(s["kind"], s["payload"]) for s in m["stages"]]
    assert kinds == [("pi", "dev"), ("gate", "python3 scripts/flow_check.py"),
                     ("hermes", "pm")]
    assert m["stages"][0]["zones"] == ["backend/**", "tests/**"]
    assert m["stages"][0]["inputs"] == ["openspec/changes/demo/spec.md"]


def test_a2_no_pipeline_section():
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan("# PLAN-x\n\n```yaml\nother: 1\n```\n"))


@pytest.mark.parametrize("snippet", [
    # package отсутствует
    "pipeline:\n  flow: 4\n  stages:\n    - id: a\n      run: gate:true\n",
    # stages пустой
    "pipeline:\n  package: p\n  flow: 4\n  stages: []\n",
    # id отсутствует
    "pipeline:\n  package: p\n  flow: 4\n  stages:\n    - run: gate:true\n",
    # неизвестный вид run
    ("pipeline:\n  package: p\n  flow: 4\n  stages:\n"
     "    - id: a\n      run: bash:ls\n"),
    # pi без zones
    ("pipeline:\n  package: p\n  flow: 4\n  stages:\n"
     "    - id: a\n      run: pi:dev\n"),
    # дубль id
    ("pipeline:\n  package: p\n  flow: 4\n  stages:\n"
     "    - id: a\n      run: gate:true\n"
     "    - id: a\n      run: gate:true\n"),
])
def test_a3_crooked_manifests_rejected(snippet):
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(
            write_tmp_plan("# PLAN-x\n\n```yaml\n" + snippet + "```\n"))


def test_a4_depends_out_of_order_warns_not_stops(tmp_path, monkeypatch,
                                                 capsys):
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n"
            "  stages:\n"
            "    - id: a\n      run: gate:true\n      depends: [b]\n"
            "    - id: b\n      run: gate:true\n```\n")
    m = pr.parse_manifest(write_tmp_plan(text))
    warns = pr.sequence_warnings(m["stages"])
    assert len(warns) == 1 and "b" in warns[0]
    # cmd_run с этим манифестом — оба gate ok, exit 0 (WARNING не STOP)
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")
    calls: list = []

    def fake_shell(cmd, cwd, timeout):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(pr, "run_shell", fake_shell)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(calls) == 2
    assert "RUNNER-WARNING" in capsys.readouterr().err


# --------------------------------------------------- (в) state/resume


def test_v1_resume_skips_done_stages(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    # первый прогон: pi → gate ok → hermes (стоп-точка ПМ), exit 0
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(calls) == 1  # только pi:dev
    state = json.loads((repo / "PLAN-demo.md.runner-state.json")
                       .read_text("utf-8"))
    assert state["stages"]["impl"]["status"] == "done"
    assert state["stages"]["check"]["status"] == "done"
    assert state["stages"]["review-plan"]["status"] == "waited"

    # resume после ПМ-действий: waited-шаг пропускается, pi НЕ повторяется,
    # пакет докатан
    def must_not_call(*a, **k):
        raise AssertionError("pi не должен вызываться на resume")
    monkeypatch.setattr(pr, "run_pi", must_not_call)
    assert pr.cmd_run(plan, dry_run=False) == 0
    out = capsys.readouterr().out
    assert out.count("уже выполнен") == 3
    assert "докатан" in out


# ------------------------------------------- (г) STOP-семантика hermes


def test_g1_hermes_step_waits_pm_exit0(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    rc = pr.cmd_run(plan, dry_run=False)
    assert rc == 0  # НЕ ошибка: ожидание ручного диспатча
    out = capsys.readouterr().out
    assert "ЖДУ ПМ: stage review-plan, роль pm" in out
    assert "state:" in out
    state = json.loads((repo / "PLAN-demo.md.runner-state.json")
                       .read_text("utf-8"))
    assert state["stages"]["review-plan"]["status"] == "waited"
    # журнал плана содержит стоп-точку
    text = plan.read_text("utf-8")
    assert "## Журнал раннера" in text
    assert "hermes:pm | ЖДУ ПМ" in text
    assert len(calls) == 1


# ------------------------------------------------- (д) STOP gate-fail


def test_d1_gate_fail_stop_exit2_no_retry(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    pi_calls: list = []
    gate_calls: list = []

    def failing_gate(cmd, cwd, timeout):
        gate_calls.append(cmd)
        return 1, "out-line", "gate failed: details"

    patch_executors(monkeypatch, repo, pi_calls=pi_calls,
                    shell_fn=failing_gate)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "STOP" in err and "gate exit 1" in err
    assert "gate failed: details" in err  # хвост stderr в диагностике
    assert len(gate_calls) == 1
    state = json.loads((repo / "PLAN-demo.md.runner-state.json")
                       .read_text("utf-8"))
    assert state["stages"]["check"]["status"] == "stopped"
    # hermes-шаг не достигнут
    assert "review-plan" not in state["stages"]
    assert "STOP" in plan.read_text("utf-8")

    # повтор без правки: stage переисполняется заново (не skip) и снова
    # STOP — успешное «ретраится до зеленого» отсутствует по определению
    capsys.readouterr()
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert len(gate_calls) == 2
    assert len(pi_calls) == 1  # pi не повторялся (status done)


def test_d2_pi_fail_stop_exit2(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    plan = write_plan(repo)

    def failing_pi(args, cwd, env, timeout):
        return 3, "", "pi crashed"
    monkeypatch.setattr(pr, "run_pi", failing_pi)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "pi exit 3" in err
    state = json.loads((repo / "PLAN-demo.md.runner-state.json")
                       .read_text("utf-8"))
    assert state["stages"]["impl"]["status"] == "stopped"


def test_d3_timeout_stop_exit2(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    plan = write_plan(repo)

    def slow_pi(args, cwd, env, timeout):
        raise subprocess.TimeoutExpired(cmd="pi", timeout=timeout)
    monkeypatch.setattr(pr, "run_pi", slow_pi)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2


# ------------------------------------------------------------- (е) e2e


def test_e1_e2e_real_worktree_brief_env_agents(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    # ветка пакета существует заранее → session_worktree.sh подключит ее
    # (без remote origin/main, как в свежих fixture-репо)
    subprocess.run(["git", "-C", str(repo), "branch",
                    "pipeline/demo-pkg"], check=True)
    plan = write_plan(repo)
    calls: list = []
    shell_cmds: list = []

    def shell_probe(cmd, cwd, timeout):
        shell_cmds.append((cmd, cwd))
        return 0, "", ""

    monkeypatch.setattr(pr, "run_pi", fake_pi(calls))
    monkeypatch.setattr(pr, "run_shell", shell_probe)
    assert pr.cmd_run(plan, dry_run=False) == 0
    # worktree реальный, создан session_worktree.sh (SESSION.md — маркер)
    wt = Path(pr.state_load(pr.state_path_for(plan))["worktree"])
    assert wt.is_dir() and (wt / "SESSION.md").is_file()
    assert wt != repo
    # role-agents.md пака dev скопирован как AGENTS.md
    pack = (FACTORY / "skills/pm-factory/pi/role-packs/dev/role-agents.md"
            ).read_text("utf-8")
    assert (wt / "AGENTS.md").read_text("utf-8") == pack
    # вызов pi: провайдер/модель/zone-guard/no-session, зоны из stage
    call = calls[0]
    args = call["args"]
    assert args[0] == "pi"
    assert "--no-session" in args
    assert args[args.index("--provider") + 1] == "zai-glm"
    assert args[args.index("--model") + 1] == "glm-5.3"
    assert args[args.index("-e") + 1].endswith("zone-guard.ts")
    assert call["env"]["PI_ZONE_WRITE"] == "backend/**:tests/**"
    assert call["cwd"] == wt
    brief = args[args.index("-p") + 1]
    assert "openspec/changes/demo/spec.md" in brief  # inputs в брифе
    assert "сделать по спеке" in brief               # task в брифе
    assert str(wt) == str(shell_cmds[0][1])          # gate в worktree
