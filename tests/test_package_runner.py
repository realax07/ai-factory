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
      AGENTS.md, PI_ZONE_WRITE из stage.zones, бриф несет inputs/task;
  (ж) фиксы по ревью pi:dev 2b76c39: STOP-контракт (битый state / PLAN вне
      git / кривой PIPELINE_TIMEOUT → RUNNER-STOP exit 2), хвост частичного
      вывода при таймауте, диагностика переживает падение journal,
      валидация pi-роли / зон с ':' / flow 1..5, хэш-суффикс сессии,
      подсказка очистки только после успеха.
  (з) интеграционные дефекты пилота BUG-026 на ekotov-wiki:
      Д1 worktree от текущего HEAD репо (не origin/main — ветка ПМ с
      PLAN/карточками в сцене); Д2 gate без env стенда (EKOTOV_WIKI_*
      срезаются, скоуп тестов — ответственность gate-команды); Д3 AGENTS.md
      проекта не перезаписывается (роль → AGENTS.pi.md, «читай вместе с
      AGENTS.md»); Д4 хвост stdout/stderr успешных стадий — в state
      (≤50 строк) и лог <план>.runner.log; Д5 путь state печатается в
      начале и при STOP, чужой state (package/plan) — RUNNER-STOP.
"""
from __future__ import annotations

import hashlib
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
    """TC-PR-001: валидный манифест парсится (package/flow/stages, kinds)."""
    m = pr.parse_manifest(write_tmp_plan(VALID))
    assert m["package"] == "demo-pkg"
    assert m["flow"] == 4
    kinds = [(s["kind"], s["payload"]) for s in m["stages"]]
    assert kinds == [("pi", "dev"), ("gate", "python3 scripts/flow_check.py"),
                     ("hermes", "pm")]
    assert m["stages"][0]["zones"] == ["backend/**", "tests/**"]
    assert m["stages"][0]["inputs"] == ["openspec/changes/demo/spec.md"]


def test_a2_no_pipeline_section():
    """TC-PR-002: PLAN без секции pipeline: — ManifestError."""
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
    """TC-PR-003: кривые манифесты (6 вариантов) — ManifestError."""
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(
            write_tmp_plan("# PLAN-x\n\n```yaml\n" + snippet + "```\n"))


def test_a4_depends_out_of_order_warns_not_stops(tmp_path, monkeypatch,
                                                 capsys):
    """TC-PR-004: depends вне порядка — WARNING, прогон продолжается."""
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
    """TC-PR-005: state/resume — done/waited пропускаются, pi не повторяется."""
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
    """TC-PR-006: hermes-шаг — «ЖДУ ПМ», exit 0, статус waited, журнал."""
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
    """TC-PR-007: gate-fail — STOP exit 2, диагностика, повтор без правки снова STOP."""
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
    """TC-PR-008: ненулевой exit pi — STOP exit 2, stage stopped."""
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
    """TC-PR-009: таймаут pi — STOP exit 2."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)

    def slow_pi(args, cwd, env, timeout):
        raise subprocess.TimeoutExpired(cmd="pi", timeout=timeout)
    monkeypatch.setattr(pr, "run_pi", slow_pi)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2


# ------------------------------------------------------------- (е) e2e


# ------------------------------------------- (ж) фиксы по ревью pi:dev


@pytest.mark.parametrize("broken", ["garbage{{not-json", '{"schema_version": "other/1"}'])
def test_j1_broken_state_stop_exit2(tmp_path, monkeypatch, capsys, broken):
    """TC-PR-012: битый runner-state (JSON/чужая схема) — RUNNER-STOP exit 2, без traceback (F1)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    (repo / "PLAN-demo.md.runner-state.json").write_text(broken, "utf-8")
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "RUNNER-STOP:" in err and "runner-state" in err
    assert calls == []  # до исполнения дело не дошло


def test_j1b_plan_outside_git_stop_exit2(tmp_path, capsys):
    """TC-PR-013: PLAN вне git-репозитория — RUNNER-STOP exit 2, без traceback (F1)."""
    plan = write_tmp_plan(VALID)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "RUNNER-STOP:" in err
    assert "git" in err.lower()


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "12.5"])
def test_j2_bad_pipeline_timeout_stop(tmp_path, monkeypatch, capsys, bad):
    """TC-PR-014: кривой PIPELINE_TIMEOUT (не целое/<=0) — RUNNER-STOP exit 2 (F2)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    monkeypatch.setenv("PIPELINE_TIMEOUT", bad)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "RUNNER-STOP:" in err and "PIPELINE_TIMEOUT" in err
    assert calls == []


def test_j2b_valid_pipeline_timeout_runs(tmp_path, monkeypatch, capsys):
    """TC-PR-014b: валидный PIPELINE_TIMEOUT исполняется (не STOP)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                            "  package: p\n  flow: 4\n  stages:\n"
                            "    - id: a\n      run: gate:true\n```\n")
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    monkeypatch.setenv("PIPELINE_TIMEOUT", "120")
    assert pr.cmd_run(plan, dry_run=False) == 0


def test_j3_timeout_keeps_partial_output(tmp_path, monkeypatch, capsys):
    """TC-PR-015: таймаут pi — хвост частичного stdout/stderr в диагностике STOP (F6)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)

    def slow_pi(args, cwd, env, timeout):
        raise subprocess.TimeoutExpired(cmd="pi", timeout=timeout,
                                        output=b"PARTIAL-OUT line1\nline2\n",
                                        stderr=b"partial-err trace\n")
    monkeypatch.setattr(pr, "run_pi", slow_pi)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "таймаут pi" in err
    assert "PARTIAL-OUT line1" in err   # хвост stdout не выброшен
    assert "partial-err trace" in err   # хвост stderr не выброшен


def test_j3b_timeout_gate_stage_keeps_output(tmp_path, monkeypatch, capsys):
    """TC-PR-015b: таймаут gate stage — частичный вывод в диагностике (F6)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                            "  package: p\n  flow: 4\n  stages:\n"
                            "    - id: a\n      run: pi:dev\n"
                            "      zones: [src/**]\n"
                            "      gate: python3 check.py\n```\n")

    def slow_gate(cmd, cwd, timeout):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout,
                                        output=b"GATE-PARTIAL\n")
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "run_shell", slow_gate)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "таймаут gate stage" in err and "GATE-PARTIAL" in err


def test_j4_stop_survives_journal_failure(tmp_path, monkeypatch, capsys):
    """TC-PR-016: падение state/journal при STOP — диагностика напечатана, exit 2, без traceback (F8)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                            "  package: p\n  flow: 4\n  stages:\n"
                            "    - id: a\n      run: gate:true\n```\n",
                      name="PLAN-x.md")

    def failing_gate(cmd, cwd, timeout):
        return 1, "out", "gate failed: details"

    def broken_journal(plan_path, line):
        raise OSError("план удален/readonly")
    monkeypatch.setattr(pr, "run_shell", failing_gate)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    monkeypatch.setattr(pr, "journal_append", broken_journal)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "gate exit 1" in err and "gate failed: details" in err


@pytest.mark.parametrize("payload", ["../etc", "/abs", "a b", "a/b", "role;id"])
def test_j5_pi_role_payload_validation(payload):
    """TC-PR-017: pi-роль — плоский [A-Za-z0-9._-]+: traversal/пробелы/слэши — ManifestError (F11)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n"
            "  stages:\n"
            f"    - id: a\n      run: pi:{payload}\n"
            "      zones: [src/**]\n```\n")
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(text))


def test_j5b_gate_payload_not_restricted():
    """TC-PR-017b: gate-payload не ограничен роль-регэкспом (команды с пробелами/путями ок)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n"
            "  stages:\n"
            "    - id: a\n      run: gate:python3 scripts/x.py --all\n```\n")
    m = pr.parse_manifest(write_tmp_plan(text))
    assert m["stages"][0]["payload"] == "python3 scripts/x.py --all"


def test_j6_package_hash_suffix_no_collision(tmp_path, monkeypatch):
    """TC-PR-018: «a b» и «a/b» — разные session/branch (суффикс sha1[:8]); демо-пакет ветки e2e стабильна (F12)."""
    seen: list = []

    def capture_wt(repo_, sid, br):
        seen.append((sid, br))
        return repo_
    monkeypatch.setattr(pr, "ensure_worktree", capture_wt)
    monkeypatch.setattr(pr, "run_shell", lambda cmd, cwd, t: (0, "", ""))
    for pkg, sub_name in (("a b", "a_b"), ("a/b", "a_slash_b")):
        sub = tmp_path / sub_name
        sub.mkdir(exist_ok=True)
        repo = make_repo(sub)
        plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                                f"  package: {pkg}\n  flow: 4\n  stages:\n"
                                "    - id: a\n      run: gate:true\n```\n",
                          name="PLAN-x.md")
        assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(seen) == 2
    (sid1, br1), (sid2, br2) = seen
    assert sid1 != sid2 and br1 != br2          # коллизии нет
    for sid, br in seen:                        # суффикс-хэш на месте
        assert len(sid.rsplit("-", 1)[1]) == 8
        assert br.rsplit("-", 1)[1] == sid.rsplit("-", 1)[1]


@pytest.mark.parametrize("flow", [0, 6, 99, -1])
def test_j7_flow_out_of_range(flow):
    """TC-PR-019: flow вне 1..5 — ManifestError (F17)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n"
            f"  flow: {flow}\n  stages:\n"
            "    - id: a\n      run: gate:true\n```\n")
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(text))


@pytest.mark.parametrize("flow", [1, 5])
def test_j7b_flow_in_range(flow):
    """TC-PR-019b: flow 1 и 5 — граница принимается (F17)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n"
            f"  flow: {flow}\n  stages:\n"
            "    - id: a\n      run: gate:true\n```\n")
    assert pr.parse_manifest(write_tmp_plan(text))["flow"] == flow


def test_j8_cleanup_hint_after_success_only(tmp_path, monkeypatch, capsys):
    """TC-PR-020: после «докатан» — готовая команда remove; при STOP и hermes-стопе подсказки нет (F15)."""
    good = "# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n" \
           "  stages:\n    - id: a\n      run: gate:true\n```\n"
    repo = make_repo(tmp_path)
    plan = write_plan(repo, good, name="PLAN-x.md")
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    assert pr.cmd_run(plan, dry_run=False) == 0
    out = capsys.readouterr().out
    assert "session_worktree.sh remove" in out
    assert "pipeline-p-" in out  # session-id с хэш-суффиксом в команде

    # STOP: worktree сохраняется, подсказки очистки нет (свежий репо —
    # без resume-состояния первого сценария)
    def failing_gate(cmd, cwd, timeout):
        return 1, "", "boom"
    sub = tmp_path / "stop-proj"
    sub.mkdir(exist_ok=True)
    repo2 = make_repo(sub)
    write_plan(repo2, good, name="PLAN-x.md")
    capsys.readouterr()
    monkeypatch.setattr(pr, "run_shell", failing_gate)
    assert pr.cmd_run(repo2 / "PLAN-x.md", dry_run=False) == 2
    captured = capsys.readouterr()
    assert "STOP" in captured.err
    assert "session_worktree.sh remove" not in captured.out

    # hermes-стоп-точка: тоже без подсказки (пакет не докатан)
    hermes = "# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n" \
             "  stages:\n    - id: a\n      run: hermes:pm\n```\n"
    capsys.readouterr()
    plan2 = write_plan(repo, hermes, name="PLAN-h.md")
    assert pr.cmd_run(plan2, dry_run=False) == 0
    captured = capsys.readouterr()
    assert "ЖДУ ПМ" in captured.out
    assert "session_worktree.sh remove" not in captured.out


@pytest.mark.parametrize("zone", ["backend:x", "src/**:y"])
def test_j9_zone_with_colon_rejected(zone):
    """TC-PR-021: зона с ':' — ManifestError (PI_ZONE_WRITE разделяется по ':') (F14)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n"
            "  stages:\n"
            f"    - id: a\n      run: pi:dev\n      zones: [src/**, {zone}]\n"
            "```\n")
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(text))


def test_e1_e2e_real_worktree_brief_env_agents(tmp_path, monkeypatch):
    """TC-PR-010: e2e на session_worktree.sh — AGENTS.md, PI_ZONE_WRITE, бриф."""
    repo = make_repo(tmp_path)
    # ветка пакета существует заранее → session_worktree.sh подключит ее
    # (без remote origin/main, как в свежих fixture-репо); имя ветки
    # строит сам раннер: pipeline/<санитиз>, суффикс sha1(package)[:8]
    sane = pr._UNSAFE_RE.sub("-", "demo-pkg").strip("-")
    suffix = hashlib.sha1(b"demo-pkg").hexdigest()[:8]
    branch = f"pipeline/{sane}-{suffix}"
    subprocess.run(["git", "-C", str(repo), "branch", branch], check=True)
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
    # J61: PI_ZONE_WRITE — нормализованные зоны (префикс-форма guard'а),
    # не glob-форма манифеста
    assert call["env"]["PI_ZONE_WRITE"] == "backend:tests"
    assert call["cwd"] == wt
    brief = args[args.index("-p") + 1]
    assert "openspec/changes/demo/spec.md" in brief  # inputs в брифе
    assert "сделать по спеке" in brief               # task в брифе
    assert str(wt) == str(shell_cmds[0][1])          # gate в worktree


def test_a5_quoted_scalars_block_list():
    """TC-PR-011: кавычкованные скаляры в блочном списке (паритет с YAML)."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 2\n"
            "  stages:\n"
            "    - id: a\n      run: pi:dev\n      zones: [src/**]\n"
            "      inputs:\n"
            "        - docs/x.md\n"
            "        - 'path with: colon'\n"
            "      task: \"сделать: быстро\"\n```\n")
    m = pr.parse_manifest(write_tmp_plan(text))
    st = m["stages"][0]
    assert st["inputs"] == ["docs/x.md", "path with: colon"]
    assert st["task"] == "сделать: быстро"


# ------------------------- (з) интеграционные дефекты пилота BUG-026


def test_z1_worktree_from_head_not_origin_main(tmp_path):
    """TC-PR-022 (Д1): worktree создается от текущего HEAD репо — коммит
    ветки ПМ (PLAN/карточки бага) присутствует в сцене, а не теряется с
    origin/main (fixture-репо без origin: старый дефолт вообще не создал бы
    worktree)."""
    repo = make_repo(tmp_path)
    (repo / "PLAN-BUG-026.md").write_text("план ПМ", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "pm branch"],
                   check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    sane = pr._UNSAFE_RE.sub("-", "d1").strip("-")
    suffix = hashlib.sha1(b"d1").hexdigest()[:8]
    sid, branch = f"pipeline-{sane}-{suffix}", f"pipeline/{sane}-{suffix}"
    wt = pr.ensure_worktree(repo, sid, branch)
    try:
        assert (wt / "SESSION.md").is_file()
        # план ПМ (коммит HEAD) есть в сцене worktree
        assert (wt / "PLAN-BUG-026.md").read_text("utf-8") == "план ПМ"
        wt_head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
        assert wt_head == head  # база — HEAD, не origin/main
    finally:
        subprocess.run(["bash", str(pr.WORKTREE_SCRIPT), "remove",
                        str(repo), sid], capture_output=True)


def test_z2_gate_env_without_stand_vars(tmp_path, monkeypatch):
    """TC-PR-023 (Д2): gate-команда наследует env без стенда (E6):
    EKOTOV_WIKI_BASE_URL/EKOTOV_WIKI_DB_PATH срезаются (эквивалент env -u) —
    pytest коллекция не цепляет tests/web; прочие переменные проходят."""
    repo = make_repo(tmp_path)
    monkeypatch.setenv("EKOTOV_WIKI_BASE_URL", "http://stand:8080")
    monkeypatch.setenv("EKOTOV_WIKI_DB_PATH", "/tmp/stand.db")
    monkeypatch.setenv("PIPELINE_TIMEOUT", "77")
    rc, out, err = pr.run_shell(
        'echo "BASE=[$EKOTOV_WIKI_BASE_URL] DB=[$EKOTOV_WIKI_DB_PATH] '
        'T=[$PIPELINE_TIMEOUT]"', repo, 30)
    assert rc == 0
    assert "BASE=[]" in out and "DB=[]" in out   # env стенда срезан
    assert "T=[77]" in out                        # остальной env проходит
    env = pr.gate_env()
    assert "EKOTOV_WIKI_BASE_URL" not in env
    assert "EKOTOV_WIKI_DB_PATH" not in env
    assert env.get("PIPELINE_TIMEOUT") == "77"


def test_z3_existing_agents_md_not_overwritten(tmp_path, monkeypatch):
    """TC-PR-024 (Д3): AGENTS.md проекта не перезаписывается — роль-пак
    кладется рядом как AGENTS.pi.md с пометкой «читай вместе с AGENTS.md»,
    бриф упоминает AGENTS.pi.md."""
    repo = make_repo(tmp_path)
    (repo / "AGENTS.md").write_text("ПРАВИЛА ПРОЕКТА v1", encoding="utf-8")
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls, worktree=repo)
    assert pr.cmd_run(plan, dry_run=False) == 0
    # проектные правила не тронуты
    assert (repo / "AGENTS.md").read_text("utf-8") == "ПРАВИЛА ПРОЕКТА v1"
    pack = (FACTORY / "skills/pm-factory/pi/role-packs/dev/role-agents.md"
            ).read_text("utf-8")
    side = (repo / "AGENTS.pi.md").read_text("utf-8")
    assert side.startswith(pack)               # роль — целиком
    assert "Читай вместе с AGENTS.md" in side  # пометка для Pi
    brief = calls[0]["args"][calls[0]["args"].index("-p") + 1]
    assert "AGENTS.pi.md" in brief and "AGENTS.md" in brief


def test_z3b_no_agents_md_role_landed_as_agents_md(tmp_path, monkeypatch):
    """TC-PR-024b (Д3): AGENTS.md в worktree нет — роль кладется как
    AGENTS.md (прежнее поведение), AGENTS.pi.md не создается."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls, worktree=repo)
    assert pr.cmd_run(plan, dry_run=False) == 0
    pack = (FACTORY / "skills/pm-factory/pi/role-packs/dev/role-agents.md"
            ).read_text("utf-8")
    assert (repo / "AGENTS.md").read_text("utf-8") == pack
    assert not (repo / "AGENTS.pi.md").exists()
    brief = calls[0]["args"][calls[0]["args"].index("-p") + 1]
    assert "в AGENTS.md" in brief and "AGENTS.pi.md" not in brief


def test_z4_success_output_in_state_and_log(tmp_path, monkeypatch):
    """TC-PR-025 (Д4): stdout/stderr успешных стадий не теряются — хвост
    в state (stdout_tail/stderr_tail) и в лог <план>.runner.log; pi и gate
    обе стадии сохраняют вывод."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []

    def loud_gate(cmd, cwd, timeout):
        return 0, "\n".join(f"out{i}" for i in range(60)), "GATE-ERR detail"

    patch_executors(monkeypatch, repo, pi_calls=calls, shell_fn=loud_gate,
                    worktree=repo)
    assert pr.cmd_run(plan, dry_run=False) == 0
    state = json.loads((repo / "PLAN-demo.md.runner-state.json")
                       .read_text("utf-8"))
    # pi-стадия: хвост stdout сохранен при успехе
    assert state["stages"]["impl"]["stdout_tail"] == "pi stdout ok"
    # gate-стадия: хвост в state, ограничен 50 строками (верхние отброшены)
    gate_tail = state["stages"]["check"]["stdout_tail"].splitlines()
    assert len(gate_tail) == 50
    assert gate_tail[-1] == "out59" and "out0" not in gate_tail
    assert state["stages"]["check"]["stderr_tail"] == "GATE-ERR detail"
    # лог рядом с планом
    log = (repo / "PLAN-demo.md.runner.log").read_text("utf-8")
    assert "stage impl | pi:dev | ok" in log and "pi stdout ok" in log
    assert "stage check | gate:" in log and "out59" in log
    assert "GATE-ERR detail" in log


def test_z4b_stop_output_in_state(tmp_path, monkeypatch):
    """TC-PR-025b (Д4): при STOP хвост вывода тоже в state-записи стадии."""
    repo = make_repo(tmp_path)

    def failing_gate(cmd, cwd, timeout):
        return 1, "g-out", "gate failed: boom"
    patch_executors(monkeypatch, repo, pi_calls=[], shell_fn=failing_gate,
                    worktree=repo)
    plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                            "  package: p\n  flow: 4\n  stages:\n"
                            "    - id: a\n      run: gate:true\n```\n",
                      name="PLAN-x.md")
    assert pr.cmd_run(plan, dry_run=False) == 2
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text("utf-8"))
    rec = state["stages"]["a"]
    assert rec["status"] == "stopped"
    assert rec["stdout_tail"] == "g-out"
    assert rec["stderr_tail"] == "gate failed: boom"


def test_z5_state_path_printed_run_and_stop(tmp_path, monkeypatch, capsys):
    """TC-PR-026 (Д5): путь state-файла печатается в начале прогона и в
    диагностике STOP — файл не «теряется» после прогона на реальном репо."""
    repo = make_repo(tmp_path)
    good = "# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 4\n" \
           "  stages:\n    - id: a\n      run: gate:true\n```\n"
    plan = write_plan(repo, good, name="PLAN-x.md")
    patch_executors(monkeypatch, repo, pi_calls=[], worktree=repo)
    assert pr.cmd_run(plan, dry_run=False) == 0
    spath = repo / "PLAN-x.md.runner-state.json"
    assert f"RUNNER: state: {spath}" in capsys.readouterr().out

    def failing_gate(cmd, cwd, timeout):
        return 1, "", "boom"
    sub = tmp_path / "stop-proj"
    sub.mkdir(exist_ok=True)
    repo2 = make_repo(sub)
    plan2 = write_plan(repo2, good, name="PLAN-x.md")
    monkeypatch.setattr(pr, "run_shell", failing_gate)
    assert pr.cmd_run(plan2, dry_run=False) == 2
    err = capsys.readouterr().err
    assert f"state: {repo2 / 'PLAN-x.md.runner-state.json'}" in err


def _foreign_state(spath: Path, **over) -> None:
    spath.write_text(json.dumps({
        "schema_version": pr.STATE_SCHEMA,
        "plan": "/elsewhere/PLAN-demo.md",
        "package": "other-pkg", "flow": 4,
        "stages": {}, "history": [], **over,
    }, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("over", [
    {"package": "other-pkg"},                       # чужой package
    {"plan": "/elsewhere/PLAN-demo.md"},            # чужой plan (скопировали)
])
def test_z5b_foreign_state_stop(tmp_path, monkeypatch, capsys, over):
    """TC-PR-026b (Д5): runner-state чужого пакета/плана — RUNNER-STOP
    exit 2, стадии не исполняются (молчаливый «докат не того пакета»
    исключен)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    _foreign_state(pr.state_path_for(plan), **over)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "RUNNER-STOP:" in err and "чужой" in err
    assert calls == []


def test_z5c_own_state_resumes(tmp_path, monkeypatch, capsys):
    """TC-PR-026c (Д5): свой state (package/plan совпадают) — resume
    работает, RUNNER-STOP нет (позитив к 026b)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls)
    assert pr.cmd_run(plan, dry_run=False) == 0   # state создан и совпадает
    assert pr.cmd_run(plan, dry_run=False) == 0   # resume: всё skipped
    assert "RUNNER-STOP" not in capsys.readouterr().err
    assert len(calls) == 1                        # pi не повторялся


# ------------------------- (и) J61: нормализация зон runner → guard


@pytest.mark.parametrize("zone,expected", [
    ("services/images/**", "services/images"),   # glob-форма манифеста
    ("tests", "tests"),                          # плоская форма
    ("tests/**/*", "tests"),                     # вложенный glob-хвост
    ("docs/*", "docs"),                          # одноуровневый glob
    ("src/backend/", "src/backend"),             # хвостовой слэш
    ("./src/**", "src"),                         # ведущий ./ (паритет с guard)
    ("a/b/**/", "a/b"),                          # glob + хвостовой слэш
])
def test_j61_normalize_zone(zone, expected):
    """TC-PR-027 (J61): normalize_zone — glob-хвосты (`/**`, `/*`, `**`)
    и слэши срезаны, плоская форма без изменений: guard матчит зоны
    префиксом, glob-форма как префикс не матчится ни с одним путем."""
    assert pr.normalize_zone(zone) == expected


def test_j61_zone_glob_normalized_in_env(tmp_path, monkeypatch):
    """TC-PR-027b (J61): PI_ZONE_WRITE в env pi — нормализованная строка
    (смесь glob- и плоской форм), не glob-форма манифеста: с
    `services/images/**` guard уходил в дефолтные зоны и блокировал
    записи pi в свою зону (пилот BUG-026)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, "# PLAN-x\n\n```yaml\npipeline:\n"
                            "  package: p\n  flow: 4\n  stages:\n"
                            "    - id: a\n      run: pi:dev\n"
                            "      zones: [services/images/**, tests]\n"
                            "```\n", name="PLAN-x.md")
    calls: list = []
    patch_executors(monkeypatch, repo, pi_calls=calls, worktree=repo)
    assert pr.cmd_run(plan, dry_run=False) == 0
    env = calls[0]["env"]
    assert env["PI_ZONE_WRITE"] == "services/images:tests"
    # бриф несет зоны как в манифесте (человекочитаемо), нормализация —
    # только в env
    brief = calls[0]["args"][calls[0]["args"].index("-p") + 1]
    assert "services/images/**" in brief
