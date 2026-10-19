# -*- coding: utf-8 -*-
"""Тесты J42: push-политика сабагентских веток (L2 CI-триггер + L4 enforcer).

L2 (.github/workflows/flow.yml): push-триггер `pipeline/**` + финальный
падающий шаг job `flow` (::error:: «сабагентская ветка ... не прошла
ворота — открой PR») при голом пуше ветки без открытого PR.

L4 (plugins/flow-enforcer/enforcer.py): в контексте активной делегации
(flow-aware, как J43.1) хук перехватывает Bash git push и разрешает только
push в ветку из ALLOW-объекта (session['branch']; формы `origin <branch>` /
`HEAD:<branch>`); push main / чужой ветки / тегов / удаление → DENY
[PUSH_POLICY]; вне делегации (ПМ) и при отсутствии branch в ALLOW —
прежнее поведение (пропуск).

Трассировка: TC-J42-001..014 — парсер parse_git_push (секция
«парсер git push»); TC-J42-015..029 — хук flow_enforce (секция
«хук (L4)»); TC-J42-030..032 — .github/workflows/flow.yml (секция
«L2: flow.yml»). Нумерация сквозная в порядке объявления.

Фикстуры: tmp-реестр, tmp-репозиторий/worktree, tmp-каталог логов —
реальный ~/.hermes/state/ не используется.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402

BRANCH = "pipeline/j42-push-policy"


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи/реестр в tmp."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(state / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    for var in ("FLOW_ENFORCER_PUSH", "FLOW_ENFORCER_FLOW",
                "FLOW_ENFORCER_SEQUENCE", "FLOW_ENFORCER_PROJECT"):
        monkeypatch.delenv(var, raising=False)
    yield state


@pytest.mark.no_plan_fixture
def make_session(tmp_path, with_worktree=False, branch=BRANCH, status="running"):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    s = {"delegation_id": "deleg-j42", "repo": str(repo), "status": status,
         "role": "dev", "branch": branch, "worktree": None}
    if with_worktree:
        wt = tmp_path / "repo-worktrees" / "deleg-j42"
        wt.mkdir(parents=True, exist_ok=True)
        s["worktree"] = str(wt)
    return s


def write_registry(tmp_path, sessions):
    path = Path(enforcer.worktree_registry_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"schema_version": "active-sessions/2", "sessions": sessions},
        ensure_ascii=False), encoding="utf-8")
    return path


def hook(command, **extra):
    args = {"command": command}
    args.update(extra)
    return enforcer.flow_enforce("Bash", args, task_id="t1")


# ----------------------------------------------------------- парсер git push


@pytest.mark.no_plan_fixture
class TestParseGitPush:
    def test_not_push(self):
        """TC-J42-001: не git push → None (команда игнорируется)."""
        assert enforcer.parse_git_push("git status") is None
        assert enforcer.parse_git_push("ls -la") is None
        assert enforcer.parse_git_push("git pushx") is None

    def test_origin_branch_allowed_form(self):
        """TC-J42-002: форма `git push origin <branch>` → dst=<branch>, reason=None."""
        p = enforcer.parse_git_push(f"git push origin {BRANCH}")
        assert p["reason"] is None and p["dst"] == BRANCH

    def test_head_branch_form(self):
        """TC-J42-003: форма `git push origin HEAD:<branch>` → dst=<branch>, reason=None."""
        p = enforcer.parse_git_push(f"git push origin HEAD:{BRANCH}")
        assert p["reason"] is None and p["dst"] == BRANCH

    def test_refs_heads_normalized(self):
        """TC-J42-004: refs/heads/<branch> нормализуется в <branch>, reason=None."""
        p = enforcer.parse_git_push(f"git push origin refs/heads/{BRANCH}")
        assert p["reason"] is None and p["dst"] == BRANCH

    def test_force_and_upstream_flags(self):
        """TC-J42-005: флаги --force/-f/-u/--set-upstream не мешают разбору, reason=None."""
        for cmd in (f"git push --force origin {BRANCH}",
                    f"git push -f origin {BRANCH}",
                    f"git push -u origin {BRANCH}",
                    f"git push --set-upstream origin {BRANCH}"):
            p = enforcer.parse_git_push(cmd)
            assert p["reason"] is None and p["dst"] == BRANCH, cmd

    def test_git_dash_c_repo(self):
        """TC-J42-006: git -C <repo> push → извлекается repo и dst."""
        p = enforcer.parse_git_push(f"git -C /tmp/x push origin {BRANCH}")
        assert p["repo"] == "/tmp/x" and p["dst"] == BRANCH

    def test_main_is_parsed_for_deny(self):
        """TC-J42-007: push в main парсится (dst=main) — DENY решает хук, не парсер."""
        p = enforcer.parse_git_push("git push origin main")
        assert p["reason"] is None and p["dst"] == "main"

    def test_bare_push_unverifiable(self):
        """TC-J42-008: голый `git push` / `git push origin` без refspec → reason (непроверяемо)."""
        assert enforcer.parse_git_push("git push")["reason"]
        assert enforcer.parse_git_push("git push origin")["reason"]

    def test_bare_head_unverifiable(self):
        """TC-J42-009: `git push origin HEAD` без суффикса ветки → reason (непроверяемо)."""
        assert enforcer.parse_git_push("git push origin HEAD")["reason"]

    def test_tag_refs_deny(self):
        """TC-J42-010: refs/tags/v1.2.3 → reason с «тегов»."""
        p = enforcer.parse_git_push("git push origin refs/tags/v1.2.3")
        assert p["reason"] and "тегов" in p["reason"]

    def test_delete_refspec_deny(self):
        """TC-J42-011: refspec `:<branch>` → reason с «удаление»."""
        p = enforcer.parse_git_push(f"git push origin :{BRANCH}")
        assert p["reason"] and "удаление" in p["reason"]

    def test_delete_and_mass_opts_deny(self):
        """TC-J42-012: --delete/--mirror/--all/--tags → reason (удаление/массовые пуши)."""
        for cmd in (f"git push --delete origin {BRANCH}",
                    "git push --mirror", "git push --all",
                    "git push --tags"):
            assert enforcer.parse_git_push(cmd)["reason"], cmd

    def test_multiple_refspecs_deny(self):
        """TC-J42-013: два refspec в одной команде → reason."""
        p = enforcer.parse_git_push(f"git push origin {BRANCH} other")
        assert p["reason"]

    def test_dry_run_neutral(self):
        """TC-J42-014: --dry-run помечает dry_run=True, reason=None (нейтрально)."""
        p = enforcer.parse_git_push(f"git push --dry-run origin main")
        assert p["dry_run"] and p["reason"] is None


# ---------------------------------------------------------------- хук (L4)


@pytest.mark.no_plan_fixture
class TestPushGateHook:
    def test_intercepts_bash_push(self, tmp_path):
        """TC-J42-015: активная делегация: git push origin main → block с «push-политика J42» и ALLOW-веткой в сообщении."""
        write_registry(tmp_path, [make_session(tmp_path)])
        res = hook(f"git push origin main", cwd=str(tmp_path / "repo"))
        assert res and res["action"] == "block"
        assert "push-политика J42" in res["message"]
        assert f"только ветка {BRANCH} из ALLOW" in res["message"]

    def test_allow_branch_ok(self, tmp_path):
        """TC-J42-016: push в ветку из ALLOW (`origin <branch>` и `HEAD:<branch>`) → None (пропуск)."""
        write_registry(tmp_path, [make_session(tmp_path)])
        assert hook(f"git push origin {BRANCH}",
                    cwd=str(tmp_path / "repo")) is None
        assert hook(f"git push origin HEAD:{BRANCH}",
                    cwd=str(tmp_path / "repo")) is None

    def test_main_denied(self, tmp_path):
        """TC-J42-017: push origin main → block, PUSH_POLICY в сообщении."""
        write_registry(tmp_path, [make_session(tmp_path)])
        res = hook("git push origin main", cwd=str(tmp_path / "repo"))
        assert res and res["action"] == "block" and "PUSH_POLICY" in res["message"]

    def test_foreign_branch_denied(self, tmp_path):
        """TC-J42-018: push в чужую ветку pipeline/other-task → block."""
        write_registry(tmp_path, [make_session(tmp_path)])
        res = hook("git push origin pipeline/other-task",
                   cwd=str(tmp_path / "repo"))
        assert res and res["action"] == "block"

    def test_tag_denied(self, tmp_path):
        """TC-J42-019: push тега v1.0.0 → block."""
        write_registry(tmp_path, [make_session(tmp_path)])
        res = hook("git push origin v1.0.0", cwd=str(tmp_path / "repo"))
        assert res and res["action"] == "block"

    def test_composite_command_denied(self, tmp_path):
        """TC-J42-020: составная команда с push разрешённой ветки + main → block."""
        write_registry(tmp_path, [make_session(tmp_path)])
        res = hook(f"cd {tmp_path / 'repo'} && git push origin {BRANCH} "
                   "&& git push origin main")
        assert res and res["action"] == "block"

    def test_non_push_command_passes(self, tmp_path):
        """TC-J42-021: Bash без git push (status && commit) → None."""
        write_registry(tmp_path, [make_session(tmp_path)])
        assert hook("git status && git commit -am x",
                    cwd=str(tmp_path / "repo")) is None

    def test_outside_delegation_passes(self, tmp_path):
        """TC-J42-022: вне делегации (реестр пуст / отсутствует) push main → None (прежнее поведение)."""
        # ПМ: ни одной активной делегации → не блокировать.
        write_registry(tmp_path, [])
        assert hook("git push origin main") is None
        # реестра нет вовсе → тоже.
        (tmp_path / "state" / "active_sessions.json").unlink(missing_ok=True)
        assert hook("git push origin main") is None

    def test_inactive_status_passes(self, tmp_path):
        """TC-J42-023: статусы finished/stale/completed → делегация неактивна, push main → None."""
        for status in ("finished", "stale", "completed"):
            write_registry(tmp_path,
                           [make_session(tmp_path, status=status)])
            assert hook("git push origin main") is None, status

    def test_degradation_no_allow_branch_passes(self, tmp_path):
        """TC-J42-024: делегация активна, но branch=None в ALLOW → пропуск (деградация)."""
        # Деградация: делегация активна, но branch в ALLOW-объекте нет —
        # прежнее поведение (пропуск).
        write_registry(tmp_path, [make_session(tmp_path, branch=None)])
        assert hook("git push origin main",
                    cwd=str(tmp_path / "repo")) is None

    def test_worktree_delegation_pm_tree_passes(self, tmp_path):
        """TC-J42-025: ПМ в главном дереве при worktree-делегации → None (не контекст делегации)."""
        # ПМ в главном дереве repo при активной worktree-делегации —
        # не в контексте делегации (сабагент работает в worktree).
        write_registry(tmp_path, [make_session(tmp_path, with_worktree=True)])
        assert hook("git push origin main",
                    cwd=str(tmp_path / "repo")) is None

    def test_worktree_delegation_in_worktree_enforced(self, tmp_path):
        """TC-J42-026: сабагент в worktree: push main → block, push ALLOW-ветки → None."""
        s = make_session(tmp_path, with_worktree=True)
        write_registry(tmp_path, [s])
        wt = s["worktree"]
        res = hook("git push origin main", cwd=wt)
        assert res and res["action"] == "block"
        assert hook(f"git push origin {BRANCH}", cwd=wt) is None

    def test_disable_env(self, tmp_path, monkeypatch):
        """TC-J42-027: FLOW_ENFORCER_PUSH=0 отключает проверку → None."""
        write_registry(tmp_path, [make_session(tmp_path)])
        monkeypatch.setenv("FLOW_ENFORCER_PUSH", "0")
        assert hook("git push origin main",
                    cwd=str(tmp_path / "repo")) is None

    def test_other_tools_pass(self, tmp_path):
        """TC-J42-028: инструмент не Bash (Read) → проверка не применяется, None."""
        write_registry(tmp_path, [make_session(tmp_path)])
        assert enforcer.flow_enforce(
            "Read", {"command": "git push origin main"}) is None

    def test_delegate_task_still_validated(self, tmp_path, monkeypatch):
        """TC-J42-029: регресс J43: delegate_task без маркеров → block MARKERS_MISSING; Bash без push → None."""
        # Регресс J43: delegate_task продолжает обрабатываться (strict-mode
        # блок без маркеров), а Bash без git push — без директивы.
        monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
        res = enforcer.flow_enforce("delegate_task", {"goal": "no markers"})
        assert res and res["action"] == "block" and "MARKERS_MISSING" in res["message"]
        write_registry(tmp_path, [make_session(tmp_path)])
        assert hook("git status", cwd=str(tmp_path / "repo")) is None


# ------------------------------------------------------------- L2: flow.yml


@pytest.mark.no_plan_fixture
class TestWorkflowPushTrigger:
    @staticmethod
    def _workflow():
        return yaml.safe_load(
            (FACTORY / ".github" / "workflows" / "flow.yml").read_text(
                encoding="utf-8"))

    def test_push_trigger_includes_pipeline(self):
        """TC-J42-030: flow.yml: push-триггер содержит main и pipeline/**, pull_request сохранен."""
        data = self._workflow()
        on_section = data.get("on") or data.get(True)  # PyYAML: on → True
        assert on_section is not None
        branches = on_section["push"]["branches"]
        assert "main" in branches
        assert "pipeline/**" in branches
        assert "pull_request" in on_section  # PR-прогон сохранен как есть

    def test_jobs_unchanged_for_push(self):
        """TC-J42-031: job flow/test-flow-control на месте, шаги Validate specs и Flow check сохранены."""
        data = self._workflow()
        assert set(data["jobs"]) >= {"flow", "test-flow-control"}
        steps = [s.get("name", "") for s in data["jobs"]["flow"]["steps"]]
        assert any("Validate specs" in s for s in steps)
        assert any("Flow check" in s for s in steps)

    def test_final_step_fails_bare_pipeline_push(self):
        """TC-J42-032: финальный шаг J42: if push+pipeline/, ::error:: «не прошла ворота — открой PR», gh pr list."""
        data = self._workflow()
        steps = data["jobs"]["flow"]["steps"]
        gate = [s for s in steps if "J42" in s.get("name", "")]
        assert gate, "финальный шаг J42 в job flow отсутствует"
        step = gate[-1]
        cond = step.get("if", "")
        assert "push" in cond and "pipeline/" in cond
        run = step.get("run", "")
        assert "::error::" in run
        assert "не прошла ворота — открой PR" in run
        assert "gh pr list" in run  # проверка ОТКРЫТОГО PR по голове ветки
