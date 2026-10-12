# -*- coding: utf-8 -*-
"""Тесты J43.1: flow-aware энфорсер + план релиза Флоу 2/4 + память фазы.

Зоны проверок (матрица Заказчика 2026-10-12):
  - flow_transition.plan_release_paths: Флоу 2 — PLAN-BUG-NNN.md в корне ИЛИ
    общий test-model/bugs/PLAN.md (со строкой «Флоу: 2»); Флоу 4 —
    PLAN-<slug>.md в корне; check_bug_fix / check_chore_task требуют план
    (легкий: цель, Флоу-строка, зоны, критерий);
  - flowctl phase: память фазы — последний run scope
    ({action, actor_role, finished_status, timestamp}) или {phase: 'none'};
  - enforcer.SEQUENCE_PREREQS — производная от STAGE_TABLE
    (синхронизация: каждый предшественник есть в таблице флоу и стоит
    РАНЬШЕ действия) + семантика нарушений/допустимых переходов.

Фикстуры — как в test_flow_transition.py; реальный ~/.hermes/state/ не
трогается. Файл отключает autouse-фикстуру PLAN (no_plan_fixture): планы
создаются руками в каждом сценарии.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import enforcer  # noqa: E402

pytestmark = pytest.mark.no_plan_fixture


# --------------------------------------------------------------- helpers


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> None:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-qm", msg)


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def snapshot_for(repo: Path, registry: Path, **kw) -> dict:
    return flow_state.inspect(
        repo_arg=str(repo),
        project=kw.get("project", "proj"),
        flow=kw.get("flow", 1),
        change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"),
        registry=str(registry),
    )


def act(**kw) -> ft.ActionRequest:
    kw.setdefault("actor_role", "dev")
    return ft.ActionRequest(**kw)


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


def flowctl_cmd(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "flowctl.py"), *argv],
                          capture_output=True, text=True)


PLAN_FLOW2 = ("# PLAN — багфиксы\n\n**Флоу: 2** (легкий план: цель, зоны,\n"
              "критерий приемки).\n")
PLAN_FLOW4 = ("# PLAN-chore-cleanup\n\n**Флоу: 4** (легкий план).\n")


# ----------------------------- (п.3) легкий план Флоу 2/4: ворота плана


class TestFlow2PlanGate:
    def _bug_repo(self, tmp_path: Path, *, with_plan: bool = True,
                  shared_plan: bool = False,
                  with_report: bool = True) -> Path:
        repo = tmp_path / "proj"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo,
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo,
                       check=True, capture_output=True)
        if with_report:
            write(repo, "test-model/bugs/BUG-042.md", "# BUG-042\n\nфикс\n")
        write(repo, "openspec/specs/widget/spec.md",
              "### Requirement: W\n#### Scenario: S\n"
              "- GIVEN a\n- WHEN b\n- THEN c\n")
        if with_plan:
            if shared_plan:
                write(repo, "test-model/bugs/PLAN.md", PLAN_FLOW2)
            else:
                write(repo, "PLAN-BUG-042.md", PLAN_FLOW2)
        commit_all(repo)
        return repo

    def test_plan_bug_nnn_in_root_allows(self, tmp_path):
        """TC-J431-001: J43.1 flow-aware."""
        repo = self._bug_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "ALLOW", d.details

    def test_shared_bugs_plan_allows(self, tmp_path):
        """TC-J431-002: Один test-model/bugs/PLAN.md на все баги допустим (содержит
        строку «Флоу: 2» и покрывает)."""
        repo = self._bug_repo(tmp_path, shared_plan=True)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "ALLOW", d.details

    def test_shared_plan_does_not_count_as_bug_report(self, tmp_path):
        """TC-J431-003: J43.1: общий test-model/bugs/PLAN.md делает каталог bugs/ непустым
        (грубый факт test_model.present) — но репорта BUG-NNN нет → DENY."""
        repo = self._bug_repo(tmp_path, with_plan=False, with_report=False)
        write(repo, "test-model/bugs/PLAN.md", PLAN_FLOW2)
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("не считается репортом" in x for x in d.details)

    def test_missing_plan_deny(self, tmp_path):
        """TC-J431-004: J43.1 flow-aware."""
        repo = self._bug_repo(tmp_path, with_plan=False)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_RELEASE_MISSING)
        assert any("test-model" in x and "PLAN" in x for x in d.details)

    def test_plan_without_flow_line_deny(self, tmp_path):
        """TC-J431-005: J43.1 flow-aware."""
        repo = self._bug_repo(tmp_path)
        write(repo, "PLAN-BUG-042.md", "# PLAN без воркфлоу\n\nцель: фикс\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_FLOW_UNDECLARED)

    def test_flow1_plan_paths_do_not_cover_flow2(self, tmp_path):
        """TC-J431-006: PLAN в каталоге change-пакета (легально для Флоу 1) НЕ покрывает
        Флоу 2 — у Флоу 2 свои легальные расположения."""
        repo = self._bug_repo(tmp_path, with_plan=False)
        write(repo, "openspec/changes/BUG-042/PLAN.md", PLAN_FLOW2)
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=2,
                                         change_id="BUG-042"),
                            act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_RELEASE_MISSING)


class TestFlow4PlanGate:
    def _chore_repo(self, tmp_path: Path, *, with_plan: bool = True) -> Path:
        repo = tmp_path / "proj"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo,
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo,
                       check=True, capture_output=True)
        write(repo, "scripts/tool.py", "X = 1\n")
        if with_plan:
            write(repo, "PLAN-chore-cleanup.md", PLAN_FLOW4)
        commit_all(repo)
        return repo

    def test_plan_slug_in_root_allows(self, tmp_path):
        """TC-J431-007: План Флоу 4 закрывает план-ворота: PLAN_RELEASE_MISSING нет.
        (Сам ALLOW для slug дает post-filter энфорсера — prepare при slug
        честно дает UNKNOWN/AMBIGUOUS_STATE о формате scope-id [chore];
        см. test_v_flow4_with_plan_allows_via_no_change_filter.)"""
        repo = self._chore_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=4,
                                         change_id="chore-cleanup"),
                            act(requested_action="chore_task",
                                paths=("scripts/*",)))
        assert not has_code(d, ft.PLAN_RELEASE_MISSING)
        assert not has_code(d, ft.PLAN_FLOW_UNDECLARED)
        assert has_code(d, ft.AMBIGUOUS_STATE)  # scope-id: slug ≠ [chore]

    def test_missing_plan_deny(self, tmp_path):
        """TC-J431-008: J43.1 flow-aware."""
        repo = self._chore_repo(tmp_path, with_plan=False)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, flow=4,
                                         change_id="chore-cleanup"),
                            act(requested_action="chore_task",
                                paths=("scripts/*",)))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_RELEASE_MISSING)
        assert any("PLAN-chore-cleanup.md" in x for x in d.details)

    def test_plan_release_paths_flow4(self, tmp_path):
        """TC-J431-009: J43.1 flow-aware."""
        paths = ft.plan_release_paths(tmp_path, "chore-cleanup", 4)
        assert paths == [tmp_path / "PLAN-chore-cleanup.md"]

    def test_plan_release_paths_flow2(self, tmp_path):
        """TC-J431-010: J43.1 flow-aware."""
        paths = ft.plan_release_paths(tmp_path, "BUG-042", 2)
        assert paths == [tmp_path / "PLAN-BUG-042.md",
                         tmp_path / "test-model" / "bugs" / "PLAN.md"]

    def test_plan_release_paths_flow1_unchanged(self, tmp_path):
        """TC-J431-011: J43.1 flow-aware."""
        paths = ft.plan_release_paths(tmp_path, "add-widget", 1)
        assert paths == [tmp_path / "PLAN-add-widget.md",
                         tmp_path / "openspec" / "changes" / "add-widget" /
                         "PLAN.md"]


# --------------------------------------- (п.4) flowctl phase: память фазы


def write_state(path: Path, runs: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"schema_version": "flowctl-state/1", "runs": runs},
        ensure_ascii=False), encoding="utf-8")


def run(rec_status: str, action: str, scope: dict, ts: str,
        finished: str | None = None) -> dict:
    return {"correlation_id": f"corr-{ts}", "status": rec_status,
            "action": action, "actor_role": "dev",
            "scope": scope, "created_at": ts,
            **({"finished_at": finished} if finished else {})}


SCOPE = {"repo": "/tmp/projX", "project": "proj", "flow": 1,
         "change": "add-widget", "task": None}


class TestPhaseCommand:
    def _phase(self, state: Path, repo: str = SCOPE["repo"]) -> dict:
        r = flowctl_cmd("phase", "--repo", repo,
                        "--project", "proj", "--flow", "1",
                        "--scope", "add-widget", "--state", str(state))
        assert r.returncode == 0, r.stdout + r.stderr
        return json.loads(r.stdout)

    def test_phase_empty(self, tmp_path):
        """TC-J431-012: (е) пустое состояние → {phase: 'none'}."""
        state = tmp_path / "state" / "flowctl_state.json"
        write_state(state, {})
        data = self._phase(state)
        assert data["schema_version"] == "flowctl-phase/1"
        assert data["phase"] == "none"

    def test_phase_after_prepare(self, tmp_path):
        """TC-J431-013: (е) после prepare (record status=prepared, не завершен) — последний
        run возвращается с finished_status=prepared."""
        state = tmp_path / "state" / "flowctl_state.json"
        write_state(state, {"c1": run("prepared", "dev_task", SCOPE,
                                      "2026-10-12T10:00:00+00:00")})
        data = self._phase(state)
        assert data["phase"] == {
            "action": "dev_task", "actor_role": "dev",
            "finished_status": "prepared",
            "timestamp": "2026-10-12T10:00:00+00:00"}
        assert data["completed_actions"] == []  # prepared — не завершен

    def test_phase_after_finish(self, tmp_path):
        """TC-J431-014: (е) после finish accepted — finished_status=accepted, действие в
        completed_actions."""
        state = tmp_path / "state" / "flowctl_state.json"
        write_state(state, {
            "c1": run("accepted", "dev_task", SCOPE,
                      "2026-10-12T10:00:00+00:00",
                      finished="2026-10-12T11:00:00+00:00"),
            "c2": run("returned", "code_review", SCOPE,
                      "2026-10-12T12:00:00+00:00",
                      finished="2026-10-12T13:00:00+00:00"),
        })
        data = self._phase(state)
        assert data["phase"]["action"] == "code_review"  # последний по времени
        assert data["phase"]["finished_status"] == "returned"
        assert set(data["completed_actions"]) == {"dev_task", "code_review"}

    def test_phase_filters_other_scope(self, tmp_path):
        """TC-J431-015: J43.1 flow-aware."""
        state = tmp_path / "state" / "flowctl_state.json"
        other = dict(SCOPE, change="other-change", flow=2)
        write_state(state, {
            "c1": run("accepted", "bug_fix", other, "2026-10-12T10:00:00+00:00",
                      finished="2026-10-12T10:30:00+00:00")})
        data = self._phase(state)
        assert data["phase"] == "none"

    def test_phase_real_prepare_then_phase(self, tmp_path):
        """TC-J431-016: Интеграция: РЕАЛЬНЫЙ prepare (не dry) пишет run в state — phase его
        видит (finished_status=prepared)."""
        from test_flowctl import make_repo  # fixture-репо Флоу 1
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md",
              "# PLAN-add-widget\n\n**Флоу: 1** (интеграционный fixture).\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        state = tmp_path / "state" / "flowctl_state.json"
        r = flowctl_cmd(
            "prepare", "--repo", str(repo), "--project", "proj",
            "--flow", "1", "--change", "add-widget", "--task", "1.1",
            "--action", "dev_task", "--role", "dev", "--path", "src/**",
            "--owner-pm", "pm-main", "--registry", str(reg),
            "--state", str(state), "--correlation-id", "corrphase1")
        assert r.returncode == 0, r.stdout + r.stderr
        data = self._phase(state, repo=str(repo))
        assert data["phase"]["action"] == "dev_task"
        assert data["phase"]["finished_status"] == "prepared"


# ------------------------ (п.4/ж) последовательность: prereqs и STAGE_TABLE


class TestSequencePrereqs:
    def test_sequence_prereqs_match_stage_table(self):
        """TC-J431-017: SEQUENCE_PREREQS — производная STAGE_TABLE: каждое действие и
        предшественник существуют в таблице флоу и предшественник стоит
        РАНЬШЕ действия (механическая синхронизация с flow_transition)."""
        for flow, table in ft.STAGE_TABLE.items():
            order = {s.action: i for i, s in enumerate(table)}
            prereqs = enforcer.SEQUENCE_PREREQS.get(flow, {})
            for action, pre in prereqs.items():
                assert action in order, (flow, action)
                for p in pre:
                    assert p in order, (flow, action, p)
                    assert order[p] < order[action], (flow, action, p)

    def test_every_stage_has_prereq_entry(self):
        """TC-J431-018: J43.1 flow-aware."""
        for flow, table in ft.STAGE_TABLE.items():
            prereqs = enforcer.SEQUENCE_PREREQS.get(flow, {})
            for s in table:
                assert s.action in prereqs, (flow, s.action)

    def test_completed_statuses_mirror_flowctl(self):
        """TC-J431-019: J43.1 flow-aware."""
        sys.path.insert(0, str(SCRIPTS))
        import flowctl
        assert enforcer.COMPLETED_STATUSES == tuple(
            flowctl.PHASE_COMPLETED_STATUSES)

    def test_violation_qa_automation_before_qa_cases(self):
        """TC-J431-020: J43.1 flow-aware."""
        phase = {"phase": "none", "completed_actions": []}
        v = enforcer.sequence_violation(1, "qa_automation", phase)
        assert v and "qa_cases" in v and "SEQUENCE" not in v

    def test_violation_merge_without_review(self):
        """TC-J431-021: J43.1 flow-aware."""
        phase = {"phase": {"action": "dev_task",
                           "finished_status": "accepted"},
                 "completed_actions": ["create_change", "dev_task"]}
        v = enforcer.sequence_violation(1, "merge_task", phase)
        assert v and "accept_review" in v

    def test_allowed_rework_after_returned_review(self):
        """TC-J431-022: Ф1: после code_review с вердиктом return следующий dev_task той же
        задачи допустим (предшественники create_change уже завершены)."""
        phase = {"phase": {"action": "code_review",
                           "finished_status": "returned"},
                 "completed_actions": ["create_change", "dev_task",
                                       "code_review"]}
        assert enforcer.sequence_violation(1, "dev_task", phase) is None

    def test_allowed_new_task_after_merge(self):
        """TC-J431-023: Ф1: после merge_task dev_task новой задачи допустим."""
        phase = {"phase": {"action": "merge_task",
                           "finished_status": "accepted"},
                 "completed_actions": ["create_change", "dev_task",
                                       "code_review", "accept_review",
                                       "merge_task"]}
        assert enforcer.sequence_violation(1, "dev_task", phase) is None

    def test_flow2_bug_fix_first_is_allowed(self):
        """TC-J431-024: J43.1 flow-aware."""
        phase = {"phase": "none", "completed_actions": []}
        assert enforcer.sequence_violation(2, "bug_fix", phase) is None

    def test_flow3_stabilize_then_accept_review(self):
        """TC-J431-025: J43.1 flow-aware."""
        phase = {"phase": {"action": "emergency_stabilize",
                           "finished_status": "accepted"},
                 "completed_actions": ["emergency_stabilize"]}
        assert enforcer.sequence_violation(
            3, "accept_review", phase) is None
        v = enforcer.sequence_violation(3, "merge_task", phase)
        assert v and "accept_review" in v

    def test_unknown_action_and_missing_data_do_not_violate(self):
        """TC-J431-026: J43.1 flow-aware."""
        assert enforcer.sequence_violation(1, "неизвестное", {"phase": "none"}) \
            is None
        assert enforcer.sequence_violation(1, "dev_task", None) is None


class TestSequenceGateEnforcer:
    """sequence_gate энфорсера: env off → нет проверки; on → phase → блок."""

    def _fake_phase(self, monkeypatch, payload: dict) -> list:
        calls: list = []

        def _fake(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(
                [], 0, json.dumps(payload), "")

        monkeypatch.setattr(enforcer.subprocess, "run", _fake)
        return calls

    MARKERS = {"role": "dev", "repo": "/tmp/proj", "scope": "add-widget",
               "task": None, "flow": 1}

    def test_gate_off_by_default(self, monkeypatch):
        """TC-J431-027: J43.1 flow-aware."""
        monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
        calls = self._fake_phase(monkeypatch, {"phase": "none"})
        assert enforcer.sequence_gate(self.MARKERS, 1, "qa_automation",
                                      "t") is None
        assert calls == []  # phase даже не вызывался

    def test_gate_on_blocks_violation(self, monkeypatch):
        """TC-J431-028: J43.1 flow-aware."""
        monkeypatch.setenv("FLOW_ENFORCER_SEQUENCE", "1")
        self._fake_phase(monkeypatch, {"phase": "none",
                                       "completed_actions": []})
        res = enforcer.sequence_gate(self.MARKERS, 1, "qa_automation", "t")
        assert res is not None and res["action"] == "block"
        assert "SEQUENCE_VIOLATION" in res["message"]
        assert "последний завершенный этап" in res["message"]

    def test_gate_on_allows_proper_next(self, monkeypatch):
        """TC-J431-029: J43.1 flow-aware."""
        monkeypatch.setenv("FLOW_ENFORCER_SEQUENCE", "1")
        self._fake_phase(monkeypatch, {
            "phase": {"action": "merge_task",
                      "finished_status": "accepted",
                      "timestamp": "2026-10-12T10:00:00+00:00"},
            "completed_actions": ["create_change", "dev_task", "code_review",
                                  "accept_review", "merge_task"]})
        assert enforcer.sequence_gate(self.MARKERS, 1, "dev_task", "t") is None

    def test_phase_unavailable_fails_open_with_log(
            self, monkeypatch, tmp_path):
        """phase недоступен (битый вывод) → не блок (best-effort), WARNING."""
        monkeypatch.setenv("FLOW_ENFORCER_SEQUENCE", "1")
        monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(tmp_path / "st"))
        monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))

        def _fake(argv, **kw):
            return subprocess.CompletedProcess([], 0, "не JSON", "")

        monkeypatch.setattr(enforcer.subprocess, "run", _fake)
        assert enforcer.sequence_gate(self.MARKERS, 1, "qa_automation",
                                      "t") is None
        log = (tmp_path / "st" / "flow-enforcer.log").read_text("utf-8")
        assert "phase_unavailable" in log and "WARNING" in log
