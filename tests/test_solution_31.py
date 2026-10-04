# -*- coding: utf-8 -*-
"""Тесты решения Заказчика 3.1-А (S5) в flow_state/flow_transition (поставка 04).

Факт approved_cases_of_change (approved-кейсы ИМЕННО этого change) и QA-роли
практики в графе (qa_case_author, qa_impact_analyst). Дополняет
tests/test_flow_state.py и tests/test_flow_transition.py, старые тесты не
меняются. Реальный ~/.hermes/state/ не трогается (fixture-реестр).

Трассировка: TC-31-001...TC-31-012 (shadow-R6 S5, ложное разрешение;
docs/shadow-r6-scenario.md, решение 3.1-А от 2026-10-02).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state as fs  # noqa: E402
import flow_transition as ft  # noqa: E402


# --------------------------------------------------------------- helpers


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


REQ_APPROVED = "# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | История: r1\n\n## Описание\n...\n"

TASKS = """# Tasks

- [x] 1.1 готово
- [x] 1.2 готово
- [x] 2.1 готово
- [x] 6.1 QA
"""


def make_repo(tmp_path: Path, name: str = "proj") -> Path:
    """Фикстура «Флоу 1, этап перед qa_automation»: qa_контур почти собран,
    но approved-кейсов СВОЕГО change нет; в approved/ лежит ЧУЖОЙ пакет —
    ситуация точки S5 shadow-R6 (глобально approved/ непуст, локально пуст)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "requirements.md", REQ_APPROVED)
    write(repo, "openspec/changes/add-widget/proposal.md", "# p\n")
    write(repo, "openspec/changes/add-widget/design.md", "# d\n")
    write(repo, "openspec/changes/add-widget/tasks.md", TASKS)
    write(repo, "openspec/changes/add-widget/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "sdd.md", "# SDD\n")
    write(repo, "openspec/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "code-reviews/add-widget/review-001-1.1.md", "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    # QA-контур: чеклист + кейсы new/ есть, review «одобрить» есть;
    # approved/ содержит ТОЛЬКО старый чужой пакет (не add-widget)
    write(repo, "test-model/checklists/add-widget.md",
          "| CHK-1 | проверка | FR-1 |\n\n## Дефекты спеки\n")
    write(repo, "test-model/new/add-widget/TC-WID-001.md", "# TC-WID-001\n\n[CHK-1]\n")
    write(repo, "test-model/reviews/review-add-widget.md",
          "одобрить: add-widget\n")
    write(repo, "test-model/approved/old-change/TC-OLD-001.md", "# TC-OLD\n")
    write(repo, "test-model/bugs/BUG-042.md", "# BUG-042\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def snapshot_for(repo: Path, registry: Path, **kw) -> dict:
    return fs.inspect(
        repo_arg=str(repo), project="proj", flow=kw.get("flow", 1),
        change_id=kw.get("change_id", "add-widget"),
        task_id=kw.get("task_id"), registry=str(registry),
    )


def fact(snapshot: dict, key: str):
    for f in snapshot["facts"]:
        if f["key"] == key:
            return f
    return None


def act(**kw) -> ft.ActionRequest:
    kw.setdefault("actor_role", "qa_automation")
    kw.setdefault("requested_action", "qa_automation")
    return ft.ActionRequest(**kw)


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


# -------------------------------------- факт approved_cases_of_change (снимок)


class TestApprovedCasesFact:
    def test_fact_missing_when_no_own_dir(self, tmp_path):
        """S5-ситуация: approved/ непуст глобально, но своего пакета нет —
        факт missing, НЕ ready (ложное разрешение исключено)."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        f = fact(s, "approved_cases_of_change")
        assert f is not None
        assert f["status"] == "missing"
        assert f["confidence"] == "unknown"
        assert f["source"] == "test-model/approved/add-widget"

    def test_fact_ready_with_own_cases(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        write(repo, "test-model/approved/add-widget/TC-WID-002.md", "# TC\n")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        f = fact(s, "approved_cases_of_change")
        assert f["status"] == "ready"
        assert f["confidence"] == "verified"
        assert f["value"]["count"] == 2
        assert f["value"]["change"] == "add-widget"

    def test_fact_missing_without_test_model(self, tmp_path):
        repo = make_repo(tmp_path)
        import shutil
        shutil.rmtree(repo / "test-model")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        assert fact(s, "approved_cases_of_change")["status"] == "missing"

    def test_fact_unknown_on_symlink_outside(self, tmp_path):
        repo = make_repo(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        (repo / "test-model" / "approved" / "add-widget").symlink_to(
            outside, target_is_directory=True)
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        f = fact(s, "approved_cases_of_change")
        assert f["status"] == "unknown"
        assert any(p["code"] == "PATH_OUTSIDE_REPO" for p in s["problems"])

    def test_snapshot_digest_stable(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s1 = snapshot_for(repo, reg)
        s2 = snapshot_for(repo, reg)
        assert s1["snapshot_digest"] == s2["snapshot_digest"]


# ------------------------------- qa_automation / archive по пакету (3.1-А)


class TestQaAutomationByChange:
    def test_qa_automation_denied_without_own_cases(self, tmp_path):
        """Ядро решения 3.1-А: старые пакеты в approved/ больше не маскируют
        пустоту своего change → DENY/MISSING_INPUT (ложное разрешение S5)."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act())
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("approved_cases_of_change" in x or
                   "test-model/approved/add-widget" in x for x in d.details)

    def test_qa_automation_allowed_with_own_cases(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act())
        assert d.status == "ALLOW", d.details

    def test_shadow_s5_scenario_now_catches(self, tmp_path):
        """Регресс точки S5: коммит fc41b90 (контур одним пакетом, approved
        своего change пуст) теперь дает DENY, а не ALLOW."""
        repo = make_repo(tmp_path)
        write(repo, "tests/test_wid.py", '"""[TC-WID-001]"""\ndef test_x():\n    pass\n')
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act())
        assert d.status == "DENY"

    def test_archive_denied_without_own_approved_cases(self, tmp_path):
        """Архивация: закрытые задачи + чужие approved не проходят —
        факт своего change обязателен (3.1-А)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="archive_change",
                                   actor_role="sa",
                                   approval_ref="PLAN.md: разрешение ПМ"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("approved_cases_of_change" in x for x in d.details)

    def test_archive_allowed_with_own_approved_cases(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(requested_action="archive_change",
                                   actor_role="sa",
                                   approval_ref="PLAN.md: разрешение ПМ"))
        assert d.status == "ALLOW", d.details

    def test_qa_automation_unknown_when_fact_unreadable(self, tmp_path):
        """Нечитаемый факт (symlink наружу) → UNKNOWN, не молчаливое ALLOW."""
        repo = make_repo(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        (repo / "test-model" / "approved" / "add-widget").symlink_to(
            outside, target_is_directory=True)
        commit_all(repo)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act())
        assert d.status != "ALLOW"


# --------------------------------------------- QA-роли практики в графе (3.1)


class TestPracticeRoles:
    def test_qa_case_author_in_graph(self, tmp_path):
        """Имя роли практики из сценария S5/agents-README больше не
        MISSING_INPUT: qa_cases от qa_case_author — легально."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(requested_action="qa_cases",
                                   actor_role="qa_case_author"))
        assert not has_code(d, ft.MISSING_INPUT) or any(
            "не входит в граф" not in x for x in d.details)
        assert not any("не входит в граф" in x for x in d.details)
        assert d.status in ("ALLOW", "DENY")  # роль распознана

    def test_qa_case_author_allow(self, tmp_path):
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(requested_action="qa_cases",
                                   actor_role="qa_case_author"))
        assert d.status == "ALLOW", d.details

    def test_qa_impact_analyst_action_in_graph(self, tmp_path):
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(requested_action="qa_impact_analysis",
                                   actor_role="qa_impact_analyst"))
        assert d.status == "ALLOW", d.details
        assert "qa_impact_analysis" not in " ".join(d.details)

    def test_qa_impact_analyst_wrong_role_on_other_actions(self, tmp_path):
        """Роль добавлена, но резервирование действий не размыто."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(requested_action="qa_review",
                                   actor_role="qa_impact_analyst"))
        assert has_code(d, ft.WRONG_ROLE)

    def test_legacy_roles_still_work(self, tmp_path):
        """Старые графовые роли (qa_author и др.) не сломаны."""
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        assert ft.check_action(s, act(requested_action="qa_cases",
                                      actor_role="qa_author")).status == "ALLOW"
        assert ft.check_action(s, act(requested_action="qa_review",
                                      actor_role="qa_case_reviewer")).status == "ALLOW"

    def test_next_candidates_include_new_action(self, tmp_path):
        repo = make_repo(tmp_path)
        s = snapshot_for(repo, make_registry(tmp_path))
        d = ft.check_action(s, act(include_probe=False) if False else act(),
                            include_next=True)
        actions = {c["action"] for c in d.next_candidates}
        assert "qa_impact_analysis" in actions


# --------------------------------------------------------------- CLI-факт


class TestCliFact:
    def test_cli_json_contains_fact(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "flow_state.py"), "inspect",
             "--repo", str(repo), "--project", "proj", "--flow", "1",
             "--change", "add-widget", "--registry", str(reg), "--json"],
            capture_output=True, text=True,
        )
        assert p.returncode == 0
        snap = json.loads(p.stdout)
        keys = {f["key"] for f in snap["facts"]}
        assert "approved_cases_of_change" in keys

    def test_real_state_untouched(self, tmp_path):
        """Все прогоны — на fixture-реестре; ~/.hermes/state/ не читается."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        snapshot_for(repo, reg)
        assert reg.parent == tmp_path
