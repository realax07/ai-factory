# -*- coding: utf-8 -*-
"""Тесты аудита 2026-10-23 (блок АУД, Н5/Н9/Н11/Н13/Н16).

Н5  — единый контракт БАГ-артефакта: flow_check.bug_report_paths,
      pr_validate.check_bug и flow_transition.check_bug_fix принимают
      ОДИНАКОВО test-model/bugs/BUG-<id>.md ИЛИ BUG-<id>-*.md.
Н11 — parse_verdict матчит нумерованные заголовки («## 7. Вердикт»);
      closed_dev_tasks матчит порядок «[x] 5.3 [M] [ops]» (метка размера
      между номером и маркером роли больше не рвет парсер).
Н13 — зоны: integrator непустая (code-reviews/**, test-model/**);
      docs/** назначен ПМ; pm-зона покрывает PLAN-*.md (J41).
Н16 — check_chore: [chore]-PR с PR_CHANGED_CODE = FAIL с подсказкой
      «используй [change-id]/[BUG-NNN]».

Н9 (openspec validate --strict) в файлах зоны не вызывается: subprocess
живет в gate_runner.py (_openspec_validate) и flow_state.py
(archived_validate) — вне зоны волны, фикс документирован в отчете.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_check  # noqa: E402
import flow_transition as ft  # noqa: E402
import pr_validate  # noqa: E402
import role_zone_policy as rzp  # noqa: E402


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "openspec/specs/widget/spec.md",
          "# widget\n\n### Requirement: Работает\nЧто-то делает.\n")
    write(repo, "test-model/bugs/PLAN.md",
          "# PLAN — багфиксы\n\n**Флоу: 2** (легкий план).\n")
    commit_all(repo)
    return repo


def snapshot_for(repo: Path, tmp_path: Path) -> dict:
    registry = tmp_path / "active_sessions.json"
    registry.write_text('{"sessions": []}', encoding="utf-8")
    return ft.flow_state.inspect(
        repo_arg=str(repo), project="proj", flow=2, change_id="BUG-042",
        registry=str(registry))


def bug_report_findings(findings) -> list[str]:
    """Детали находок ровно про баг-репорт (не план релиза/спеки)."""
    return [f.detail for f in findings if "баг-репорт" in f.detail]


# ------------------------------------------------------- Н5: БАГ-артефакт


class TestBugArtifactContract:
    def test_bug_report_paths_exact_name(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-042.md", "# BUG-042\n")
        paths = flow_check.bug_report_paths(repo, "BUG-042")
        assert paths == [repo / "test-model" / "bugs" / "BUG-042.md"]

    def test_bug_report_paths_suffixed_name(self, tmp_path):
        """TC-AUD-001: Негатив-фикстура прежнего контракта flow_transition: файл
        BUG-042-fix.md (без точного имени) — легальный артефакт."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-042-fix.md", "# BUG-042\n")
        paths = flow_check.bug_report_paths(repo, "BUG-042")
        assert paths == [repo / "test-model" / "bugs" / "BUG-042-fix.md"]

    def test_bug_report_paths_bare_digits_and_missing(self, tmp_path):
        repo = make_repo(tmp_path)
        assert flow_check.bug_report_paths(repo, "042") == []
        write(repo, "test-model/bugs/BUG-042.md", "# x\n")
        assert flow_check.bug_report_paths(repo, "042")[0].name == "BUG-042.md"

    def test_pr_validate_check_bug_accepts_exact_name(self, tmp_path):
        """TC-AUD-002: Негатив-фикстура прежнего контракта pr_validate: glob
        BUG-042-*.md НЕ матчит BUG-042.md → прежде был ложный FAIL PR."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-042.md",
              "# BUG-042\n\nСтатус: OPEN\n")
        assert pr_validate.check_bug(repo, "BUG-042") == []

    def test_pr_validate_check_bug_accepts_suffixed_name(self, tmp_path):
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-042-from-cases.md",
              "# BUG-042\n\nСтатус: OPEN\n")
        assert pr_validate.check_bug(repo, "BUG-042") == []

    def test_pr_validate_check_bug_missing_message_covers_both(self, tmp_path):
        repo = make_repo(tmp_path)
        missing = pr_validate.check_bug(repo, "BUG-042")
        assert len(missing) == 1
        assert "BUG-042.md" in missing[0] and "BUG-042-*.md" in missing[0]

    def test_flow_transition_bug_fix_accepts_suffixed_report(self, tmp_path):
        """TC-AUD-003: Негатив-фикстура прежних ворот Флоу 2: только suffixed-репорт —
        переход bug_fix прежде валился, теперь проходит."""
        repo = make_repo(tmp_path)
        write(repo, "test-model/bugs/BUG-042-regress.md", "# BUG-042\n")
        commit_all(repo)
        snap = snapshot_for(repo, tmp_path)
        action = ft.ActionRequest(actor_role="dev", requested_action="bug_fix")
        findings = ft.check_bug_fix(snap, action, {"checked": set(),
                                                   "evidence": set()}, 2)
        assert bug_report_findings(findings) == []

    def test_flow_transition_bug_fix_missing_report_still_denies(self, tmp_path):
        """TC-AUD-004: Позитив-контроль: репорта нет вовсе — DENY остается (усиление
        контракта не превратилось в молчаливый пропуск)."""
        repo = make_repo(tmp_path)
        snap = snapshot_for(repo, tmp_path)
        action = ft.ActionRequest(actor_role="dev", requested_action="bug_fix")
        findings = ft.check_bug_fix(snap, action, {"checked": set(),
                                                   "evidence": set()}, 2)
        details = bug_report_findings(findings)
        assert details and any("BUG-042" in d for d in details)

    def test_one_artifact_two_gates_agree(self, tmp_path):
        """TC-AUD-005: Контракт Н5 end-to-end: один файл — одинаковый вердикт обоих ворот
        (прежде: flow_transition ALLOW / pr_validate FAIL или наоборот)."""
        for i, name in enumerate(("BUG-042.md", "BUG-042-notes.md")):
            root = tmp_path / f"g{i}"
            root.mkdir()
            repo = make_repo(root)
            write(repo, f"test-model/bugs/{name}",
                  "# BUG-042\n\nСтатус: OPEN\n")
            commit_all(repo)
            gates = (
                flow_check.bug_report_paths(repo, "BUG-042"),
                pr_validate.check_bug(repo, "BUG-042"),
            )
            assert bool(gates[0]) == (gates[1] == []), name


# ------------------------------------------- Н11: parse_verdict / закрытые


class TestParseVerdictNumberedHeading:
    def test_numbered_heading_matched(self):
        text = "# Ревью\n\n## 7. Вердикт: approve\n"
        assert flow_check.parse_verdict(text) == "approve"

    def test_numbered_multilevel_heading_return(self):
        text = "### 3.2 Вердикт: return — доработка\n"
        assert flow_check.parse_verdict(text) == "return"

    def test_numbered_heading_without_colon(self):
        assert flow_check.parse_verdict("## 2 Вердикт approve\n") == "approve"

    def test_plain_heading_still_matched(self):
        assert flow_check.parse_verdict("## Вердикт: approve\n") == "approve"

    def test_no_verdict_heading_none(self):
        assert flow_check.parse_verdict("## 7. Итог: approve\n") is None


class TestClosedDevTasksMarkerOrder:
    TASKS = """TC-AUD-006: # Tasks

- [x] 5.1 сделано
- [x] 5.2 [S] мелочь
- [x] 5.3 [M] [ops] приемка заказчиком
- [x] 5.4 [ops]
- [x] 6.1 QA
- [ ] 5.5 [ops] не закрыта
- [x] 5.6 [M] [docs]
"""

    def test_size_label_before_role_marker_excluded(self):
        """TC-AUD-007: Негатив-фикстура Н11: «[x] 5.3 [M] [ops]» — ops-задача за меткой
        размера; прежде парсер не видел [ops] и требовал code-review."""
        closed = flow_check.closed_dev_tasks(self.TASKS)
        assert "5.3" not in closed

    def test_size_label_alone_included(self):
        assert "5.2" in flow_check.closed_dev_tasks(self.TASKS)

    def test_plain_and_role_marker_cases(self):
        closed = flow_check.closed_dev_tasks(self.TASKS)
        assert "5.1" in closed          # без меток
        assert "5.4" not in closed      # маркер сразу
        assert "6.1" not in closed      # QA-раздел
        assert "5.5" not in closed      # не закрыта
        assert "5.6" not in closed      # docs за меткой размера


# --------------------------------------------------------- Н13: зоны ролей


class TestRoleZonesN13:
    def test_integrator_zone_nonempty_and_covers_merge_artifacts(self):
        zones = rzp.allowed_zones_for("integrator")
        assert zones  # минимум не пустая
        ok = rzp.narrow_zones("integrator",
                              ["code-reviews/add-widget/**",
                               "test-model/regress/add-widget/**"])
        assert ok["zones"] == ["code-reviews/add-widget/**",
                               "test-model/regress/add-widget/**"]
        assert ok["violations"] == []

    def test_integrator_still_out_of_product_code(self):
        ok = rzp.narrow_zones("integrator",
                              ["backend/**", "openspec/changes/add-widget/**"])
        assert ok["zones"] == []
        assert len(ok["violations"]) == 2

    def test_integrator_removed_from_empty_policy_roles(self):
        assert "integrator" not in rzp.EMPTY_POLICY_ROLES

    def test_pm_zone_covers_plan_files(self):
        """TC-AUD-008: J41: PLAN-<id>.md пишет ПМ — зона обязана покрывать (Н13)."""
        ok = rzp.narrow_zones("pm", ["PLAN-add-widget.md", "PLAN-BUG-042.md"])
        assert ok["zones"] == ["PLAN-add-widget.md", "PLAN-BUG-042.md"]
        assert ok["violations"] == []

    def test_pm_zone_covers_docs(self):
        ok = rzp.narrow_zones("pm", ["docs/runbook.md", "docs/ba/x.md"])
        assert ok["zones"] == ["docs/runbook.md", "docs/ba/x.md"]

    def test_pm_still_out_of_product_code_and_specs(self):
        ok = rzp.narrow_zones("pm", ["backend/**",
                                     "openspec/changes/add-widget/tasks.md"])
        assert ok["zones"] == []

    def test_truly_non_writing_roles_keep_empty_policy(self):
        assert rzp.allowed_zones_for("relay") == ()
        assert rzp.allowed_zones_for("customer") == ()
        assert rzp.allowed_zones_for("no_such_role") == ()

    def test_policy_version_marks_amendment(self):
        assert "Н13" in rzp.policy_version()


# -------------------------------------------------------- Н16: [chore]-PR


class TestCheckChoreProductCode:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("PR_CHANGED_SPECS", raising=False)
        monkeypatch.delenv("PR_CHANGED_CODE", raising=False)

    def test_chore_with_product_code_fails_with_hint(self, tmp_path):
        monkeypatch_stub = None  # noqa: F841  (env выставлен ниже явно)
        import os
        os.environ["PR_CHANGED_CODE"] = "1"
        try:
            errs = pr_validate.check_chore(tmp_path, "chore")
        finally:
            import os as _os
            _os.environ.pop("PR_CHANGED_CODE", None)
        assert len(errs) == 1
        assert "[change-id]/[BUG-NNN]" in errs[0]

    def test_chore_clean_diff_passes(self, tmp_path):
        assert pr_validate.check_chore(tmp_path, "chore") == []

    def test_chore_specs_change_still_blocked_first(self, tmp_path):
        import os
        os.environ["PR_CHANGED_SPECS"] = "1"
        os.environ["PR_CHANGED_CODE"] = "1"
        try:
            errs = pr_validate.check_chore(tmp_path, "chore")
        finally:
            os.environ.pop("PR_CHANGED_SPECS", None)
            os.environ.pop("PR_CHANGED_CODE", None)
        assert any("openspec/" in e for e in errs)
