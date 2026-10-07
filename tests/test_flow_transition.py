# -*- coding: utf-8 -*-
"""Тесты scripts/flow_transition.py (поставка 03: check_action, правила Флоу 1–5).

Табличные тесты (design D6): fixture-снимки × действие × ожидаемый status/код,
без subprocess; CLI-тесты — отдельно, exit 0/1/2. Реальный ~/.hermes/state/ не
трогается — реестр сессий всегда fixture-файл; ничего не пишется в репозиторий
(shadow, NFR-3). Парсеры flow_check переиспользуются импортом (D1), поэтому
зависимости задач в тестах проверяются через реальный _dep_evidence на
fixture-репозитории.

Трассировка: TC-FTR-001...TC-FTR-024 (спека deterministic-flow, Requirements
«Разрешение действия», «Порядок флоу 1–5», «Этапные ворота Заказчика», «Честная
граница enforcement», «Provenance review», «Режим shadow»; ТЗ
docs/chatgpt-deterministic-flow/03-transitions.md).
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

import flow_check  # noqa: E402
import flow_state  # noqa: E402
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
REQ_DRAFT = REQ_APPROVED.replace("УТВЕРЖДЕН", "ЧЕРНОВИК")

TASKS = """# Tasks

- [x] 1.1 готово
- [ ] 1.2 [P] параллельная
- [ ] 2.1 (после 1.1) зависимая
- [ ] 3.1 (после 1.2) поздняя
- [ ] 6.1 QA-задача
"""


def make_repo(
    tmp_path: Path,
    *,
    req: str | None = REQ_APPROVED,
    change_id: str = "add-widget",
    tasks: str | None = TASKS,
    with_review: bool = True,
    with_sdd: bool = True,
    with_deltas: bool = True,
    with_specs: bool = True,
) -> Path:
    """Fixture-репозиторий Флоу 1 на этапе «dev»: everything до dev_task."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    if req:
        write(repo, "requirements.md", req)
    write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
    write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
    if tasks:
        write(repo, f"openspec/changes/{change_id}/tasks.md", tasks)
    if with_deltas:
        write(
            repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
            "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n",
        )
    if with_review:
        write(repo, f"code-reviews/{change_id}/review-001-1.1.md", "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    if with_sdd:
        write(repo, "sdd.md", "# SDD\n")
    if with_specs:
        write(repo, "openspec/specs/widget/spec.md",
              "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "test-model/checklists/add-widget.md",
          "| CHK-1 | проверка | FR-1 |\n\n## Дефекты спеки\n")
    write(repo, "test-model/new/add-widget/TC-WID-001.md",
          "# TC-WID-001\n\n[CHK-1]\n")
    write(repo, "test-model/bugs/BUG-042.md", "# BUG-042\n")
    commit_all(repo)
    return repo


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
    kw.setdefault("requested_action", "dev_task")
    return ft.ActionRequest(**kw)


def codes(d: ft.Decision) -> list[str]:
    return d.blocking_reasons


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


# ------------------------------------------------- TC-FTR-001: структура Decision


class TestDecisionShape:
    def test_decision_fields(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        for key in ("allowed", "status", "action", "scope", "actor_role",
                    "snapshot_digest", "requirements_checked",
                    "blocking_reasons", "required_gates", "evidence_refs",
                    "next_candidates"):
            assert key in d.to_dict(), key
        assert d.status == "ALLOW"
        assert d.allowed is True
        assert d.snapshot_digest == s["snapshot_digest"]
        assert d.scope["flow"] == 1

    def test_purity_no_mutation(self, tmp_path):
        """Чистота: snapshot и action не мутируются, повтор — тот же результат."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        before = json.dumps(s, sort_keys=True, ensure_ascii=False)
        a = act(task_id="1.2")
        d1 = ft.check_action(s, a)
        d2 = ft.check_action(s, a)
        assert d1.status == d2.status == "ALLOW"
        assert json.dumps(s, sort_keys=True, ensure_ascii=False) == before


# ------------------------------------------- TC-FTR-002/003: вход, stale, unknown


class TestInputValidation:
    def test_stale_snapshot(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(
            s, act(task_id="1.2", expected_snapshot_digest="deadbeef" * 8))
        assert d.status == "DENY"
        assert has_code(d, ft.STALE_SNAPSHOT)

    def test_unknown_action(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="fly_to_mars"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)

    def test_missing_role_action(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(actor_role="", requested_action=""))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)

    def test_unrecognized_snapshot_unknown(self, tmp_path):
        d = ft.check_action({"schema_version": "other/9"}, act())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.AMBIGUOUS_STATE)

    def test_unknown_flow(self, tmp_path):
        s = {"schema_version": flow_state.SCHEMA_VERSION,
             "scope": {"flow": 9, "project": "p", "change": "x-y"},
             "facts": [], "problems": [], "snapshot_digest": "d"}
        d = ft.check_action(s, act())
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.AMBIGUOUS_STATE)

    def test_flow_id_mismatch_ambiguous(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=2, change_id="add-widget")
        d = ft.check_action(s, act(requested_action="bug_fix"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.AMBIGUOUS_STATE)


# --------------------------------- TC-FTR-004: Флоу 1, разрешенный путь и пропуски


class TestFlow1:
    def test_happy_path_dev_task(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "ALLOW"
        assert "flow_check" in " ".join(d.required_gates)

    def test_dev_before_arch_review(self, tmp_path):
        """Спека: Dev до архитектурного ревью → DENY/INVALID_GATE."""
        repo = make_repo(tmp_path, with_sdd=False)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("architecture review" in x for x in d.details)

    def test_dev_without_change_package(self, tmp_path):
        repo = make_repo(tmp_path, change_id="add-widget")
        import shutil
        shutil.rmtree(repo / "openspec" / "changes" / "add-widget")
        commit_all(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)

    def test_unapproved_requirements_blocks_dev(self, tmp_path):
        repo = make_repo(tmp_path, req=REQ_DRAFT)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("requirements.md" in x for x in d.details)

    def test_qa_chain_order(self, tmp_path):
        """QA не сводится к одной булевой: чеклист → кейсы → ревью → автотесты."""
        import shutil
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)

        s = snapshot_for(repo, reg)
        assert ft.check_action(
            s, act(requested_action="qa_checklist", actor_role="qa_checklist")
        ).status == "ALLOW"

        # кейсы без чеклиста → DENY
        repo2 = make_repo(tmp_path / "b")
        (repo2 / "test-model" / "checklists" / "add-widget.md").unlink()
        commit_all(repo2)
        s2 = snapshot_for(repo2, reg)
        d2 = ft.check_action(s2, act(requested_action="qa_cases",
                                     actor_role="qa_author"))
        assert d2.status == "DENY" and has_code(d2, ft.INVALID_GATE)

        # автотесты без approved → DENY (approved-каталога нет вообще)
        repo4 = make_repo(tmp_path / "d")
        import shutil as _sh
        _sh.rmtree(repo4 / "test-model" / "approved", ignore_errors=True)
        s4 = snapshot_for(repo4, reg)
        d4 = ft.check_action(s4, act(requested_action="qa_automation",
                                     actor_role="qa_automation"))
        assert d4.status == "DENY" and has_code(d4, ft.INVALID_GATE)

    def test_archive_blocked_by_open_tasks(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(
            s, act(requested_action="archive_change", actor_role="integrator",
                   approval_ref="PLAN.md: разрешение ПМ"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("open=" in x for x in d.details)

    def test_archive_requires_pm_permission(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        # закрыть все dev-задачи + QA-контур
        write(repo, f"openspec/changes/add-widget/tasks.md",
              "- [x] 1.1\n- [x] 1.2\n- [x] 2.1\n- [x] 6.1\n")
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo)
        s = snapshot_for(repo, reg)
        d = ft.check_action(
            s, act(requested_action="archive_change", actor_role="integrator",
                   approval_ref="PLAN.md: разрешение ПМ на архивацию"))
        assert d.status == "ALLOW"

    def test_archive_by_sa_is_legal_role(self, tmp_path):
        """Решение Заказчика 3.3 (S7, 2026-10-02): archive_change от sa —
        легальная роль (контракт 7: автор спек сливает дельты), не WRONG_ROLE."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        write(repo, "openspec/changes/add-widget/tasks.md",
              "- [x] 1.1\n- [x] 1.2\n- [x] 2.1\n- [x] 6.1\n")
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo)
        s = snapshot_for(repo, reg)
        d = ft.check_action(
            s, act(requested_action="archive_change", actor_role="sa",
                   approval_ref="PLAN.md: разрешение ПМ на архивацию"))
        assert d.status == "ALLOW"
        assert not has_code(d, ft.WRONG_ROLE)

    def test_archive_wrong_role_still_denied(self, tmp_path):
        """Обратная сторона 3.3: чужие роли (pm, dev) на архивации по-прежнему
        WRONG_ROLE — расширение легальных ролей не размывает резервирование."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        for role in ("pm", "dev"):
            d = ft.check_action(
                s, act(requested_action="archive_change", actor_role=role,
                       approval_ref="PLAN.md: разрешение ПМ на архивацию"))
            assert d.status == "DENY", role
            assert has_code(d, ft.WRONG_ROLE), role

    def test_release_requires_approval_and_closed_change(self, tmp_path):
        """Решение Заказчика 3.2 (S6, 2026-10-02): граф не меняется — release
        строго после archive_change (практика Р6 признана нарушением порядка).
        Негативный: release при незакрытом change → DENY/INVALID_GATE,
        даже с approval_ref."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="release", actor_role="pm"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert has_code(d, ft.INVALID_GATE)

        s2 = snapshot_for(repo, reg)
        d2 = ft.check_action(
            s2, act(requested_action="release", actor_role="pm",
                    approval_ref="чат-лог: «погнали» 2026-10-02"))
        # P0.4: строковый ref не из журнала решений решением не считается →
        # HUMAN_APPROVAL_REQUIRED остается вместе с INVALID_GATE.
        assert d2.status == "DENY"
        assert has_code(d2, ft.INVALID_GATE)
        assert has_code(d2, ft.HUMAN_APPROVAL_REQUIRED)


# --------------------------------------- TC-FTR-005: роли (спека «Чужая роль»)


class TestRoles:
    def test_wrong_role_dev_task(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(actor_role="code_reviewer", task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)

    def test_pm_cannot_merge(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.1")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="pm", task_id="1.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)

    def test_accept_review_wrong_role(self, tmp_path):
        """Чужая роль + provenance: DENY-код роли доминирует, пометка остаётся."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.1")
        d = ft.check_action(s, act(requested_action="accept_review",
                                   actor_role="dev", task_id="1.1"))
        assert d.status == "DENY"
        assert has_code(d, ft.WRONG_ROLE)
        assert has_code(d, ft.STALE_EVIDENCE)


# --------------------------- TC-FTR-006: этапные ворота Заказчика (HUMAN_APPROVAL)


class TestCustomerGates:
    def test_create_change_without_decision(self, tmp_path):
        """Спека: Старт нового change без решения → DENY/HUMAN_APPROVAL_REQUIRED."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_create_change_with_decision_log_record(self, tmp_path):
        """P0.4: строковый approval_ref = decision_id валидной записи журнала
        решений decisions/<YYYY-MM-DD>-<slug>.md → ворота исполнены
        («решение зафиксировано»)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")  # SHA на момент решения
        write(repo, "decisions/2026-10-02-start-add-widget.md",
              "# Решение: старт add-widget\n\n"
              "```decision-record\n"
              "{\n"
              "  \"schema_version\": \"decision-record/1\",\n"
              "  \"decision_id\": \"2026-10-02-start-add-widget\",\n"
              "  \"date\": \"2026-10-02\",\n"
              "  \"scope\": {\"project\": \"proj\", \"change_id\": \"add-widget\","
              " \"phase\": 1},\n"
              "  \"action\": \"create_change\",\n"
              f"  \"commit\": \"{sha}\",\n"
              "  \"source\": \"чат-лог: «погнали» 2026-10-02\"\n"
              "}\n"
              "```\n")
        commit_all(repo, "decision log entry")
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa",
                                   approval_ref="2026-10-02-start-add-widget"))
        assert d.status == "ALLOW", d.details
        assert any("decisions/2026-10-02-start-add-widget.md" in x
                   for x in d.evidence_refs)

    def test_create_change_with_string_ref_not_in_log(self, tmp_path):
        """P0.4: непустая строка approval_ref, НЕ являющаяся записью журнала,
        больше не принимается (сужение D5 — цель P0.4): HUMAN_APPROVAL_REQUIRED
        с подсказкой формата."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa",
                                   approval_ref="PLAN.md: «Погнали» 2026-10-02"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert any("decisions/" in x for x in d.details)

    def test_decision_other_phase_not_transferred(self, tmp_path):
        """Спека: Решение другой фазы не переносится."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa",
                                   approval_ref={"decision_id": "D1",
                                                 "grants": ["create_change"],
                                                 "project": "other",
                                                 "change_id": "add-widget",
                                                 "phase": 2}))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_decision_grant_mismatch(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa",
                                   approval_ref={"decision_id": "D2",
                                                 "grants": ["release"],
                                                 "project": "proj",
                                                 "phase": 1}))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)

    def test_decision_matching_scope_allows(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa",
                                   approval_ref={"decision_id": "D3",
                                                 "grants": ["create_change"],
                                                 "project": "proj",
                                                 "phase": 1}))
        assert d.status == "ALLOW"

    def test_pm_opinion_is_not_decision(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="release", actor_role="pm",
                                   approval_ref="ПМ считает согласованным"))
        # Строковый ref принимается в срезе 1 (D5), но для release также
        # требуется закрытый change → DENY по INVALID_GATE.
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)


# ------------------------------------------------- TC-FTR-007: provenance (D4)


class TestProvenanceCompat:
    def test_accept_review_unknown_compat(self, tmp_path):
        """Спека «Provenance review»: compatibility mode → UNKNOWN/STALE_EVIDENCE."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.1")
        d = ft.check_action(s, act(requested_action="accept_review",
                                   actor_role="code_reviewer", task_id="1.1"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.STALE_EVIDENCE)
        assert d.allowed is False

    def test_merge_task_unknown_with_approve(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.1")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="dev_lead", task_id="1.1"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.STALE_EVIDENCE)
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)

    def test_merge_without_review_deny(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="dev_lead", task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)  # нет approve для 1.2
        assert has_code(d, ft.STALE_EVIDENCE)  # provenance-пометка тоже есть

    def test_approve_of_other_task_not_accepted(self, tmp_path):
        """ТЗ 03 п.8: approve чужой задачи не принимается за evidence этой."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="dev_lead", task_id="2.1"))
        assert has_code(d, ft.INVALID_GATE)
        assert any("2.1" in x for x in d.details)


# --------------------------------------- TC-FTR-008: параллель и зависимости


class TestParallelDeps:
    def _dep_evidence(self, repo: Path) -> dict:
        return ft._dep_evidence(repo, "add-widget", ("1.1", "1.2", "2.1"))

    def test_two_independent_ready(self, tmp_path):
        """Спека: Независимые задачи ready одновременно (обе [P])."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        # [P]-подтверждение из tasks.md (парсер CLI / вызывающий API) → ALLOW:
        d1 = ft.check_action(s, act(task_id="1.2", task_parallel=True,
                                    parallel_confirmed=True))
        assert d1.status == "ALLOW"
        # вторая независимая [P]-задача (3.1 зависит от 1.2 — зависимая, не она):
        # независимость проверяем на задаче без deps
        tasks2 = "- [x] 1.1 готово\n- [ ] 1.3 [P] вторая независимая\n"
        repo2 = make_repo(tmp_path / "b", tasks=tasks2)
        s2 = snapshot_for(repo2, reg, task_id="1.3")
        d2 = ft.check_action(s2, act(task_id="1.3", task_parallel=True,
                                     parallel_confirmed=True))
        assert d2.status == "ALLOW"
        # admit_session-ворота зон присутствуют как required_gates
        assert any("admit_session" in g for g in d1.required_gates)

    def test_parallel_without_marker_confirmation_unknown(self, tmp_path):
        """R5/ТЗ 03 п.1: параллельная задача допускается только при [P] —
        флаг API «на веру» не принимается, неподтвержденный [P] → UNKNOWN."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2", task_parallel=True))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("admit_session" in g for g in d.required_gates)

    def test_dependent_waits_for_merge(self, tmp_path):
        """Спека/приёмка: зависимая ждёт merge предшественницы."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        ev = self._dep_evidence(repo)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(
            s, act(task_id="2.1", task_dependencies=("1.1",),
                   dependency_evidence={"1.1": ev["1.1"]}))
        # 1.1 закрыта [x], но approve-вердикт есть → допустимо
        assert d.status == "ALLOW", d.details

    def test_dependent_open_predecessor(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        ev = self._dep_evidence(repo)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(
            s, act(task_id="2.1", task_dependencies=("1.2",),
                   dependency_evidence={"1.2": ev["1.2"]}))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("ждёт merge" in x for x in d.details)

    def test_dep_without_evidence_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(s, act(task_id="2.1",
                                   task_dependencies=("1.1",)))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)

    def test_dep_closed_without_review(self, tmp_path):
        """J10: предшественница [x], но без approve-вердикта → INVALID_GATE."""
        repo = make_repo(tmp_path, with_review=False)
        reg = make_registry(tmp_path)
        ev = ft._dep_evidence(repo, "add-widget", ("1.1",))
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(
            s, act(task_id="2.1", task_dependencies=("1.1",),
                   dependency_evidence={"1.1": ev["1.1"]}))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("J10" in x for x in d.details)


# ---------------------------------------- TC-FTR-009: Флоу 2 (баг-фикс, эскалация)


class TestFlow2:
    def _bug_snapshot(self, tmp_path: Path, **kw):
        repo = make_repo(tmp_path, **kw)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=2, change_id="BUG-042")
        return repo, reg, s

    def test_bug_fix_allowed(self, tmp_path):
        _, _, s = self._bug_snapshot(tmp_path)
        d = ft.check_action(s, act(requested_action="bug_fix"))
        assert d.status == "ALLOW"

    def test_missing_bug_report(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo / "test-model" / "bugs" / "BUG-042.md").unlink()
        commit_all(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=2, change_id="BUG-042")
        d = ft.check_action(s, act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)

    def test_missing_existing_spec(self, tmp_path):
        repo = make_repo(tmp_path, with_specs=False)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=2, change_id="BUG-042")
        d = ft.check_action(s, act(requested_action="bug_fix"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("существующая спека" in x for x in d.details)

    def test_spec_delta_escalation(self, tmp_path):
        """Спека: Флоу 2 для нового поведения → DENY + next_candidates эскалации."""
        _, _, s = self._bug_snapshot(tmp_path)
        d = ft.check_action(s, act(requested_action="bug_fix", spec_delta=True))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        nxt = {(c["action"], c["actor_role"])
               for c in d.next_candidates}
        assert ("create_change", "sa") in nxt
        assert ("escalate_to_customer", "pm") in nxt


# -------------------------------------- TC-FTR-010: Флоу 3 (хотфикс, PR-долг)


class TestFlow3:
    def _hotfix_repo(self, tmp_path: Path) -> tuple[Path, Path, dict]:
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=3, change_id="BUG-042")
        return repo, reg, s

    def test_emergency_without_incident_ref_unknown(self, tmp_path):
        _, _, s = self._hotfix_repo(tmp_path)
        d = ft.check_action(s, act(requested_action="emergency_stabilize"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)

    def test_emergency_with_incident_ref(self, tmp_path):
        _, _, s = self._hotfix_repo(tmp_path)
        d = ft.check_action(
            s, act(requested_action="emergency_stabilize",
                   incident_ref="incident-2026-10-01: 500 на /login"))
        assert d.status == "ALLOW"
        assert any("PR-цикл" in g for g in d.required_gates)

    def test_deploy_requires_approval(self, tmp_path):
        _, _, s = self._hotfix_repo(tmp_path)
        d = ft.check_action(s, act(requested_action="deploy_rollback",
                                   actor_role="devops"))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        assert has_code(d, ft.EXTERNAL_ENFORCEMENT_UNKNOWN)

    def test_full_cycle_not_declared_done(self, tmp_path):
        """ТЗ 03 п.4: хотфикс без PR-цикла не считается завершенным —
        required_gates держат последующий PR-цикл открытым."""
        _, _, s = self._hotfix_repo(tmp_path)
        d = ft.check_action(
            s, act(requested_action="emergency_stabilize",
                   incident_ref="incident-1"))
        assert any("PR" in g for g in d.required_gates)


# ------------------------------------------- TC-FTR-011: Флоу 4 (обслуживание)


class TestFlow4:
    def _chore_snapshot(self, tmp_path: Path, **kw):
        repo = make_repo(tmp_path, **kw)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=4, change_id="chore")
        return repo, reg, s

    def test_chore_ok(self, tmp_path):
        _, _, s = self._chore_snapshot(tmp_path)
        d = ft.check_action(
            s, act(requested_action="chore_task",
                   paths=("scripts/tool.py",)))
        assert d.status == "ALLOW"

    def test_chore_protected_paths_need_marker(self, tmp_path):
        """J3: защищенные пути без [pipeline]-маркера."""
        _, _, s = self._chore_snapshot(tmp_path)
        d = ft.check_action(
            s, act(requested_action="chore_task",
                   paths=("AGENTS.md", "scripts/x.py")))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        d2 = ft.check_action(
            s, act(requested_action="chore_task",
                   paths=("AGENTS.md",), pipeline_marker=True))
        assert d2.status == "ALLOW"

    def test_chore_cannot_change_rules(self, tmp_path):
        """ТЗ 03 п.5: обслуживание не меняет правила — change-пакетом."""
        _, _, s = self._chore_snapshot(tmp_path)
        d = ft.check_action(
            s, act(requested_action="chore_task", paths=("scripts/x.py",),
                   rules_change=True))
        assert d.status == "DENY"
        assert has_code(d, ft.HUMAN_APPROVAL_REQUIRED)
        nxt = [c["action"] for c in d.next_candidates]
        assert "create_change" in nxt

    def test_chore_review_required(self, tmp_path):
        """Флоу 4 не обходит PR/review: code_review этап присутствует и работает."""
        _, _, s = self._chore_snapshot(tmp_path)
        d = ft.check_action(s, act(requested_action="code_review",
                                   actor_role="code_reviewer"))
        assert d.status == "ALLOW"  # ревью по диффу chore — задача не обязательна


# ----------------------------------------------- TC-FTR-012: Флоу 5 (экспресс)


class TestFlow5:
    def _express_snapshot(self, tmp_path: Path, **kw):
        repo = make_repo(tmp_path, **kw)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=5, change_id="quick-widget")
        return repo, reg, s

    def test_express_requires_conditions(self, tmp_path):
        _, _, s = self._express_snapshot(tmp_path)
        d = ft.check_action(s, act(requested_action="express_task"))
        assert d.status == "UNKNOWN"
        assert has_code(d, ft.MISSING_INPUT)
        d2 = ft.check_action(s, act(requested_action="express_task",
                                    small_change=True))
        assert d2.status == "ALLOW"

    def test_express_close_requires_retro_artifacts(self, tmp_path):
        """ТЗ 03 п.6: ретро-артефакты обязательны до закрытия."""
        repo = make_repo(tmp_path, req=None)
        import shutil
        shutil.rmtree(repo / "test-model" / "new", ignore_errors=True)
        commit_all(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=5, change_id="quick-widget")
        d = ft.check_action(s, act(requested_action="express_close",
                                   actor_role="pm"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)
        assert any("ретроспективные" in x for x in d.details)

    def test_express_close_with_retro_ok(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        # ретро: requirements approved + кейсы new/ + спеки
        s = snapshot_for(repo, reg, flow=5, change_id="add-widget")
        d = ft.check_action(s, act(requested_action="express_close",
                                   actor_role="pm"))
        assert d.status == "ALLOW", d.details


# --------------------------------- TC-FTR-013: DENY перечисляет ВСЕ причины


class TestAllReasons:
    def test_deny_lists_all_reasons(self, tmp_path):
        repo = make_repo(tmp_path, req=REQ_DRAFT, with_sdd=False)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="qa_author"))
        assert d.status == "DENY"
        assert set(d.blocking_reasons) == {ft.WRONG_ROLE, ft.INVALID_GATE,
                                           ft.HUMAN_APPROVAL_REQUIRED}

    def test_unknown_dominates_allow(self, tmp_path):
        """UNKNOWN никогда не разрешает исполнение (allowed=False)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="2.1")
        d = ft.check_action(s, act(task_id="2.1", task_dependencies=("1.1",)))
        assert d.status == "UNKNOWN"
        assert d.allowed is False

    def test_stable_codes_and_details_with_evidence(self, tmp_path):
        """Приёмка: каждый запрет — стабильный код + путь к правилу/evidence."""
        repo = make_repo(tmp_path, with_sdd=False)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "DENY"
        for c in d.blocking_reasons:
            assert c in ft.REASON_CODES
        assert d.details and d.evidence_refs


# ------------------------------------------------ TC-FTR-014: next_candidates


class TestNext:
    def _next(self, repo: Path, reg: Path, flow: int = 1,
              change: str = "add-widget") -> dict:
        s = snapshot_for(repo, reg, flow=flow, change_id=change)
        out = []
        seen = set()
        for stage in ft.STAGE_TABLE[flow]:
            a = ft.ActionRequest(actor_role=stage.roles[0],
                                 requested_action=stage.action,
                                 task_id=None)
            key = (stage.action, None)
            if key in seen:
                continue
            seen.add(key)
            d = ft.check_action(s, a)
            if d.status == "ALLOW":
                out.append(stage.action)
        return {"candidates": out, "snapshot": s}

    def test_next_on_ready_flow1(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("next", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget",
                    "--registry", str(reg), "--json")
        data = json.loads(r.stdout)
        actions = [c["action"] for c in data["candidates"]]
        assert "dev_task" in actions
        assert "qa_checklist" in actions
        assert "release" not in actions
        assert "create_change" not in actions

    def test_next_dev_task_candidates_via_cli_probe(self, tmp_path):
        """Зависимая задача не в кандидатах, пока предшественница открыта."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        ev = ft._dep_evidence(repo, "add-widget", ("1.2", "2.1"))
        d_open = ft.check_action(
            s, act(task_id="2.1", task_dependencies=("1.2",),
                   dependency_evidence={"1.2": ev["1.2"]}))
        assert d_open.status == "DENY"


# ------------------------------------------------------------ TC-FTR-015: CLI


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flow_transition.py"), *args],
        capture_output=True, text=True,
    )


class TestCLI:
    def test_check_allow_exit0_json(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "1.2",
                    "--action", "dev_task", "--role", "dev",
                    "--registry", str(reg), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        d = json.loads(r.stdout)
        assert d["status"] == "ALLOW"
        assert d["scope"]["task"] == "1.2"

    def test_check_deny_exit1(self, tmp_path):
        repo = make_repo(tmp_path, with_sdd=False)
        reg = make_registry(tmp_path)
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "1.2",
                    "--action", "dev_task", "--role", "dev",
                    "--registry", str(reg))
        assert r.returncode == 1
        assert "DENY" in r.stdout
        assert "architecture review" in r.stdout

    def test_check_unknown_exit2(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "1.1",
                    "--action", "accept_review", "--role", "code_reviewer",
                    "--registry", str(reg))
        assert r.returncode == 2
        assert "UNKNOWN" in r.stdout

    def test_check_bad_repo_exit2(self, tmp_path):
        r = run_cli("check", "--repo", str(tmp_path / "nope"), "--project", "p",
                    "--flow", "1", "--change", "a-b", "--action", "dev_task",
                    "--role", "dev")
        assert r.returncode == 2
        assert "FLOW-TRANSITION-ERROR" in r.stdout

    def test_check_cli_dep_evidence_from_repo(self, tmp_path):
        """CLI сам собирает [P]/зависимости/evidence из tasks.md (read-only)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        # 3.1 зависит от 1.2 (открыта) → DENY без ручных флагов
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "3.1",
                    "--action", "dev_task", "--role", "dev",
                    "--registry", str(reg), "--json")
        assert r.returncode == 1
        d = json.loads(r.stdout)
        assert ft.INVALID_GATE in d["blocking_reasons"]
        # 2.1 зависит от 1.1 (закрыта + approve) → ALLOW
        r2 = run_cli("check", "--repo", str(repo), "--project", "proj",
                     "--flow", "1", "--change", "add-widget", "--task", "2.1",
                     "--action", "dev_task", "--role", "dev",
                     "--registry", str(reg), "--json")
        d2 = json.loads(r2.stdout)
        assert d2["status"] == "ALLOW", d2["details"]
        # 1.2 — [P] без зависимостей → ALLOW; parallel распознан из tasks.md
        r3 = run_cli("check", "--repo", str(repo), "--project", "proj",
                     "--flow", "1", "--change", "add-widget", "--task", "1.2",
                     "--action", "dev_task", "--role", "dev",
                     "--registry", str(reg), "--json")
        d3 = json.loads(r3.stdout)
        assert d3["status"] == "ALLOW"

    def test_next_exit0_with_candidates(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("next", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget",
                    "--registry", str(reg), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        actions = [c["action"] for c in data["candidates"]]
        assert "dev_task" in actions
        # независимая [P]-задача 1.2 присутствует как отдельный кандидат
        tasks_cands = [c for c in data["candidates"] if c["action"] == "dev_task"]
        assert any(c["task"] == "1.2" for c in tasks_cands)

    def test_next_dependent_task_waiting(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("next", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget",
                    "--registry", str(reg), "--json")
        data = json.loads(r.stdout)
        waiting_tasks = {w.get("task") for w in data["waiting"]}
        cand_tasks = {c.get("task") for c in data["candidates"]
                      if c["action"] == "dev_task"}
        assert "3.1" in waiting_tasks  # зависит от открытой 1.2
        assert "2.1" in cand_tasks     # зависит от закрытой 1.1 с approve

    def test_next_no_candidates_exit2(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("next", "--repo", str(repo), "--project", "proj",
                    "--flow", "2", "--change", "BUG-042",
                    "--registry", str(reg), "--json")
        data = json.loads(r.stdout)
        # bug_fix допустим на этом fixture → кандидаты есть, exit 0
        assert r.returncode == 0
        assert "bug_fix" in [c["action"] for c in data["candidates"]]

    def test_next_flow2_escalation_candidates(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("next", "--repo", str(repo), "--project", "proj",
                    "--flow", "2", "--change", "BUG-042", "--spec-delta",
                    "--registry", str(reg), "--json")
        data = json.loads(r.stdout)
        # Решение 2026-10-07-code-review-flow2: code_review легален во Флоу 2
        # и не зависит от spec-delta — bug_fix в DENY, но кандидат есть.
        nxt = {(c["action"], c["actor_role"]) for c in data["candidates"]}
        assert ("bug_fix", "dev") not in nxt
        assert ("code_review", "code_reviewer") in nxt
        assert r.returncode == 0

    def test_cli_json_stable(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r1 = run_cli("check", "--repo", str(repo), "--project", "proj",
                     "--flow", "1", "--change", "add-widget", "--task", "1.2",
                     "--action", "dev_task", "--role", "dev",
                     "--registry", str(reg), "--json")
        r2 = run_cli("check", "--repo", str(repo), "--project", "proj",
                     "--flow", "1", "--change", "add-widget", "--task", "1.2",
                     "--action", "dev_task", "--role", "dev",
                     "--registry", str(reg), "--json")
        assert json.loads(r1.stdout) == json.loads(r2.stdout)


# ------------------------------------------------ TC-FTR-016: shadow read-only


class TestShadowReadOnly:
    def test_no_repo_writes_and_no_agents(self, tmp_path):
        """Shadow: check/next не пишут в репозиторий, git status не меняется."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        before_status = git(repo, "status", "--porcelain")
        before_files = {str(p.relative_to(repo)) for p in repo.rglob("*")
                        if ".git" not in p.parts}
        before_head = git(repo, "rev-parse", "HEAD")
        s = snapshot_for(repo, reg, task_id="1.2")
        ft.check_action(s, act(task_id="1.2"), include_next=True)
        run_cli("check", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget", "--task", "1.2",
                "--action", "dev_task", "--role", "dev",
                "--registry", str(reg))
        run_cli("next", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget",
                "--registry", str(reg))
        after_files = {str(p.relative_to(repo)) for p in repo.rglob("*")
                       if ".git" not in p.parts}
        assert git(repo, "status", "--porcelain") == before_status
        assert after_files == before_files
        assert git(repo, "rev-parse", "HEAD") == before_head

    def test_registry_untouched(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        before = reg.read_text(encoding="utf-8")
        s = snapshot_for(repo, reg, task_id="1.2")
        ft.check_action(s, act(task_id="1.2"))
        run_cli("next", "--repo", str(repo), "--project", "proj",
                "--flow", "1", "--change", "add-widget",
                "--registry", str(reg))
        assert reg.read_text(encoding="utf-8") == before


# ---------------------- review-001: негативные тесты фиксов R4/R5/R6, R8, R9


class TestR4TransitiveFlow1Order:
    """R4 (major): транзитивный порядок Флоу 1 «утв. требования → change/SDD →
    architecture review → dev task»; release отличает архивацию от [x]."""

    def test_dev_task_blocked_by_draft_requirements(self, tmp_path):
        """Обязательный негативный: dev_task при draft requirements → DENY."""
        repo = make_repo(tmp_path, req=REQ_DRAFT)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("requirements.md" in x for x in d.details)

    def test_dev_task_blocked_by_missing_requirements(self, tmp_path):
        """requirements.md отсутствует — факт missing тоже должен блокировать
        dev-путь (review-001: «факт missing не читается ни одной проверкой»)."""
        repo = make_repo(tmp_path, req=None)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.2")
        d = ft.check_action(s, act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.MISSING_INPUT)

    def test_release_without_archive_fact_deny(self, tmp_path):
        """R4 release + решение Б (P0.1): «просто все чекбоксы [x]» ≠
        завершенный archive_change — отсутствие пакета archive/<id>/ →
        DENY/INVALID_GATE «release до архивации» (решение 3.2-Б), а не
        UNKNOWN: отсутствие archive — проверяемый отрицательный факт."""
        repo = make_repo(tmp_path)
        write(repo, "openspec/changes/add-widget/tasks.md",
              "- [x] 1.1\n- [x] 1.2\n- [x] 2.1\n- [x] 6.1\n")
        write(repo, "test-model/approved/add-widget/TC-WID-001.md", "# TC\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="release", actor_role="pm",
                                   approval_ref="чат-лог: «погнали»"))
        assert d.status == "DENY"
        assert has_code(d, ft.INVALID_GATE)
        assert any("release до архивации" in x for x in d.details)


class TestR5ParallelMechanism:
    """R5 (major): [P]-механизм работает в CLI-пути (основном пользовательском)."""

    def test_cli_p_marker_autodetected_admit_session_gate(self, tmp_path):
        """Обязательный негативный/позитивный: [P]-задача через CLI БЕЗ флага
        --parallel получает admit_session-пометку зон (live-проба B)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "1.2",
                    "--action", "dev_task", "--role", "dev",
                    "--registry", str(reg), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        d = json.loads(r.stdout)
        assert any("admit_session" in g for g in d["required_gates"]), \
            d["required_gates"]

    def test_cli_parallel_flag_without_p_marker_unknown(self, tmp_path):
        """--parallel на задаче БЕЗ [P]: флаг на веру не принимается → UNKNOWN,
        admit_session-пометка присутствует."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        r = run_cli("check", "--repo", str(repo), "--project", "proj",
                    "--flow", "1", "--change", "add-widget", "--task", "2.1",
                    "--action", "dev_task", "--role", "dev", "--parallel",
                    "--registry", str(reg), "--json")
        d = json.loads(r.stdout)
        assert d["status"] == "UNKNOWN"
        assert any("admit_session" in g for g in d["required_gates"])
        assert any("[P]" in x for x in d["details"])

    def test_non_parallel_task_unaffected(self, tmp_path):
        """Обычная (не [P]) задача: без флага прежний ALLOW — семантика
        ALLOW/DENY/UNKNOWN для непараллельного пути не изменилась."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="2.1")
        ev = ft._dep_evidence(repo, "add-widget", ("1.1",))
        d = ft.check_action(
            s, act(task_id="2.1", task_dependencies=("1.1",),
                   dependency_evidence={"1.1": ev["1.1"]}))
        assert d.status == "ALLOW", d.details


class TestR6HotfixDebt:
    """R6 (major): незакрытый PR-цикл хотфикса — STALE_EVIDENCE-долг на всех
    последующих действиях Флоу 3 (ТЗ 03 п.4; контракт §7 Флоу 3)."""

    def test_flow3_merge_task_carries_debt_marker(self, tmp_path):
        """Обязательный негативный: merge_task Флоу 3 с маркером долга."""
        repo = make_repo(tmp_path)
        write(repo, "code-reviews/BUG-042/review-001-1.1.md",
              "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=3, change_id="BUG-042", task_id="1.1")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="dev_lead", task_id="1.1"))
        assert has_code(d, ft.STALE_EVIDENCE)
        assert any("незакрытый долг хотфикса" in x for x in d.details)
        assert any("PR-цикл" in g for g in d.required_gates)
        assert d.allowed is False

    def test_flow3_accept_review_carries_debt_marker(self, tmp_path):
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, flow=3, change_id="BUG-042")
        d = ft.check_action(s, act(requested_action="accept_review",
                                   actor_role="code_reviewer"))
        assert d.status == "UNKNOWN"
        assert any("незакрытый долг хотфикса" in x for x in d.details)

    def test_flow2_merge_has_no_hotfix_debt(self, tmp_path):
        """Долг — только Флоу 3: merge_task Флоу 2 без маркера хотфикс-долга."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg, task_id="1.1")
        d = ft.check_action(s, act(requested_action="merge_task",
                                   actor_role="dev_lead", task_id="1.1"))
        assert not any("незакрытый долг хотфикса" in x for x in d.details)
        assert not any("долг хотфикса" in g for g in d.required_gates)


class TestR8RolesAndEvidenceFlows2to5:
    """R8 (minor): приемка ТЗ 03 — wrong-role и STALE_SNAPSHOT на каждом флоу."""

    CASES = [
        (2, "BUG-042", "bug_fix", "dev"),
        (3, "BUG-042", "emergency_stabilize", "dev"),
        (4, "chore", "chore_task", "dev"),
        (5, "quick-widget", "express_task", "dev"),
    ]

    def test_wrong_role_on_each_flow(self, tmp_path):
        for flow, change, action, role in self.CASES:
            repo = make_repo(tmp_path / f"r{flow}")
            reg = make_registry(tmp_path / f"r{flow}")
            s = snapshot_for(repo, reg, flow=flow, change_id=change)
            d = ft.check_action(s, act(requested_action=action,
                                       actor_role="dev_lead",
                                       incident_ref="inc-1" if flow == 3 else None))
            assert d.status == "DENY", (flow, d.details)
            assert has_code(d, ft.WRONG_ROLE), flow

    def test_stale_snapshot_on_each_flow(self, tmp_path):
        for flow, change, action, role in self.CASES:
            repo = make_repo(tmp_path / f"s{flow}")
            reg = make_registry(tmp_path / f"s{flow}")
            s = snapshot_for(repo, reg, flow=flow, change_id=change)
            d = ft.check_action(s, act(requested_action=action, actor_role=role,
                                       expected_snapshot_digest="deadbeef" * 8,
                                       incident_ref="inc-1" if flow == 3 else None))
            assert d.status == "DENY", (flow, d.details)
            assert has_code(d, ft.STALE_SNAPSHOT), flow


class TestR9ActionRequestSerialization:
    """R9 (minor): to_dict не теряет вход решения (digest + evidence)."""

    def test_to_dict_contains_digest_and_evidence(self):
        a = ft.ActionRequest(
            actor_role="dev", requested_action="dev_task", task_id="2.1",
            expected_snapshot_digest="abc123",
            task_dependencies=("1.1",),
            dependency_evidence={"1.1": {"task_closed": True,
                                         "review_approved": True}},
        )
        d = a.to_dict()
        assert d["expected_snapshot_digest"] == "abc123"
        assert d["dependency_evidence"] == {
            "1.1": {"task_closed": True, "review_approved": True}}
        assert d["parallel_confirmed"] is None

    def test_to_dict_evidence_none_when_absent(self):
        d = ft.ActionRequest(actor_role="dev",
                             requested_action="dev_task").to_dict()
        assert d["dependency_evidence"] is None
        assert d["expected_snapshot_digest"] is None
