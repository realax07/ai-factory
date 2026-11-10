# -*- coding: utf-8 -*-
"""J64.13: стадия dev разворачивается по задачам tasks.md (правило 11, J31).

Одна pi-стадия на весь пакет (таймаут 1800 с) нарушала «1 задача = 1
сессия». Ключ манифеста `per_task: true` разворачивает pi-стадию в
под-стадии `<id>-<задача>` (task_id → flowctl prepare --task), порядок — по
зависимостям tasks.md.

Трассировка:
  TC-J64-DPT-001  per_task_ids: открытые dev-задачи; закрытые, QA-раздел 6,
                  [ops]/[docs]/[design] — пропускаются; топологический
                  порядок по «(после N.M)»; цикл и нет tasks.md — RunnerStop
  TC-J64-DPT-002  манифест: per_task только для pi без task_id и verdict
  TC-J64-DPT-003  раннер: пары dev-N → review-N (code_review по задаче) по
                  порядку зависимостей; без review: при зависимостях — STOP на
                  развертке; список фиксируется в state, resume по нему
  TC-J64-DPT-004  файл вердикта пары засчитывается J10 (approved_review_tasks)
  TC-J64-DPT-005  dev закрыл чекбокс сам (per_task с review) — STOP
  TC-J64-DPT-006  цепочка на настоящих проверках ворот: ревью по открытой
                  задаче разрешено; dev следующей — после approve и закрытия
                  чекбокса раннером
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_runner as pr  # noqa: E402
import test_package_runner as tpr  # noqa: E402
from test_package_runner import flow_gates_sandbox  # noqa: E402,F401  (autouse: ворота-заглушки)

TASKS = """# Tasks

- [x] 1.1 модель данных
- [ ] 1.2 API (после 1.3)
- [ ] 1.3 сервис (после 1.1)
- [ ] 2.1 [ops] деплой
- [ ] 2.2 [docs] README
- [ ] 3.1 UI (после 1.2)
- [ ] 6.1 кейсы QA
"""


def _tasks(root: Path, text: str = TASKS, package: str = "add-widget") -> Path:
    p = root / "openspec" / "changes" / package / "tasks.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_per_task_ids(tmp_path):
    """TC-J64-DPT-001."""
    _tasks(tmp_path)
    assert pr.per_task_ids(tmp_path, "add-widget") == ["1.3", "1.2", "3.1"]
    with pytest.raises(pr.RunnerStop, match="нет"):
        pr.per_task_ids(tmp_path, "other-pkg")
    _tasks(tmp_path, "- [ ] 1.1 a (после 1.2)\n- [ ] 1.2 b (после 1.1)\n")
    with pytest.raises(pr.RunnerStop, match="цикл"):
        pr.per_task_ids(tmp_path, "add-widget")
    # зависимость на открытую не-dev или несуществующую задачу — STOP сразу
    for text in ("- [ ] 1.1 a (после 2.1)\n- [ ] 2.1 [ops] деплой\n",
                 "- [ ] 1.1 a (после 9.9)\n"):
        _tasks(tmp_path, text)
        with pytest.raises(pr.RunnerStop, match="вне развертки"):
            pr.per_task_ids(tmp_path, "add-widget")


MANIFEST = """\
# PLAN-add-widget

**Флоу: 1**

```yaml
pipeline:
  package: add-widget
  flow: 1
  stages:
    - id: dev
      run: pi:dev
      zones: [src/**]
      per_task: true
      task: реализовать задачу
```
"""


@pytest.mark.parametrize("extra", ["      task_id: \"1.1\"\n",
                                   "      verdict:\n        file: x.md\n",
                                   "      optional: true\n"])
def test_manifest_per_task_validation(tmp_path, extra):
    """TC-J64-DPT-002."""
    repo = tpr.make_repo(tmp_path)
    plan = tpr.write_plan(repo, MANIFEST.replace("      per_task: true\n",
                                                 "      per_task: true\n" + extra),
                          name="PLAN-add-widget.md")
    with pytest.raises(pr.ManifestError, match="per_task"):
        pr.parse_manifest(plan)


def _runner(tmp_path, monkeypatch, manifest):
    repo = tpr.make_repo(tmp_path)
    _tasks(repo)
    plan = tpr.write_plan(repo, manifest, name="PLAN-add-widget.md")
    calls = []

    def fake_pi(args, cwd, env, timeout):
        calls.append(env.get("PI_ZONE_WRITE", ""))
        return 0, "ok", ""
    monkeypatch.setattr(pr, "run_pi", fake_pi)
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    seen = []
    real_gate_new = pr.gate_new

    def gate_new(s, r, w):
        seen.append((s["id"], s["task_id"], s.get("action")))
        if s.get("verdict"):
            vf = w / s["verdict"]["file"]
            vf.parent.mkdir(parents=True, exist_ok=True)
            vf.write_text("# Ревью\n\n## Вердикт: approve\n", encoding="utf-8")
        return real_gate_new(s, r, w)
    monkeypatch.setattr(pr, "gate_new", gate_new)
    return repo, plan, calls, seen


def test_runner_stops_without_review_when_deps(tmp_path, monkeypatch, capsys):
    """TC-J64-DPT-003: зависимые задачи без review: — STOP на развертке."""
    repo, plan, calls, seen = _runner(tmp_path, monkeypatch, MANIFEST)
    assert pr.cmd_run(plan, dry_run=False) != 0
    assert "review" in capsys.readouterr().err and calls == []


def test_runner_expands_dev_review_pairs(tmp_path, monkeypatch):
    """TC-J64-DPT-003: пары dev-N → review-N по порядку зависимостей;
    resume по списку из state."""
    manifest = MANIFEST.replace("      per_task: true\n",
                                "      per_task: true\n      review: code-reviewer\n")
    repo, plan, calls, seen = _runner(tmp_path, monkeypatch, manifest)
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert seen == [("dev-1.3", "1.3", ""), ("dev-1.3-review", "1.3", "code_review"),
                    ("dev-1.2", "1.2", ""), ("dev-1.2-review", "1.2", "code_review"),
                    ("dev-3.1", "3.1", ""), ("dev-3.1-review", "3.1", "code_review")]
    assert len(calls) == 6
    # чекбоксы закрыл раннер после approve каждой пары (решение 2026-11-11)
    for tid in ("1.3", "1.2", "3.1"):
        assert pr.task_checkbox(repo, "add-widget", tid) == "closed"
    assert pr.task_checkbox(repo, "add-widget", "2.1") == "open"   # [ops] не тронута
    state = json.loads(pr.state_path_for(plan).read_text(encoding="utf-8"))
    assert state["expanded"]["dev"] == ["1.3", "1.2", "3.1"]
    assert state["stages"]["dev"]["status"] == "expanded"
    _tasks(repo, TASKS + "- [ ] 4.1 новая задача\n")
    calls.clear()
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert calls == []


def test_review_file_name_counts_for_j10(tmp_path):
    """TC-J64-DPT-004: файл вердикта пары (review-<задача>-001.md с мета
    Reviewer-Delegation) засчитывается J10 — ворота dev_task следующей
    задачи видят approve зависимости."""
    import flow_check
    sub = pr.expand_per_task({"id": "dev", "kind": "pi", "payload": "dev",
                              "review": "code-reviewer", "task": "t"},
                             ["1.3"], {}, "add-widget")[1]
    vf = tmp_path / sub["verdict"]["file"]
    vf.parent.mkdir(parents=True)
    vf.write_text("# Ревью\nReviewer-Delegation: deleg-0123456789abcdef\n\n"
                  "## Вердикт: approve\n", encoding="utf-8")
    assert "1.3" in flow_check.approved_review_tasks(tmp_path, "add-widget")


def test_dev_closing_checkbox_itself_stops(tmp_path, monkeypatch, capsys):
    """TC-J64-DPT-005: при per_task с review dev не закрывает чекбокс сам."""
    manifest = MANIFEST.replace("      per_task: true\n",
                                "      per_task: true\n      review: code-reviewer\n")
    repo, plan, calls, seen = _runner(tmp_path, monkeypatch, manifest)

    def dev_closes(args, cwd, env, timeout):
        t = Path(cwd) / "openspec/changes/add-widget/tasks.md"
        t.write_text(t.read_text(encoding="utf-8").replace("- [ ] 1.3", "- [x] 1.3"),
                     encoding="utf-8")
        return 0, "ok", ""
    monkeypatch.setattr(pr, "run_pi", dev_closes)
    assert pr.cmd_run(plan, dry_run=False) != 0
    assert "закрыл чекбокс задачи 1.3 сам" in capsys.readouterr().err


def test_chain_passes_real_gate_checks(tmp_path):
    """TC-J64-DPT-006: цепочка dev-1.3 → review-1.3 → dev-1.2 на настоящих
    проверках ворот (flow_state.inspect + check_code_review + _deps_findings,
    J10-evidence) — без заглушек gate_begin."""
    import subprocess
    import flow_state
    import flow_transition as ft
    repo = tmp_path / "proj-chain"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _tasks(repo, "- [ ] 1.3 сервис\n- [ ] 1.2 API (после 1.3)\n")

    def snap(task):
        return flow_state.inspect(repo, "proj", 1, "add-widget", task_id=task)

    def review_findings(task):
        ctx = {"checked": set(), "evidence": set()}
        act = ft.ActionRequest(actor_role="code_reviewer",
                               requested_action="code_review", task_id=task)
        return [f for f in ft.check_code_review(snap(task), act, ctx, 1)]

    def dev_dep_findings(task, deps):
        ctx = {"checked": set(), "evidence": set()}
        act = ft.ActionRequest(actor_role="dev", requested_action="dev_task",
                               task_id=task, task_dependencies=tuple(deps),
                               dependency_evidence=ft._dep_evidence(repo, "add-widget",
                                                                    tuple(deps)))
        return ft._deps_findings(act, ctx)

    # dev-1.3 отработал, чекбокс открыт (бриф раннера) → ревью 1.3 разрешено
    assert review_findings("1.3") == []
    # до approve и закрытия — dev-1.2 ждет зависимость
    assert dev_dep_findings("1.2", ["1.3"])
    # ревью 1.3 approve (штамп раннера) + раннер закрыл чекбокс
    vf = repo / "code-reviews/add-widget/review-1.3-001.md"
    vf.parent.mkdir(parents=True)
    vf.write_text("# Ревью\nReviewer-Delegation: deleg-0123456789abcdef\n\n"
                  "## Вердикт: approve\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    assert pr.close_task_checkbox(repo, "add-widget", "1.3", "close 1.3")
    assert dev_dep_findings("1.2", ["1.3"]) == []          # dev-1.2 проходит
    assert pr.close_task_checkbox(repo, "add-widget", "1.3", "again") is None
