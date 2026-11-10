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
        # ревьюер под-стадии пишет вердикт по задаче (файл из манифеста)
        for f in Path(cwd).glob("AGENTS*.md"):
            pass
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
