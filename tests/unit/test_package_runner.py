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
  (и) J61: нормализация зон runner→guard (glob-хвосты срезаются).
  (к) J62: stand-стадии (export-парсинг stdout стенда, env → последующие
      pi/gate стадии, state/resume, НЕ-автоматическое гашение) и
      вердикт-ворота (verdict: file/contains, «Одобрить», pass/fail/файл
      отсутствует, негативы валидации).
  (л) J62-остаток: optional-стадии (gate fail / verdict fail / pi fail /
      таймаут у optional: true → skipped + WARNING, не STOP; обязательная
      — STOP; mixed-манифест; resume не переисполняет skipped; валидация
      optional).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
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


def agents_snapshot(cwd) -> dict:
    """Ролевые файлы раннера в worktree на момент вызова pi (после pi
    раннер их удаляет — в дифф/коммит стадии они не попадают)."""
    return {name: (Path(cwd) / name).read_text("utf-8")
            for name in ("AGENTS.md", "AGENTS.pi.md")
            if (Path(cwd) / name).is_file()}


def fake_pi(calls: list, rc: int = 0):
    def _run_pi(args, cwd, env, timeout):
        calls.append({"args": args, "cwd": cwd, "env": env,
                      "agents": agents_snapshot(cwd)})
        return rc, "pi stdout ok", ""
    return _run_pi


@pytest.fixture(autouse=True)
def flow_gates_sandbox(request, tmp_path, monkeypatch):
    """Реестр сессий, state flowctl и режим — во временном каталоге:
    реальный ~/.hermes/state тесты раннера не трогают. Без маркера
    real_flow_gates ворота pi-стадии подменены разрешающими (их собственная
    проверка — секция (м))."""
    st = tmp_path / "flow-state"
    st.mkdir(exist_ok=True)
    monkeypatch.setenv("PIPELINE_FLOW_REGISTRY", str(st / "active_sessions.json"))
    monkeypatch.setenv("PIPELINE_FLOW_STATE", str(st / "flowctl_state.json"))
    monkeypatch.setenv("FLOW_MODE_FILE", str(st / "flow_mode.json"))
    if request.node.get_closest_marker("real_flow_gates"):
        return
    monkeypatch.setattr(pr, "gate_new", lambda s, r, w: {
        "kind": "fake", "cid": "fake-cid", "delegation_id": "deleg-fake",
        "role": pr.flow_role(s["payload"]), "registry": str(st / "reg.json"),
        "state": str(st / "state.json"), "repo": str(r),
        # как настоящий gate_new: HEAD worktree до стадии (provenance J65.4)
        "base_sha": pr._git_head(w)})
    monkeypatch.setattr(pr, "gate_begin", lambda m, s, r, w, b, g: g)
    monkeypatch.setattr(pr, "zone_recheck", lambda g, w: [])
    monkeypatch.setattr(pr, "shelve_attempt", lambda w, b, label: "fake")
    monkeypatch.setattr(pr, "gate_end", lambda g, w, rep: (True, "fake ok"))
    monkeypatch.setattr(pr, "gate_close", lambda g, c: None)
    monkeypatch.setattr(pr, "gate_abandon", lambda g, why: None)
    monkeypatch.setattr(pr, "_registry_status", lambda reg, did: None)
    monkeypatch.setattr(pr, "commit_stage", lambda wt, msg: None)


def patch_executors(monkeypatch, repo: Path, pi_calls: list,
                    shell_fn=None, worktree: Path | None = None):
    """Подмена pi/shell/worktree; pi пишет вызовы в pi_calls (pi в тестах
    не вызывается)."""
    def fake_pi(args, cwd, env, timeout):
        pi_calls.append({"args": args, "cwd": cwd, "env": env,
                         "agents": agents_snapshot(cwd)})
        return 0, "pi stdout ok", ""
    monkeypatch.setattr(pr, "run_pi", fake_pi)
    if shell_fn is not None:
        monkeypatch.setattr(pr, "run_shell", shell_fn)
    else:
        monkeypatch.setattr(pr, "run_shell",
                            lambda cmd, cwd, timeout, stand_env=None: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree",
                        lambda repo_, sid, br: worktree or repo_)


# ------------------------------------------------------- (а) парсер


def test_a1_valid_manifest_parsed():
    """TC-PR-001: валидный манифест парсится (package/flow/stages, kinds)."""
    m = pr.parse_manifest(write_tmp_plan(VALID))
    assert m["package"] == "demo-pkg"
    assert m["flow"] == 4
    kinds = [(s["kind"], s["executor"], s["payload"]) for s in m["stages"]]
    assert kinds == [("agent", "pi", "dev"), ("gate", "", "python3 scripts/flow_check.py"),
                     ("manual", "hermes", "pm")]
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
    # pi без zones у роли без зоны в реестре ([test-adapted] J65.1: у роли с
    # зоной zones берется из agents/roles.json — TC-J65-ROL-005)
    ("pipeline:\n  package: p\n  flow: 4\n  stages:\n"
     "    - id: a\n      run: pi:auditor\n"),
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

    def fake_shell(cmd, cwd, timeout, stand_env=None):
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

    def failing_gate(cmd, cwd, timeout, stand_env=None):
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

    def slow_gate(cmd, cwd, timeout, stand_env=None):
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

    def failing_gate(cmd, cwd, timeout, stand_env=None):
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
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, t, stand_env=None: (0, "", ""))
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
    def failing_gate(cmd, cwd, timeout, stand_env=None):
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

    def shell_probe(cmd, cwd, timeout, stand_env=None):
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
    assert calls[0]["agents"]["AGENTS.md"] == pack
    assert not (wt / "AGENTS.md").exists()   # убран после pi (не в дифф)
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
    side = calls[0]["agents"]["AGENTS.pi.md"]
    assert not (repo / "AGENTS.pi.md").exists()  # убран после pi
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
    assert calls[0]["agents"] == {"AGENTS.md": pack}  # AGENTS.pi.md нет
    assert not (repo / "AGENTS.md").exists()  # файл раннера убран после pi
    brief = calls[0]["args"][calls[0]["args"].index("-p") + 1]
    assert "в AGENTS.md" in brief and "AGENTS.pi.md" not in brief


def test_z4_success_output_in_state_and_log(tmp_path, monkeypatch):
    """TC-PR-025 (Д4): stdout/stderr успешных стадий не теряются — хвост
    в state (stdout_tail/stderr_tail) и в лог <план>.runner.log; pi и gate
    обе стадии сохраняют вывод."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo)
    calls: list = []

    def loud_gate(cmd, cwd, timeout, stand_env=None):
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

    def failing_gate(cmd, cwd, timeout, stand_env=None):
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

    def failing_gate(cmd, cwd, timeout, stand_env=None):
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


# --------------- (к) J62: stand-стадии и вердикт-ворота раннера


def test_k1_parse_stand_env_mock_stdout():
    """TC-PR-028 (J62): parse_stand_env — строки «export VAR=value» из stdout
    стенда (мок stdout, формат scripts/qa_stand_up.sh): ведущие пробелы,
    кавычки, мусор без export игнорируется."""
    stdout = (
        "==> Схема + seed\n"
        "[OK] nginx-конф отрендерен\n"
        "  export EKOTOV_WIKI_BASE_URL=http://127.0.0.1:18443\n"
        "  export EKOTOV_WIKI_DB_PATH=/tmp/qa-stand/app.db\n"
        "\texported_not_a_var=1\n"
        "export QUOTED=\"http://h:1\"\n"
        "export SINGLE='x y'\n"
        "echo export not_at_line_start=0\n"
    )
    env = pr.parse_stand_env(stdout)
    assert env == {
        "EKOTOV_WIKI_BASE_URL": "http://127.0.0.1:18443",
        "EKOTOV_WIKI_DB_PATH": "/tmp/qa-stand/app.db",
        "QUOTED": "http://h:1",
        "SINGLE": "x y",
    }
    assert pr.parse_stand_env("никаких export здесь нет") == {}
    assert pr.parse_stand_env("") == {}


STAND_MANIFEST = """\
# PLAN-x

```yaml
pipeline:
  package: stand-pkg
  flow: 1
  stages:
    - id: stand-up
      run: stand:bash scripts/qa_stand_up.sh reset
    - id: impl
      run: pi:dev
      zones: [backend/**]
    - id: check
      run: gate:python3 -m pytest tests/api -q
```
"""


def test_k2_stand_exports_env_to_subsequent_stages(tmp_path, monkeypatch):
    """TC-PR-029 (J62): stand-стадия — stdout парсится (export VAR=value),
    env сохраняется в state и прокидывается во все последующие pi/gate
    стадии; сам stand выполняется в worktree."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, STAND_MANIFEST, name="PLAN-x.md")
    calls: list = []
    shell_calls: list = []

    def fake_shell(cmd, cwd, timeout, stand_env=None):
        shell_calls.append({"cmd": cmd, "cwd": cwd, "stand_env": stand_env})
        if cmd.startswith("bash scripts/qa_stand_up.sh"):
            return 0, ("  export EKOTOV_WIKI_BASE_URL=http://127.0.0.1:18443\n"
                       "  export EKOTOV_WIKI_DB_PATH=/tmp/qa-stand/app.db\n"), ""
        return 0, "", ""

    monkeypatch.setattr(pr, "run_shell", fake_shell)
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout:
                        calls.append({"env": env}) or (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    # stand — в worktree, без stand_env
    assert shell_calls[0]["cmd"] == "bash scripts/qa_stand_up.sh reset"
    assert shell_calls[0]["cwd"] == repo
    assert shell_calls[0]["stand_env"] is None
    # gate-стадия получила env стенда
    gate_env_seen = shell_calls[1]["stand_env"]
    assert gate_env_seen["EKOTOV_WIKI_BASE_URL"] == "http://127.0.0.1:18443"
    assert gate_env_seen["EKOTOV_WIKI_DB_PATH"] == "/tmp/qa-stand/app.db"
    # pi-стадия получила env стенда (и зоны не сломаны)
    assert calls[0]["env"]["EKOTOV_WIKI_BASE_URL"] == "http://127.0.0.1:18443"
    assert calls[0]["env"]["PI_ZONE_WRITE"] == "backend"
    # env стенда сохранен в state (resume)
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text("utf-8"))
    assert state["stand_env"] == gate_env_seen
    assert state["stages"]["stand-up"]["status"] == "done"
    assert "stand ok:" in state["stages"]["stand-up"]["detail"]
    # журнал плана содержит stand-стадию
    assert "stand:bash scripts/qa_stand_up.sh reset | ok" in \
        plan.read_text("utf-8")


def test_k2b_stand_teardown_not_automatic_hint(tmp_path, monkeypatch, capsys):
    """TC-PR-029b (J62): после «докатан» — напоминание, что стенд НЕ гасится
    автоматически (reaper/gc подберет сироту); в манифесте без stand — нет."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, STAND_MANIFEST, name="PLAN-x.md")
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, timeout, stand_env=None:
                        (0, "export EKOTOV_WIKI_BASE_URL=http://s:1\n", "")
                        if cmd.startswith("bash scripts/qa_stand_up.sh")
                        else (0, "", ""))
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    out = capsys.readouterr().out
    assert "НЕ выполняется автоматически" in out and "stand_reaper" in out


def test_k3_stand_without_exports_stops(tmp_path, monkeypatch, capsys):
    """TC-PR-030 (J62, негатив): stand-стадия без export в stdout — STOP
    exit 2 (стенд не отчитался env); последующие стадии не исполняются."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, STAND_MANIFEST, name="PLAN-x.md")
    pi_calls: list = []

    def silent_stand(cmd, cwd, timeout, stand_env=None):
        return 0, "стенд поднят (без export)\n", ""

    monkeypatch.setattr(pr, "run_shell", silent_stand)
    monkeypatch.setattr(pr, "run_pi", fake_pi(pi_calls))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "STOP" in err and "export" in err
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text("utf-8"))
    assert state["stages"]["stand-up"]["status"] == "stopped"
    assert pi_calls == []  # до pi дело не дошло


def test_k3b_stand_fail_stops(tmp_path, monkeypatch, capsys):
    """TC-PR-030b (J62, негатив): ненулевой exit stand — STOP exit 2."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, STAND_MANIFEST, name="PLAN-x.md")

    def failing_stand(cmd, cwd, timeout, stand_env=None):
        return 3, "", "stand: контур неполон"
    monkeypatch.setattr(pr, "run_shell", failing_stand)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "stand exit 3" in capsys.readouterr().err


def test_k3c_stand_resume_keeps_env(tmp_path, monkeypatch, capsys):
    """TC-PR-030c (J62): resume — stand_env из state докатывается в
    последующие стадии без переисполнения stand-стадии."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, STAND_MANIFEST, name="PLAN-x.md")
    stand_runs: list = []

    def counting_stand(cmd, cwd, timeout, stand_env=None):
        if cmd.startswith("bash scripts/qa_stand_up.sh"):
            stand_runs.append(cmd)
            return 0, "export EKOTOV_WIKI_BASE_URL=http://s:1\n", ""
        return 0, "", ""
    monkeypatch.setattr(pr, "run_shell", counting_stand)
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    # Первый прогон обрывается на gate-стадии (флаг одного сбоя)
    gate_failed = {"once": False}

    def gate_fail_first_run_only(cmd, cwd, timeout, stand_env=None):
        if cmd.startswith("bash scripts/qa_stand_up.sh"):
            return counting_stand(cmd, cwd, timeout)
        if not gate_failed["once"]:
            gate_failed["once"] = True
            return 1, "", "gate boom"
        return 0, "", ""
    monkeypatch.setattr(pr, "run_shell", gate_fail_first_run_only)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert len(stand_runs) == 1
    # resume: stand не переисполняется, gate повторно получает env стенда
    monkeypatch.setattr(pr, "run_shell", counting_stand)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(stand_runs) == 1  # stand НЕ переисполнялся
    out = capsys.readouterr().out
    assert "уже выполнен" in out and "докатан" in out


VERDICT_MANIFEST = """\
# PLAN-x

```yaml
pipeline:
  package: verdict-pkg
  flow: 1
  stages:
    - id: review
      run: pi:code-reviewer
      zones: [test-model/reviews/**]
      verdict:
        file: test-model/reviews/c9/review-001.md
        contains: "Одобрить"
    - id: next
      run: gate:true
```
"""


def test_k4_verdict_gate_pass(tmp_path, monkeypatch, capsys):
    """TC-PR-031 (J62): вердикт-ворота pass — pi написал файл с маркером
    «Одобрить», пакет докатан."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, VERDICT_MANIFEST, name="PLAN-x.md")

    def pi_writes_verdict(args, cwd, env, timeout):
        vf = cwd / "test-model/reviews/c9/review-001.md"
        vf.parent.mkdir(parents=True, exist_ok=True)
        vf.write_text("## Ревью\n\n## Вердикт: Одобрить\n", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(pr, "run_pi", pi_writes_verdict)
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, timeout, stand_env=None: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert "докатан" in capsys.readouterr().out


def test_k4b_verdict_gate_fail_stop(tmp_path, monkeypatch, capsys):
    """TC-PR-032 (J62): вердикт-ворота fail — маркера нет → STOP exit 2
    «ЖДУ ПМ: возврат ревью», next-стадия не исполняется, stage stopped."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, VERDICT_MANIFEST, name="PLAN-x.md")

    def pi_writes_return(args, cwd, env, timeout):
        vf = cwd / "test-model/reviews/c9/review-001.md"
        vf.parent.mkdir(parents=True, exist_ok=True)
        vf.write_text("## Вердикт: Вернуть\n", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(pr, "run_pi", pi_writes_return)
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, timeout, stand_env=None: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "ЖДУ ПМ: возврат ревью" in err
    # [test-adapted] J65.4: вердикт читает единый парсер, а не подстрока
    assert "review-001.md — return" in err
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text("utf-8"))
    assert state["stages"]["review"]["status"] == "stopped"
    assert "next" not in state["stages"]


def test_k4c_verdict_file_missing_stops(tmp_path, monkeypatch, capsys):
    """TC-PR-032b (J62, негатив): файл вердикта не создан — STOP
    «ЖДУ ПМ: возврат ревью» (прозаический вердикт «по памяти» не проходит)."""
    repo = make_repo(tmp_path)
    plan = write_plan(repo, VERDICT_MANIFEST, name="PLAN-x.md")
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "run_shell",
                        lambda cmd, cwd, timeout, stand_env=None: (0, "", ""))
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "ЖДУ ПМ: возврат ревью" in err and "не читается" in err


def test_k4d_verdict_gate_on_gate_stage(tmp_path, monkeypatch, capsys):
    """TC-PR-033 (J62): вердикт-ворота на gate-стадии — тоже работают."""
    text = VERDICT_MANIFEST.replace(
        "    - id: review\n      run: pi:code-reviewer\n"
        "      zones: [test-model/reviews/**]\n",
        "    - id: review\n      run: gate:bash make-review.sh\n")
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")

    def gate_writes_verdict(cmd, cwd, timeout, stand_env=None):
        vf = cwd / "test-model/reviews/c9/review-001.md"
        vf.parent.mkdir(parents=True, exist_ok=True)
        vf.write_text("## Вердикт: Одобрить\n", encoding="utf-8")
        return 0, "", ""
    monkeypatch.setattr(pr, "run_pi",
                        lambda args, cwd, env, timeout: (0, "", ""))
    monkeypatch.setattr(pr, "run_shell", gate_writes_verdict)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert "докатан" in capsys.readouterr().out


def test_k5_verdict_validation_negatives():
    """TC-PR-034 (J62, негативы): verdict не отображение / без file —
    ManifestError; валидный verdict нормализуется. [test-adapted] J65.4:
    `contains` устарел — без него verdict валиден, с ним — сохраняется
    (раннер предупреждает и игнорирует)."""
    base = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 1\n"
            "  stages:\n    - id: a\n      run: gate:true\n")
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(base + "      verdict: approved\n```\n"))
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(
            base + "      verdict:\n        contains: \"Одобрить\"\n```\n"))
    m0 = pr.parse_manifest(write_tmp_plan(
        base + "      verdict:\n        file: review.md\n```\n"))
    assert m0["stages"][0]["verdict"] == {"file": "review.md"}
    m = pr.parse_manifest(write_tmp_plan(
        base + "      verdict:\n        file: r.md\n"
               "        contains: \"Одобрить\"\n```\n"))
    assert m["stages"][0]["verdict"] == {"file": "r.md", "contains": "Одобрить"}
    # без verdict — None (обратная совместимость)
    m2 = pr.parse_manifest(write_tmp_plan(VALID))
    assert m2["stages"][0]["verdict"] is None


# -------------------------------------- (л) optional-стадии (J62-остаток)

OPTIONAL_MANIFEST = """\
# PLAN-x

```yaml
pipeline:
  package: opt-pkg
  flow: 1
  stages:
    - id: design
      run: pi:ui-designer
      zones: [design/**]
      optional: true
    - id: check
      run: gate:true
    - id: final
      run: gate:true
```
"""


def test_l1_optional_gate_fail_skips_and_continues(tmp_path, monkeypatch,
                                                   capsys):
    """TC-PR-035: optional gate:fail → stage skipped + WARNING, пакет едет
    дальше (следующая стадия исполняется, exit 0, НЕ STOP)."""
    text = (OPTIONAL_MANIFEST
            .replace("    - id: design\n      run: pi:ui-designer\n"
                     "      zones: [design/**]\n      optional: true\n",
                     "    - id: opt_gate\n      run: gate:false\n"
                     "      optional: true\n")
            .replace("    - id: final\n", "    - id: after\n"))
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")
    calls: list = []

    # gate:false → 1, gate:true → 0
    def shell_by_cmd(cmd, cwd, timeout, stand_env=None):
        calls.append(cmd)
        if cmd.strip() == "false":
            return 1, "", "gate failed"
        return 0, "", ""

    monkeypatch.setattr(pr, "run_shell", shell_by_cmd)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(calls) == 3  # opt_gate(false) + check + after — все исполнены
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["opt_gate"]["status"] == "skipped"
    assert state["stages"]["after"]["status"] == "done"
    err = capsys.readouterr().err
    assert "RUNNER-WARNING" in err and "skipped" in err
    plan_text = plan.read_text(encoding="utf-8")
    assert "WARNING" in plan_text and "SKIPPED" in plan_text


def test_l2_optional_verdict_fail_skips(tmp_path, monkeypatch, capsys):
    """TC-PR-036: optional pi-стадия с verdict fail (маркера нет) →
    skipped, пакет докатан (обязательная same-семантика — STOP)."""
    text = VERDICT_MANIFEST.replace(
        "    - id: review\n      run: pi:code-reviewer\n"
        "      zones: [test-model/reviews/**]\n",
        "    - id: review\n      run: pi:ui-designer\n"
        "      zones: [design/**]\n      optional: true\n")
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")
    patch_executors(monkeypatch, repo, [])  # pi ok, но verdict-файла нет
    assert pr.cmd_run(plan, dry_run=False) == 0
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["review"]["status"] == "skipped"
    assert "verdict" in state["stages"]["review"]["detail"]
    assert state["stages"]["next"]["status"] == "done"


def test_l3_optional_pi_fail_skips(tmp_path, monkeypatch, capsys):
    """TC-PR-037: optional pi exit≠0 → skipped + продолжение; pi-таймаут —
    тоже skipped; обязательная стадия после — STOP как раньше."""
    repo = make_repo(tmp_path)
    calls: list = []

    def pi_fails_first(args, cwd, env, timeout):
        calls.append(args[4])  # роль из брифа не достать — пишем факт вызова
        if len(calls) == 1:
            return 3, "", "pi exploded"
        return 0, "ok", ""

    patch_executors(monkeypatch, repo, [])
    monkeypatch.setattr(pr, "run_pi", pi_fails_first)
    text = OPTIONAL_MANIFEST.replace(
        "    - id: check\n      run: gate:true\n    - id: final\n",
        "    - id: must\n      run: gate:true\n    - id: after\n")
    plan = write_plan(repo, text, name="PLAN-x.md")
    assert pr.cmd_run(plan, dry_run=False) == 0
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["design"]["status"] == "skipped"
    assert state["stages"]["design"]["exit_code"] == 3
    assert state["stages"]["must"]["status"] == "done"
    assert state["stages"]["after"]["status"] == "done"

    # pi-таймаут optional → skipped тоже
    calls.clear()

    def pi_timeout(args, cwd, env, timeout):
        raise subprocess.TimeoutExpired(cmd="pi", timeout=timeout,
                                       output="partial out", stderr="perr")

    monkeypatch.setattr(pr, "run_pi", pi_timeout)
    plan2 = write_plan(repo, text, name="PLAN-x2.md")
    assert pr.cmd_run(plan2, dry_run=False) == 0
    state2 = json.loads((repo / "PLAN-x2.md.runner-state.json").read_text())
    assert state2["stages"]["design"]["status"] == "skipped"
    assert "таймаут" in state2["stages"]["design"]["detail"]
    assert "partial out" in state2["stages"]["design"]["stdout_tail"]


def test_l3b_optional_stage_gate_fail_skips(tmp_path, monkeypatch, capsys):
    """TC-PR-037b: optional pi-стадия — pi ok, но stage-gate fail →
    skipped (пакет едет дальше)."""
    repo = make_repo(tmp_path)
    text = OPTIONAL_MANIFEST.replace(
        "      zones: [design/**]\n      optional: true\n",
        '      zones: [design/**]\n      gate: "false"\n      optional: true\n')
    plan = write_plan(repo, text, name="PLAN-x.md")
    patch_executors(monkeypatch, repo, [],
                    shell_fn=lambda cmd, cwd, timeout, stand_env=None:
                    (1, "", "gate dead") if cmd.strip() == "false"
                    else (0, "", ""))
    assert pr.cmd_run(plan, dry_run=False) == 0
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["design"]["status"] == "skipped"
    assert "gate stage exit 1" in state["stages"]["design"]["detail"]
    assert state["stages"]["check"]["status"] == "done"


def test_l4_mandatory_stage_still_stops(tmp_path, monkeypatch, capsys):
    """TC-PR-038 (регресс): та же стадия без optional — STOP exit 2,
    следующая стадия НЕ исполняется."""
    text = (OPTIONAL_MANIFEST
            .replace("      zones: [design/**]\n      optional: true\n",
                     "      zones: [design/**]\n")
            .replace("    - id: final\n", "    - id: after\n"))
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")
    calls: list = []

    def pi_fails(args, cwd, env, timeout):
        calls.append("pi")
        return 1, "", "pi exploded"

    patch_executors(monkeypatch, repo, [])
    monkeypatch.setattr(pr, "run_pi", pi_fails)

    def shell_counts(cmd, cwd, timeout, stand_env=None):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(pr, "run_shell", shell_counts)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert calls == ["pi"]  # check/after не исполнялись
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["design"]["status"] == "stopped"
    err = capsys.readouterr().err
    assert "ЖДУ ПМ: STOP" in err


def test_l5_mixed_manifest(tmp_path, monkeypatch, capsys):
    """TC-PR-039: смешанный манифест — optional-стадии падают (skipped),
    пакет едет; обязательная стадия падает → STOP exit 2; в state и
    skipped, и stopped."""
    text = ("""\
# PLAN-x

```yaml
pipeline:
  package: mixed-pkg
  flow: 1
  stages:
    - id: design
      run: pi:ui-designer
      zones: [design/**]
      optional: true
    - id: design_check
      run: pi:design-validator
      zones: [test-model/reviews/**]
      optional: true
      verdict:
        file: test-model/reviews/c9/design-check-001.md
        contains: "Одобрить"
    - id: dev
      run: gate:false
    - id: after
      run: gate:true
```
""")
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")
    patch_executors(monkeypatch, repo, [],
                    shell_fn=lambda cmd, cwd, timeout, stand_env=None:
                    (1, "", "x") if cmd.strip() == "false" else (0, "", ""))
    assert pr.cmd_run(plan, dry_run=False) == 2
    state = json.loads((repo / "PLAN-x.md.runner-state.json").read_text())
    assert state["stages"]["design"]["status"] == "done"  # pi ok — done
    assert state["stages"]["design_check"]["status"] == "skipped"  # verdict fail
    assert state["stages"]["dev"]["status"] == "stopped"
    assert "after" not in state["stages"]
    plan_text = plan.read_text(encoding="utf-8")
    assert plan_text.count("WARNING") == 1  # одна optional-стадия упала


def test_l6_resume_skipped_not_rerun(tmp_path, monkeypatch, capsys):
    """TC-PR-040: resume — skipped-стадия не переисполняется (ретраев
    нет), пакет докатывается."""
    text = (OPTIONAL_MANIFEST
            .replace("    - id: design\n      run: pi:ui-designer\n"
                     "      zones: [design/**]\n      optional: true\n",
                     "    - id: opt_gate\n      run: gate:false\n"
                     "      optional: true\n")
            .replace("    - id: final\n", "    - id: after\n"))
    repo = make_repo(tmp_path)
    plan = write_plan(repo, text, name="PLAN-x.md")

    def shell_by_cmd(cmd, cwd, timeout, stand_env=None):
        if cmd.strip() == "false":
            return 1, "", "gate failed"
        return 0, "", ""

    patch_executors(monkeypatch, repo, [], shell_fn=shell_by_cmd)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert pr.cmd_run(plan, dry_run=False) == 0  # resume
    out = capsys.readouterr().out
    assert "opt_gate — уже выполнен (resume, пропуск)" in out
    assert "докатан" in out


def test_l7_optional_validation():
    """TC-PR-041 (негатив/позитив): optional не bool — ManifestError;
    optional: true/false парсится; без optional — False."""
    base = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 1\n"
            "  stages:\n    - id: a\n      run: gate:true\n")
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(base + "      optional: \"yes\"\n```\n"))
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(base + "      optional: 1\n```\n"))
    m = pr.parse_manifest(write_tmp_plan(base + "      optional: true\n```\n"))
    assert m["stages"][0]["optional"] is True
    m = pr.parse_manifest(write_tmp_plan(base + "      optional: false\n```\n"))
    assert m["stages"][0]["optional"] is False
    m = pr.parse_manifest(write_tmp_plan(VALID))
    assert m["stages"][0]["optional"] is False


# ---------------- (м) ворота pi-стадии: flowctl prepare/run/finish + зона
# Реальные flowctl/session_check во временном реестре (фикстура
# flow_gates_sandbox), pi подменен функцией, пишущей файлы в worktree.


def gated_plan(tmp_path: Path, stages: str, *, package: str = "express-x",
               flow: int = 5) -> tuple[Path, Path]:
    """Fixture-репо с PLAN-<package>.md (Флоу: N + манифест), закоммичен."""
    repo = make_repo(tmp_path)
    text = (f"# PLAN-{package}\n\n**Флоу: {flow}** — тестовый пакет.\n\n"
            f"```yaml\npipeline:\n  package: {package}\n  flow: {flow}\n"
            f"  stages:\n{stages}```\n")
    plan = write_plan(repo, text, name=f"PLAN-{package}.md")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "plan"],
                   check=True)
    return repo, plan


def patch_gated(monkeypatch, tmp_path: Path, writes: list, rc: int = 0):
    """pi пишет файлы writes (относительно worktree); worktree — git
    worktree с SESSION.md (как у session_worktree.sh)."""
    wt = tmp_path / "wt"
    calls: list = []

    def fake_pi(args, cwd, env, timeout):
        calls.append({"args": args, "env": env,
                      "agents": agents_snapshot(cwd)})
        for rel in writes:
            p = Path(cwd) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("X = 1\n", encoding="utf-8")
        return rc, "pi stdout ok", ""

    def fake_worktree(repo, sid, branch):
        if not wt.exists():
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q",
                            "-b", branch, str(wt)], check=True)
            (wt / "SESSION.md").write_text("session\n", encoding="utf-8")
        return wt

    monkeypatch.setattr(pr, "run_pi", fake_pi)
    monkeypatch.setattr(pr, "ensure_worktree", fake_worktree)
    return wt, calls


def registry_statuses() -> list[tuple[str, str]]:
    reg, _ = pr.flow_paths()
    if not reg.is_file():
        return []
    data = json.loads(reg.read_text(encoding="utf-8"))
    return [(s["role"], s["status"]) for s in data.get("sessions", [])]


def branch_files(wt: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(wt), "log", "--format=",
                          "--name-only", "HEAD~1..HEAD"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(x for x in out.splitlines() if x.strip())


DEV_STAGE = ("    - id: impl\n      run: pi:dev\n      zones: [src/**]\n"
             "      task: сделать\n")


@pytest.mark.real_flow_gates
def test_m1_gated_stage_accepted_committed_closed(tmp_path, monkeypatch,
                                                  capsys):
    """TC-PR-042: pi-стадия проходит prepare/run/finish: дифф в зоне →
    коммит стадии (только работа агента: без SESSION.md и AGENTS.md
    раннера), резервация закрыта (closed), запись цикла flowctl —
    express_task с provisional (pr_validate — на PR CI)."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    wt, calls = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert len(calls) == 1 and "AGENTS.md" in calls[0]["agents"]
    assert branch_files(wt) == ["src/x.py"]
    subj = subprocess.run(["git", "-C", str(wt), "log", "-1", "--format=%s"],
                          capture_output=True, text=True).stdout
    assert subj.startswith("[pipeline] express-x/impl: pi:dev")
    assert registry_statuses() == [("dev", "closed")]
    _, fstate = pr.flow_paths()
    runs = json.loads(fstate.read_text(encoding="utf-8"))["runs"]
    (rec,) = runs.values()
    assert rec["action"] == "express_task" and rec["status"] == "provisional"
    gate = pr.state_load(pr.state_path_for(plan))["flow_gates"]["impl"]
    assert gate["open"] is False and gate["commit"]
    assert "ворота входа пройдены" in capsys.readouterr().out


@pytest.mark.real_flow_gates
def test_m2_out_of_zone_stop_then_resume(tmp_path, monkeypatch, capsys):
    """TC-PR-043: запись вне зоны — STOP (OUT_OF_ZONE), коммита нет, зона
    держится (needs_attention); повтор после правки: прошлая попытка
    освобождена (released), новая принята и закрыта."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    wt, _ = patch_gated(monkeypatch, tmp_path, ["src/x.py", "docs/x.md"])
    head = pr._git_head(repo)
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "ворота выхода" in err and "OUT_OF_ZONE" in err and "docs/x.md" in err
    assert pr._git_head(wt) == head
    assert registry_statuses() == [("dev", "needs_attention")]
    (wt / "docs" / "x.md").unlink()           # ПМ убрал лишнее
    patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert registry_statuses() == [("dev", "released"), ("dev", "closed")]
    assert branch_files(wt) == ["src/x.py"]


@pytest.mark.real_flow_gates
def test_m3_prepare_deny_stops_before_pi(tmp_path, monkeypatch, capsys):
    """TC-PR-044: DENY prepare (Флоу 1 без change-пакета/требований) —
    STOP до pi, резервации нет."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE, package="add-gadget",
                            flow=1)
    _, calls = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "ворота входа: flowctl prepare dev_task" in err
    assert calls == []
    assert registry_statuses() == []


@pytest.mark.real_flow_gates
def test_m4_zone_outside_policy_stops(tmp_path, monkeypatch, capsys):
    """TC-PR-045: зона стадии шире политики роли (agents/README.md) —
    STOP ZONE_OUTSIDE_POLICY до pi (роль без этапа во Флоу 5 —
    code_reviewer; политика: code-reviews/*/review-*.md)."""
    repo, plan = gated_plan(
        tmp_path, "    - id: review\n      run: pi:code-reviewer\n"
                  "      zones: [test-model/reviews/**]\n")
    _, calls = patch_gated(monkeypatch, tmp_path, [])
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "ZONE_OUTSIDE_POLICY" in err and "test-model/reviews/**" in err
    assert calls == []


@pytest.mark.real_flow_gates
def test_m5_zone_conflict_with_foreign_session(tmp_path, monkeypatch, capsys):
    """TC-PR-046: зона занята чужой сессией того же repo (делегация или
    другой пакет) — STOP ZONE_CONFLICT до pi."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    reg, _ = pr.flow_paths()
    res = pr.sc.reserve({
        "repo": str(repo), "delegation_id": "deleg-foreign", "role": "dev",
        "project": "proj", "owner_pm": "pm-main", "paths": ["src/**"],
        "policy_version": pr.rzp.policy_version()}, reg)
    assert res["allowed"]
    _, calls = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "ZONE_CONFLICT" in capsys.readouterr().err
    assert calls == []


@pytest.mark.real_flow_gates
def test_m6_role_without_stage_zone_gate(tmp_path, monkeypatch, capsys):
    """TC-PR-047: роль без этапа во флоу (regress_runner) — WARNING
    ROLE_WITHOUT_STAGE, резервация по политике роли; запись в зоне —
    коммит и closed; запись вне зоны — STOP по post-check."""
    stages = ("    - id: regress\n      run: pi:regress-runner\n"
              "      zones: [test-model/regress/express-x/**]\n")
    repo, plan = gated_plan(tmp_path, stages)
    wt, _ = patch_gated(monkeypatch, tmp_path,
                        ["test-model/regress/express-x/regress-001.md"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert "ROLE_WITHOUT_STAGE" in capsys.readouterr().err
    assert branch_files(wt) == ["test-model/regress/express-x/regress-001.md"]
    assert registry_statuses() == [("regress_runner", "closed")]


@pytest.mark.real_flow_gates
def test_m6b_role_without_stage_out_of_zone(tmp_path, monkeypatch, capsys):
    """TC-PR-047b: роль без этапа пишет вне зоны — STOP (session_check)."""
    stages = ("    - id: regress\n      run: pi:regress-runner\n"
              "      zones: [test-model/regress/express-x/**]\n")
    repo, plan = gated_plan(tmp_path, stages)
    patch_gated(monkeypatch, tmp_path, ["tests/test_x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 2
    err = capsys.readouterr().err
    assert "session_check check" in err and "tests/test_x.py" in err


@pytest.mark.real_flow_gates
def test_m7_optional_stage_gate_denied_skips(tmp_path, monkeypatch, capsys):
    """TC-PR-048: optional-стадия, не прошедшая ворота входа, — skipped
    (пакет едет дальше), резервация не остается."""
    stages = ("    - id: review\n      run: pi:code-reviewer\n"
              "      zones: [test-model/reviews/**]\n      optional: true\n"
              + DEV_STAGE)
    repo, plan = gated_plan(tmp_path, stages)
    patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    st = pr.state_load(pr.state_path_for(plan))["stages"]
    assert st["review"]["status"] == "skipped" and st["impl"]["status"] == "done"
    assert registry_statuses() == [("dev", "closed")]


def test_m8_stage_action_mapping():
    """TC-PR-049: роль → этап STAGE_TABLE флоу; action: выбирает другой
    этап роли; чужой этап — STAGE_ACTION_INVALID; роль без этапа — None."""
    assert pr.flow_role("code-reviewer") == "code_reviewer"
    assert pr.stage_action("dev", 1) == "dev_task"
    assert pr.stage_action("dev", 5) == "express_task"
    assert pr.stage_action("code_reviewer", 1) == "code_review"
    assert pr.stage_action("code_reviewer", 1, "accept_review") == "accept_review"
    with pytest.raises(pr.GateDenied, match="STAGE_ACTION_INVALID"):
        pr.stage_action("dev", 1, "code_review")
    assert pr.stage_action("ba", 1) is None
    assert pr.stage_action("regress_runner", 4) is None


@pytest.mark.parametrize("zone,expected", [
    ("code-reviews/*/review-*.md", "code-reviews"),   # glob в середине
    ("openspec/changes/*/tasks.md", "openspec/changes"),
    ("requirements.md", "requirements.md"),
    ("**", "**"),                                     # весь репо — как есть
])
def test_m9_normalize_policy_glob_zone(zone, expected):
    """TC-PR-050: зона политики с glob в середине → конкретный префикс для
    guard'а (точная сверка — session_check по диффу)."""
    assert pr.normalize_zone(zone) == expected


def test_m10_gate_manifest_keys_validation():
    """TC-PR-051: action/task_id/approval_ref — непустые строки, парсятся
    в stage; без ключей — пустые строки."""
    base = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p\n  flow: 1\n"
            "  stages:\n    - id: a\n      run: pi:dev\n      zones: [src/**]\n")
    m = pr.parse_manifest(write_tmp_plan(
        base + "      action: dev_task\n      task_id: \"1.1\"\n"
               "      approval_ref: decisions/x.md\n```\n"))
    st = m["stages"][0]
    assert (st["action"], st["task_id"], st["approval_ref"]) == (
        "dev_task", "1.1", "decisions/x.md")
    assert pr.parse_manifest(write_tmp_plan(base + "```\n"))["stages"][0][
        "action"] == ""
    with pytest.raises(pr.ManifestError):
        pr.parse_manifest(write_tmp_plan(base + "      task_id: 7\n```\n"))


def test_m11_yaml_trailing_comment_stripped():
    """TC-PR-052: комментарий в конце строки срезается (паритет с
    yaml.safe_load); `#` внутри кавычек и без пробела перед ним — данные."""
    text = ("# PLAN-x\n\n```yaml\npipeline:\n  package: p  # пакет\n"
            "  flow: 5\n  stages:\n"
            "    - id: a\n      run: pi:sa   # СА пишет спеку\n"
            "      zones: [src/**]  # зона\n"
            "      task: \"шаг #1 # не комментарий\"\n"
            "    - id: b\n      run: gate:echo a#b\n```\n")
    m = pr.parse_manifest(write_tmp_plan(text))
    a, b = m["stages"]
    assert m["package"] == "p"
    assert (a["payload"], a["zones"]) == ("sa", ["src/**"])
    assert a["task"] == "шаг #1 # не комментарий"
    assert b["payload"] == "echo a#b"


def test_m12_guide_examples_parse_and_fit_policy():
    """TC-PR-053: примеры манифеста гайда docs/guides/pipeline-manifest.md
    разбираются раннером, зоны pi-стадий — в рамках политики ролей (иначе
    стадия примера получает ZONE_OUTSIDE_POLICY на воротах)."""
    import re
    guide = (FACTORY / "docs/guides/pipeline-manifest.md").read_text("utf-8")
    blocks = re.findall(r"```yaml\n.*?```", guide, re.DOTALL)
    assert len(blocks) >= 2
    for block in blocks:
        m = pr.parse_manifest(write_tmp_plan("# P\n\n" + block + "\n"))
        for st in m["stages"]:
            if st["kind"] != "pi":
                continue
            role = pr.flow_role(st["payload"])
            narrowed = pr.rzp.narrow_zones(
                role, [pr.sc.canonical(z) for z in st["zones"]])
            assert narrowed["violations"] == [], (st["id"], narrowed)


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")


@pytest.mark.real_flow_gates
def test_m13_dependent_flow1_stages_see_package_branch(tmp_path, monkeypatch,
                                                       capsys):
    """TC-PR-054 (ревью #214, blocker): зависимые стадии Флоу 1 подряд —
    create_change (pi:sa) коммитит change-пакет только в ветку пакета,
    architecture_review (pi:architect) проходит prepare: снимок фактов
    берется из worktree пакета, а не из основного клона (там пакета нет)."""
    pkg = "add-gadget"
    stages = (
        "    - id: create_change\n      run: pi:sa\n"
        "      approval_ref: 2026-11-02-start-add-gadget\n"
        "      zones:\n"
        f"        - openspec/changes/{pkg}/proposal.md\n"
        f"        - openspec/changes/{pkg}/design.md\n"
        f"        - openspec/changes/{pkg}/tasks.md\n"
        f"        - openspec/changes/{pkg}/specs/**\n"
        "        - sdd.md\n"
        "    - id: arch_review\n      run: pi:architect\n"
        "      zones:\n        - architecture/**\n"
        f"        - test-model/reviews/{pkg}/review-001-architecture.md\n")
    repo = make_repo(tmp_path)
    (repo / "requirements.md").write_text(REQ_APPROVED, encoding="utf-8")
    repo, plan = gated_plan(tmp_path, stages, package=pkg, flow=1)
    sha = pr._git_head(repo)
    dec = repo / "decisions" / "2026-11-02-start-add-gadget.md"
    dec.parent.mkdir(exist_ok=True)
    dec.write_text(
        "# Решение: старт add-gadget\n\n```decision-record\n" + json.dumps({
            "schema_version": "decision-record/1",
            "decision_id": "2026-11-02-start-add-gadget",
            "date": "2026-11-02",
            "scope": {"project": "proj", "change_id": pkg, "phase": 1},
            "action": "create_change", "commit": sha,
            "source": "чат-лог: «погнали» 2026-11-02"},
            ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "decision"],
                   check=True)
    writes = {
        "sa": [f"openspec/changes/{pkg}/proposal.md",
               f"openspec/changes/{pkg}/design.md",
               f"openspec/changes/{pkg}/tasks.md",
               f"openspec/changes/{pkg}/specs/widget/spec.md", "sdd.md"],
        "architect": ["architecture/map.md",
                      f"test-model/reviews/{pkg}/review-001-architecture.md"],
    }
    wt, calls = patch_gated(monkeypatch, tmp_path, [])
    seen: list = []

    def fake_pi(args, cwd, env, timeout):
        role = "sa" if "pi:sa" in args[-1] or "Роль: sa" in args[-1] \
            else "architect"
        seen.append(role)
        for rel in writes[role]:
            p = Path(cwd) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("### Requirement: W\n#### Scenario: S\n- GIVEN a\n"
                         "- WHEN b\n- THEN c\n" if rel.endswith("spec.md")
                         else "# x\n", encoding="utf-8")
        return 0, "ok", ""

    monkeypatch.setattr(pr, "run_pi", fake_pi)
    # OpenSpec CLI в тестовой среде нет — гейт openspec_validate этапа
    # create_change гоняется заглушкой (сама передача — PIPELINE_OPENSPEC_CMD)
    monkeypatch.setenv("PIPELINE_OPENSPEC_CMD", "true")
    rc = pr.cmd_run(plan, dry_run=False)
    err = capsys.readouterr().err
    assert rc == 0, err
    assert seen == ["sa", "architect"]
    # основной клон change-пакета не видел — работа только в ветке пакета
    assert not (repo / "openspec" / "changes" / pkg).exists()
    assert registry_statuses() == [("sa", "closed"), ("architect", "closed")]


@pytest.mark.real_flow_gates
def test_m14_optional_failure_shelves_files(tmp_path, monkeypatch, capsys):
    """TC-PR-055 (ревью #214, major): optional-стадия упала после записи —
    ее файлы уходят в git stash, следующая стадия принимается без чужих
    файлов в дифе."""
    stages = ("    - id: draft\n      run: pi:dev\n      zones: [src/**]\n"
              "      optional: true\n"
              "    - id: impl\n      run: pi:dev\n      zones: [scripts/**]\n")
    repo, plan = gated_plan(tmp_path, stages)
    wt, _ = patch_gated(monkeypatch, tmp_path, [])
    attempts: list = []

    def fake_pi(args, cwd, env, timeout):
        first = not attempts
        attempts.append(1)
        rel = "src/x.py" if first else "scripts/x.py"
        p = Path(cwd) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("X = 1\n", encoding="utf-8")
        return (1 if first else 0), "out", ""

    monkeypatch.setattr(pr, "run_pi", fake_pi)
    assert pr.cmd_run(plan, dry_run=False) == 0
    st = pr.state_load(pr.state_path_for(plan))
    assert st["stages"]["draft"]["status"] == "skipped"
    assert st["flow_gates"]["draft"]["shelved"].startswith("stash")
    assert branch_files(wt) == ["scripts/x.py"]
    stash = subprocess.run(["git", "-C", str(wt), "stash", "show",
                            "--include-untracked", "--name-only"],
                           capture_output=True, text=True).stdout
    assert "src/x.py" in stash
    assert registry_statuses() == [("dev", "released"), ("dev", "closed")]


@pytest.mark.real_flow_gates
def test_m15_finish_does_not_reopen_closed_zone(tmp_path, monkeypatch):
    """TC-PR-056 (ревью #214, major): повторный flowctl finish по
    provisional-записи, закрытой раннером, — blocked, зона не
    переоткрывается (реестр остается closed); запись помечена раннером."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    wt, _ = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    gate = pr.state_load(pr.state_path_for(plan))["flow_gates"]["impl"]
    report = tmp_path / "again.md"
    report.write_text("x", encoding="utf-8")
    rc, payload, _ = pr.run_flowctl([
        "finish", "--correlation-id", gate["cid"], "--report", str(report),
        "--pr-id", "1", "--registry", gate["registry"], "--state",
        gate["state"], "--json"])
    assert rc == 2 and payload["verdict"] == "blocked"
    assert registry_statuses() == [("dev", "closed")]
    _, fstate = pr.flow_paths()
    rec = json.loads(fstate.read_text("utf-8"))["runs"][gate["cid"]]
    assert rec["package_runner"]["commit"] == gate["commit"]


@pytest.mark.real_flow_gates
def test_m16_prepare_reservation_released_on_failure(tmp_path, monkeypatch,
                                                     capsys):
    """TC-PR-057 (ревью #214, minor): prepare создал резервацию, затем
    отказ (rc≠0 / сбой run) — резервация освобождается, повтор не
    получает ZONE_CONFLICT со своей сиротой."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    real = pr.run_flowctl

    def flaky(argv):
        rc, payload, err = real(argv)
        if argv[0] == "run":
            return 2, {}, "flowctl run: TimeoutExpired: boom"
        return rc, payload, err

    monkeypatch.setattr(pr, "run_flowctl", flaky)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "TimeoutExpired" in capsys.readouterr().err
    assert registry_statuses() == [("dev", "released")]
    monkeypatch.setattr(pr, "run_flowctl", real)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert registry_statuses() == [("dev", "released"), ("dev", "closed")]


@pytest.mark.real_flow_gates
def test_m17_recheck_blocks_files_after_finish(tmp_path, monkeypatch, capsys):
    """TC-PR-058 (ревью #214, minor): файл вне зоны, появившийся после
    приемки (артефакт гейта finish), не попадает в коммит стадии — STOP."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    wt, _ = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    real_end = pr.gate_end

    def end_then_artifact(gate, worktree, report):
        res = real_end(gate, worktree, report)
        (worktree / "gate-cache.txt").write_text("x", encoding="utf-8")
        return res

    monkeypatch.setattr(pr, "gate_end", end_then_artifact)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "gate-cache.txt" in capsys.readouterr().err
    subj = subprocess.run(["git", "-C", str(wt), "log", "-1", "--format=%s"],
                          capture_output=True, text=True).stdout
    assert not subj.startswith("[pipeline]")      # коммита стадии нет


@pytest.mark.real_flow_gates
def test_m18_engine_missing_stops_pi_stage(tmp_path, monkeypatch, capsys):
    """TC-PR-059 (ревью #214, minor): раннер без движка фабрики (копия в
    проекте без AI_FACTORY_HOME) — pi-стадия STOP FACTORY_ENGINE_MISSING,
    pi без ворот не запускается."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE)
    _, calls = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    monkeypatch.setattr(pr, "fc", None)
    assert pr.cmd_run(plan, dry_run=False) == 2
    assert "FACTORY_ENGINE_MISSING" in capsys.readouterr().err
    assert calls == []


@pytest.mark.real_flow_gates
def test_m19_flow4_slug_package_passes_gates(tmp_path, monkeypatch):
    """TC-PR-060 (J64.3): пакет Флоу 4 со slug-именем (план PLAN-<slug>.md)
    проходит реальные ворота — раньше prepare давал UNKNOWN AMBIGUOUS_STATE
    (CHORE_RE = ^chore$), и раннер останавливался."""
    repo, plan = gated_plan(tmp_path, DEV_STAGE, package="chore-x", flow=4)
    wt, _ = patch_gated(monkeypatch, tmp_path, ["src/x.py"])
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert branch_files(wt) == ["src/x.py"]
    assert registry_statuses() == [("dev", "closed")]
