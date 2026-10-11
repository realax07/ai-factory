# -*- coding: utf-8 -*-
"""Тесты J41 (задача A): план релиза — обязательный артефакт исполняемых
ворот фабрики; bypass-результат делегации — undelivered (кандидат 2b из J39).

Стиль и фикстуры — как в test_flow_transition.py (fixture-репозиторий +
fixture-реестр, без subprocess для библиотечных решений). Реальный
~/.hermes/state/ не трогается.

J41-правила (решение Заказчика 2026-10-11; урок P15 add-wiki — релиз
стартовал без PLAN-файла, план жил в tasks.md СА и переписке ПМ):
  - create_change (Флоу 1) без плана релиза → DENY/PLAN_RELEASE_MISSING;
  - план без объявления воркфлоу («Флоу: N», N 1–5) → DENY/PLAN_FLOW_UNDECLARED;
  - валидный план (шапка как у backlog/J41-*.md) → plan-findings нет;
  - dev_task — транзитивно: dev не стартует без плана даже при проскоченном
    СА-этапе;
  - watchdog: bypass-делегация маркируется undelivered_bypass (результат НЕ
    доставляется; механики доставки у вотчдога нет — только маркировка).

Примечание: conftest-фикстура plan_release_fixture (autouse) здесь отключена
маркером no_plan_fixture — этот файл проверяет САМО правило и управляет
планами вручную; в остальных сьютах фикстура подкладывает PLAN, чтобы их
«собранные» fixture-репозитории остались ALLOW.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402
import delegate_watchdog as dw  # noqa: E402

# J41: этот файл — тесты САМОГО правила плана релиза. Маркер no_plan_fixture
# (зарегистрирован в pytest_configure ниже) отключает autouse-фикстуру
# plan_release_fixture из tests/conftest.py: здесь fixture-репозитории
# строятся БЕЗ PLAN-файла, а планы создаются руками в каждом сценарии
# (missing / undeclared / valid).
pytestmark = pytest.mark.no_plan_fixture


def pytest_configure(config):
    """Регистрация маркера no_plan_fixture (отключение autouse-фикстуры
    plan_release_fixture из conftest.py)."""
    config.addinivalue_line(
        "markers",
        "no_plan_fixture: не подкладывать fixture-PLAN (тесты самого J41-правила)",
    )


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


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | История: r1\n\n"
                "## Описание\n...\n")
TASKS = """# Tasks

- [x] 1.1 готово
- [ ] 1.2 параллельная
"""


def make_repo(tmp_path: Path, *, change_id: str = "add-widget",
              req: str | None = REQ_APPROVED, tasks: str | None = TASKS,
              with_sdd: bool = True, with_deltas: bool = True,
              name: str = "proj") -> Path:
    """Fixture-репозиторий Флоу 1 (как test_flow_transition.make_repo),
    БЕЗ PLAN-файла — его сценарии добавляют руками."""
    repo = tmp_path / name
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
        write(repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
              "### Requirement: W\n#### Scenario: S\n"
              "- GIVEN a\n- WHEN b\n- THEN c\n")
    if with_sdd:
        write(repo, "sdd.md", "# SDD\n")
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


def has_code(d: ft.Decision, code: str) -> bool:
    return code in d.blocking_reasons


# Шапка плана — как у backlog/J41-план-релиза-*.md (жирный Флоу-декларант).
PLAN_HEADER = (
    "# PLAN-add-widget — план релиза change-пакета\n"
    "\n"
    "**Флоу: 1** (решение Заказчика 2026-10-11: релиз стартует с плана ПМ,\n"
    "СА лишь детализирует).\n"
)


# ------------------------------------------- (а) create_change без плана


class TestCreateChangeRequiresPlan:
    def test_create_change_without_plan_missing(self, tmp_path):
        """TC-J41-001: J41(а): create_change без PLAN-файла → DENY/PLAN_RELEASE_MISSING."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_RELEASE_MISSING)
        assert any("план релиза" in x for x in d.details)

    def test_plan_in_change_dir_root_candidates(self, tmp_path):
        """Оба расположения легальны: PLAN-add-widget.md в корне и
        openspec/changes/add-widget/PLAN.md — проверка путей."""
        repo = make_repo(tmp_path)
        paths = ft.plan_release_paths(repo, "add-widget")
        assert (repo / "PLAN-add-widget.md") in paths
        assert (repo / "openspec/changes/add-widget/PLAN.md") in paths


# --------------------------------- (б) план без объявления воркфлоу


class TestPlanFlowUndeclared:
    def test_plan_without_flow_declaration(self, tmp_path):
        """TC-J41-002: J41(б): PLAN есть, строки «Флоу: N» нет → DENY/PLAN_FLOW_UNDECLARED."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md",
              "# PLAN-add-widget\n\n## Этапы\n1. dev\n2. review\n")
        commit_all(repo, "plan без воркфлоу")
        reg = make_registry(tmp_path)
        s = snapshot_for(repo, reg)
        d = ft.check_action(s, act(requested_action="create_change",
                                   actor_role="sa"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_FLOW_UNDECLARED)
        assert not has_code(d, ft.PLAN_RELEASE_MISSING)

    def test_flow_out_of_range_is_undeclared(self, tmp_path):
        """«Флоу: 9» — воркфлоу не объявлен (N только 1–5)."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md",
              "# PLAN\n\n**Флоу: 9**\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg),
                            act(requested_action="create_change",
                                actor_role="sa"))
        assert has_code(d, ft.PLAN_FLOW_UNDECLARED)

    def test_flow_plain_and_bold_both_accepted(self, tmp_path):
        """regex держит оба формата: «Флоу: 2» и «**Флоу: 2**» (шапка J41)."""
        for header in ("Флоу: 2\n", "**Флоу: 3**\n"):
            repo = make_repo(tmp_path, name="proj-" + header.strip())
            write(repo, "PLAN-add-widget.md", "# PLAN\n\n" + header)
            commit_all(repo)
            reg = make_registry(tmp_path)
            d = ft.check_action(snapshot_for(repo, reg),
                                act(requested_action="create_change",
                                    actor_role="sa"))
            assert not has_code(d, ft.PLAN_FLOW_UNDECLARED), header


# --------------------------------- (в) валидный план — plan-findings нет


class TestValidPlanAllows:
    def test_valid_plan_no_plan_findings(self, tmp_path):
        """TC-J41-003: J41(в): валидный план (шапка как у backlog/J41-*.md) →
        PLAN_RELEASE_MISSING / PLAN_FLOW_UNDECLARED отсутствуют."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md", PLAN_HEADER)
        commit_all(repo, "план релиза (ПМ)")
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"), act(task_id="1.2"))
        assert d.status == "ALLOW", d.details
        assert not has_code(d, ft.PLAN_RELEASE_MISSING)
        assert not has_code(d, ft.PLAN_FLOW_UNDECLARED)
        assert any("PLAN-add-widget.md" in x for x in d.evidence_refs)

    def test_valid_plan_in_change_package_dir(self, tmp_path):
        """Второе легальное расположение: openspec/changes/<id>/PLAN.md."""
        repo = make_repo(tmp_path)
        write(repo, "openspec/changes/add-widget/PLAN.md", PLAN_HEADER)
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"), act(task_id="1.2"))
        assert d.status == "ALLOW", d.details
        assert any("openspec/changes/add-widget/PLAN.md" in x
                   for x in d.evidence_refs)

    def test_create_change_with_plan_and_decision_allow(self, tmp_path):
        """create_change: валидный план + решение в журнале → ALLOW."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md", PLAN_HEADER)
        commit_all(repo, "план релиза (ПМ)")
        reg = make_registry(tmp_path)
        sha = git(repo, "rev-parse", "HEAD")
        write(repo, "decisions/2026-10-11-start-add-widget.md",
              "# Решение: старт add-widget\n\n"
              "```decision-record\n"
              "{\n"
              "  \"schema_version\": \"decision-record/1\",\n"
              "  \"decision_id\": \"2026-10-11-start-add-widget\",\n"
              "  \"date\": \"2026-10-11\",\n"
              "  \"scope\": {\"project\": \"proj\", \"change_id\": \"add-widget\","
              " \"phase\": 1},\n"
              "  \"action\": \"create_change\",\n"
              f"  \"commit\": \"{sha}\",\n"
              "  \"source\": \"чат-лог: «погнали» 2026-10-11\"\n"
              "}\n"
              "```\n")
        commit_all(repo, "decision log entry")
        d = ft.check_action(snapshot_for(repo, reg),
                            act(requested_action="create_change",
                                actor_role="sa",
                                approval_ref="2026-10-11-start-add-widget"))
        assert d.status == "ALLOW", d.details


# ------------------------------------- (г) dev_task — транзитивная защита


class TestDevTaskTransitive:
    def test_dev_task_denied_without_plan(self, tmp_path):
        """TC-J41-004: J41(г): dev_task транзитивно требует план — репо собран, но PLAN
        нет → DENY/PLAN_RELEASE_MISSING (транзитивная защита)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_RELEASE_MISSING)

    def test_dev_task_denied_with_undeclared_plan(self, tmp_path):
        """План без «Флоу:» блокирует и dev (не только СА-этап)."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md", "# PLAN\n\nбез воркфлоу\n")
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2"))
        assert d.status == "DENY"
        assert has_code(d, ft.PLAN_FLOW_UNDECLARED)

    def test_dev_task_allowed_with_valid_plan(self, tmp_path):
        """Контроль: с валидным планом dev_task ALLOW."""
        repo = make_repo(tmp_path)
        write(repo, "PLAN-add-widget.md", PLAN_HEADER)
        commit_all(repo)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2"))
        assert d.status == "ALLOW", d.details


# -------------------------- (д) watchdog: bypass → undelivered_bypass


def bypass_delegation(did: str, age_s: float = 3600) -> dict:
    """Платформенная запись делегации, завершенной МИМО flowctl (J39)."""
    return {"delegation_id": did, "state": "completed",
            "delivery_state": "delivered",
            "created_at": time.time() - age_s,
            "dispatched_at": None, "completed_at": None,
            "parent_session_id": "sess-parent"}


class TestWatchdogUndeliveredBypass:
    def test_bypass_marked_undelivered(self, tmp_path):
        """TC-J41-005: J41(д): bypass-детект (нет валидной flowctl-записи) ставит
        undelivered_bypass в incident-запись; доставки нет — только метка."""
        delegations = [bypass_delegation("deleg-bypass01")]
        flow = {"runs": {}}  # ни prepare, ни gated-map — чистый bypass
        bypasses, stale = dw._scan(delegations, flow, baseline={"installed_at": 0})
        assert not stale
        assert len(bypasses) == 1
        entry = bypasses[0]
        assert entry["delegation_id"] == "deleg-bypass01"
        assert entry["undelivered_bypass"] is True
        assert entry["result_delivered"] is False
        assert "undelivered_bypass_reason" in entry

    def test_gated_delegation_not_marked(self, tmp_path):
        """Контроль: делегация ЧЕРЕЗ ворота (valid flowctl-запись) не помечается."""
        delegations = [bypass_delegation("deleg-gated001")]
        flow = {"runs": {"corr1": {"delegation_id": "deleg-gated001",
                                   "status": "running"}}}
        bypasses, stale = dw._scan(delegations, flow, baseline={"installed_at": 0})
        assert bypasses == [] and stale == []

    def test_grace_period_not_marked(self, tmp_path):
        """Младше GRACE_SECONDS — стартовая гонка prepare, не инцидент."""
        delegations = [bypass_delegation("deleg-young000",
                                         age_s=dw.GRACE_SECONDS / 2)]
        bypasses, _ = dw._scan(delegations, {"runs": {}},
                               baseline={"installed_at": 0})
        assert bypasses == []

    def test_console_output_lines_undelivered(self, tmp_path, capsys,
                                              monkeypatch):
        """TC-J41-015: консольный вывод watchdog содержит BYPASS DETECTED и
        строку UNDELIVERED BYPASS (маркировка без новой инфраструктуры)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        # Подменяем все state-пути на tmp (реальный ~/.hermes не трогаем).
        monkeypatch.setattr(dw, "INCIDENTS", state_dir / "incidents.json")
        monkeypatch.setattr(dw, "PM_NUDGE_STATE",
                            state_dir / "pm_nudge.json")
        monkeypatch.setattr(dw, "ACK_STATE", state_dir / "ack.json")
        monkeypatch.setattr(dw, "GATED_MAP_STATE", state_dir / "gmap.json")
        monkeypatch.setattr(dw, "PM_INSTRUCTION_STATE",
                            state_dir / "pm_instruction.txt")
        monkeypatch.setattr(dw, "_baseline_path",
                            lambda: state_dir / "baseline.json")
        monkeypatch.setattr(dw, "FLOWCTL_STATE", state_dir / "flowctl_state.json")
        pm_instruction = state_dir / "pm_instruction.txt"

        # load(): путь-константа → fixture-файл в state_dir (по имени файла);
        # отсутствующий файл → None (как FileNotFoundError в проде).
        def fake_load(path):
            name = Path(path).name
            f = state_dir / name
            if not f.exists():
                return None
            return json.loads(f.read_text(encoding="utf-8"))

        # flowctl_state: пусто (нет ни одной gated-записи — чистый bypass).
        (state_dir / "flowctl_state.json").write_text('{"runs": {}}',
                                                      encoding="utf-8")
        monkeypatch.setattr(dw, "load_delegations",
                            lambda: [bypass_delegation("deleg-bypass02")])
        monkeypatch.setattr(dw, "load", fake_load)
        rc = dw.main()
        out = capsys.readouterr().out
        assert rc == 1
        assert "BYPASS DETECTED" in out
        assert "UNDELIVERED BYPASS" in out
        assert "deleg-bypass02" in out
        # Incident-файл: признак undelivered_bypass в записи.
        incidents = json.loads(dw.INCIDENTS.read_text(encoding="utf-8"))
        assert incidents["bypass"][0]["undelivered_bypass"] is True
        assert pm_instruction.exists()
