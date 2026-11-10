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
  TC-J64-DPT-003  раннер: под-стадия на задачу с task_id, по порядку, pi —
                  по разу на задачу; список фиксируется в state, resume не
                  переразворачивает и пропускает выполненные
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
                                   "      verdict:\n        file: x.md\n"])
def test_manifest_per_task_validation(tmp_path, extra):
    """TC-J64-DPT-002."""
    repo = tpr.make_repo(tmp_path)
    plan = tpr.write_plan(repo, MANIFEST.replace("      per_task: true\n",
                                                 "      per_task: true\n" + extra),
                          name="PLAN-add-widget.md")
    with pytest.raises(pr.ManifestError, match="per_task"):
        pr.parse_manifest(plan)


def test_runner_expands_per_task(tmp_path, monkeypatch, capsys):
    """TC-J64-DPT-003."""
    repo = tpr.make_repo(tmp_path)
    _tasks(repo)
    plan = tpr.write_plan(repo, MANIFEST, name="PLAN-add-widget.md")
    calls = []
    monkeypatch.setattr(pr, "run_pi", lambda args, cwd, env, timeout:
                        (calls.append(1), (0, "ok", ""))[1])
    monkeypatch.setattr(pr, "ensure_worktree", lambda repo_, sid, br: repo_)
    seen = []
    real_gate_new = pr.gate_new
    monkeypatch.setattr(pr, "gate_new", lambda s, r, w: (
        seen.append((s["id"], s["task_id"])), real_gate_new(s, r, w))[1])
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert seen == [("dev-1.3", "1.3"), ("dev-1.2", "1.2"), ("dev-3.1", "3.1")]
    assert len(calls) == 3
    state = json.loads(pr.state_path_for(plan).read_text(encoding="utf-8"))
    assert state["expanded"]["dev"] == ["1.3", "1.2", "3.1"]
    assert state["stages"]["dev"]["status"] == "expanded"
    # resume: список из state, выполненные под-стадии пропускаются
    _tasks(repo, TASKS + "- [ ] 4.1 новая задача\n")
    calls.clear()
    assert pr.cmd_run(plan, dry_run=False) == 0
    assert calls == []
