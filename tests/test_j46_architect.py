# -*- coding: utf-8 -*-
"""Тесты J46 (архитектор — актор ревью, вердикт-ворота, карта как
обязательный артефакт). Решение Заказчика 2026-10-12: «Давай. Но ты еще
забыл про map. Она же основной была» (J44 вливается в J46).

Кейсы (ТЗ J46):
  (а) dev_task продуктового пакета без architecture-ревью → DENY
      ARCH_REVIEW_MISSING;
  (б) с ревью + вердиктом approve → ALLOW;
  (в) docs-only пакет (пути вне backend/services/frontend/design) без
      ревью → ALLOW (ворота не применяются);
  (г) backend/ есть, architecture/map.md нет → FLOW-ERROR «карта
      архитектуры отсутствует»;
  (д) архивный продуктовый пакет: architecture-ревью без строки
      «Карта: …» → FLOW-ERROR;
  (е) «Карта: обновлена» / «Карта: без изменений» → OK;
  (ж) энфорсер: role=architect → действие architecture_review (мок
      subprocess);
  (з) SEQUENCE_PREREQS: architecture_review после create_change допустим,
      без него — SEQUENCE_VIOLATION; актор STAGE_TABLE — architect.

Стиль фикстур — как test_j41_plan_release.py / test_j43_flow_enforcer.py:
fixture-репозитории в tmp_path, реальный ~/.hermes/state не трогается.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_check  # noqa: E402
import flow_transition as ft  # noqa: E402

PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))
import enforcer  # noqa: E402


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
- [ ] 1.2 работа
"""

ARCH_REVIEW_APPROVE = (
    "# Architecture review — add-widget\n\n"
    "## Вердикт: approve\n\n"
    "Карта: без изменений — новый модуль внутри существующего сервиса "
    "backend/app, новых сервисов/контейнеров нет.\n"
)


def make_repo(tmp_path: Path, *, change_id: str = "add-widget",
              name: str = "proj") -> Path:
    """Fixture-репозиторий Флоу 1 (собранный пакет; PLAN подкладывает
    autouse-фикстура conftest — тесты ворот архитектора не проверяют
    J41-правило плана)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "requirements.md", REQ_APPROVED)
    write(repo, f"openspec/changes/{change_id}/proposal.md", "# p\n")
    write(repo, f"openspec/changes/{change_id}/design.md", "# d\n")
    write(repo, f"openspec/changes/{change_id}/tasks.md", TASKS)
    write(repo, f"openspec/changes/{change_id}/specs/widget/spec.md",
          "### Requirement: W\n#### Scenario: S\n"
          "- GIVEN a\n- WHEN b\n- THEN c\n")
    write(repo, "sdd.md", "# SDD\n")
    commit_all(repo)
    return repo


def make_registry(tmp_path: Path) -> Path:
    p = tmp_path / "active_sessions.json"
    p.write_text('{"sessions": []}', encoding="utf-8")
    return p


def snapshot_for(repo: Path, registry: Path, **kw) -> dict:
    return flow_state_inspect(repo, registry, **kw)


def flow_state_inspect(repo: Path, registry: Path, **kw) -> dict:
    import flow_state
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


# --------------------- (а/б/в) вердикт-ворота архитектора на dev_task


class TestArchReviewGate:
    def test_dev_task_product_without_review_denied(self, tmp_path):
        """TC-J46-001: J46(а): dev_task пакета с путями backend/ без
        architecture-ревью → DENY/ARCH_REVIEW_MISSING."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2", paths=("backend/app/w.py",)))
        assert d.status == "DENY"
        assert has_code(d, ft.ARCH_REVIEW_MISSING)
        assert any("architecture-ревью" in x for x in d.details)

    def test_dev_task_with_review_and_verdict_allowed(self, tmp_path):
        """TC-J46-002: J46(б): architecture-ревью с «## Вердикт: approve» →
        ALLOW (и файл в evidence)."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/reviews/add-widget/review-001-architecture.md",
              ARCH_REVIEW_APPROVE)
        commit_all(repo, "arch review")
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2", paths=("backend/app/w.py",)))
        assert d.status == "ALLOW", d.details
        assert not has_code(d, ft.ARCH_REVIEW_MISSING)

    def test_review_with_return_verdict_not_enough(self, tmp_path):
        """Вердикт «return» (доработка) — ворота не засчитывает."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/reviews/add-widget/review-001-architecture.md",
              "# Architecture review\n\n## Вердикт: return\n")
        commit_all(repo, "arch review return")
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2", paths=("backend/app/w.py",)))
        assert d.status == "DENY"
        assert has_code(d, ft.ARCH_REVIEW_MISSING)

    def test_docs_only_package_without_review_allowed(self, tmp_path):
        """TC-J46-003: J46(в): docs-only пакет (пути вне продуктовых зон)
        без architecture-ревью → ALLOW."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                            act(task_id="1.2", paths=("docs/guide.md",)))
        assert d.status == "ALLOW", d.details
        assert not has_code(d, ft.ARCH_REVIEW_MISSING)

    def test_product_prefix_variants_gated(self, tmp_path):
        """Все четыре продуктовые зоны на воротах: backend/ services/
        frontend/ design/ (и голое «backend» тоже)."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        for path in ("services/api/main.py", "frontend/src/App.tsx",
                     "design/mockup.fig", "backend"):
            d = ft.check_action(snapshot_for(repo, reg, task_id="1.2"),
                                act(task_id="1.2", paths=(path,)))
            assert has_code(d, ft.ARCH_REVIEW_MISSING), path


# ------------------------------- (г) карта архитектуры — обязательный артефакт


class TestMapRequired:
    def test_map_missing_flow_error(self, tmp_path, capsys):
        """TC-J46-004: J46(г): backend/ есть, architecture/map.md нет →
        FLOW-ERROR «карта архитектуры отсутствует»."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        write(repo, "backend/app/__init__.py", "")
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert rc == 1
        assert "карта архитектуры отсутствует (J46)" in out

    def test_map_present_no_map_error(self, tmp_path, capsys):
        """Контроль: с architecture/map.md ошибки карты нет."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        write(repo, "backend/app/__init__.py", "")
        write(repo, "architecture/map.md", "# Карта\n")
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert "карта архитектуры отсутствует" not in out
        assert rc == 0

    def test_no_product_code_no_map_required(self, tmp_path, capsys):
        """Проект без backend//services/ (например, фабрика) карту не
        требует — ворота не применяются."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        write(repo, "scripts/tool.py", "")
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert "карта архитектуры отсутствует" not in out
        assert rc == 0


# ------------------- (д/е) вердикт по карте в architecture-ревью архива


def make_archived_repo(tmp_path: Path, *, map_line: str | None,
                       review_name: str = "review-001-architecture.md",
                       name: str = "proj") -> Path:
    """Репо с архивным продуктовым пакетом (design.md упоминает backend/)
    и architecture-ревью (с картой-вердиктом или без)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    write(repo, "openspec/changes/archive/2026-10-01-add-widget/design.md",
          "# Design\n\nКод: backend/app/widget.py\n")
    review = "# Architecture review — add-widget\n\n## Вердикт: approve\n\n"
    if map_line:
        review += f"Карта: {map_line}\n"
    write(repo, f"test-model/reviews/2026-10-01-add-widget/{review_name}",
          review)
    commit_all(repo)
    return repo


class TestArchiveMapVerdict:
    def test_archive_review_without_map_line_flow_error(self, tmp_path, capsys):
        """TC-J46-005: J46(д): у архивного продуктового пакета есть
        architecture-ревью, но нет строки «Карта: …» → FLOW-ERROR."""
        repo = make_archived_repo(tmp_path, map_line=None)
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert rc == 1
        assert "в architecture-ревью нет вердикта по карте (J46)" in out
        assert "2026-10-01-add-widget" in out

    @pytest.mark.parametrize("line", ["обновлена", "без изменений"])
    def test_archive_map_verdict_ok(self, tmp_path, capsys, line):
        """TC-J46-006: J46(е): «Карта: обновлена» и «Карта: без изменений»
        — обе легальные строки, ошибки нет."""
        repo = make_archived_repo(tmp_path, map_line=line,
                                  name=f"proj-{line.replace(' ', '-')}")
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert "вердикта по карте" not in out
        assert rc == 0

    def test_wrong_case_or_prose_not_accepted(self, tmp_path, capsys):
        """Регистр точный: «карта: обновлена» / «Карта: Обновлена» / проза
        «карта обновлена» вердиктом не считаются."""
        for i, bad in enumerate(
                ["карта: обновлена", "Обновлена", "Карта — обновлена"]):
            repo = make_archived_repo(tmp_path, map_line=bad,
                                      name=f"proj-bad{i}")
            rc = flow_check.check(repo)
            out = capsys.readouterr().out
            assert rc == 1, bad
            assert "вердикта по карте (J46)" in out, bad

    def test_archive_without_review_not_flagged(self, tmp_path, capsys):
        """Ретро-пакеты БЕЗ architecture-ревью не флагаются (миграцию
        строк ПМ делает в СУЩЕСТВУЮЩИХ ревью; ревью нет — проверять
        нечего)."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        write(repo, "openspec/changes/archive/2026-10-01-add-widget/design.md",
              "# Design\n\nКод: backend/app/widget.py\n")
        commit_all(repo)
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert "вердикта по карте" not in out
        assert rc == 0

    def test_docs_only_archive_not_flagged(self, tmp_path, capsys):
        """Архивный пакет без продуктовых дельт (docs-only) ворота карты
        не проходят."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        write(repo, "openspec/changes/archive/2026-10-02-edit-docs/design.md",
              "# Design\n\nПравка README.md, кода нет.\n")
        write(repo, "test-model/reviews/2026-10-02-edit-docs/"
                    "review-001-architecture.md",
              "# Architecture review\n\nБез вердикта по карте.\n")
        commit_all(repo)
        rc = flow_check.check(repo)
        out = capsys.readouterr().out
        assert "вердикта по карте" not in out
        assert rc == 0


# ---------------------------------------------- (ж/з) энфорсер и таблица


@pytest.fixture()
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда энфорсера (как test_j43_flow_enforcer)."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(tmp_path / "state" / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_PROJECT", raising=False)
    return state


class TestEnforcerArchitect:
    def test_role_architect_maps_to_architecture_review(self, tmp_path,
                                                        plugin_env,
                                                        monkeypatch):
        """TC-J46-007: J46(ж): role=architect → энфорсер прогоняет prepare
        с действием architecture_review (мок subprocess); ALLOW-prepare →
        без block-директивы."""
        calls: list[list[str]] = []

        def _fake(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(
                [], 0, '{"decision": {"status": "ALLOW"}}', "")

        monkeypatch.setattr(enforcer.subprocess, "run", _fake)
        goal = (f"flow: flow=1 role=architect repo={tmp_path} "
                "scope=add-widget paths=architecture/map.md\n"
                "Задача: архитектурное ревью.\n")
        res = enforcer.flow_enforce("delegate_task", {"goal": goal}, "t-j46")
        assert res is None  # ALLOW, sequence-проверка выключена
        assert calls, "prepare не вызван"
        assert "architecture_review" in calls[0]

    def test_sequence_architecture_review_after_create_change(self):
        """TC-J46-008: J46(з): SEQUENCE_PREREQS Флоу 1 — architecture_review
        требует create_change; после него — допустим, без — нарушение."""
        assert enforcer.SEQUENCE_PREREQS[1][
            "architecture_review"] == frozenset({"create_change"})
        phase_done = {"phase": {"action": "create_change",
                                "finished_status": "accepted"},
                      "completed_actions": ["create_change"]}
        assert enforcer.sequence_violation(
            1, "architecture_review", phase_done) is None
        # Ничего не завершено (последний этап не accepted) → нарушение:
        phase_empty = {"phase": "none", "completed_actions": []}
        v = enforcer.sequence_violation(1, "architecture_review", phase_empty)
        assert v and "create_change" in v

    def test_stage_table_actor_is_architect_and_synced(self):
        """STAGE_TABLE Флоу 1: актор architecture_review — architect;
        энфорсер ROLE_ACTIONS синхронен; prereqs-действие стоит в таблице
        РАНЬШЕ (механическая синхронизация)."""
        stages = {s.action: s for s in ft.STAGE_TABLE[1]}
        assert stages["architecture_review"].roles == ("architect",)
        assert enforcer.ROLE_ACTIONS["architect"] == "architecture_review"
        order = {s.action: i for i, s in enumerate(ft.STAGE_TABLE[1])}
        assert order["create_change"] < order["architecture_review"]
        assert order["architecture_review"] < order["dev_task"]
