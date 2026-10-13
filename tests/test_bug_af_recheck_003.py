# -*- coding: utf-8 -*-
"""BUG-AF-RECHECK-003: историческое approve считалось действующим.

Фикс (обе функции):
  - flow_check.approved_review_tasks() — действуют АКТУАЛЬНАЯ итерация задачи
    (max rev среди ВСЕХ review-файлов: имена + review-mapping.json): 
    approve→return — не покрыто; return→approve — покрыто;
    approve→return→approve — покрыто последней; нечитаемый/противоречивый
    вердикт последней итерации — не покрыта + WARNING (не молча);
  - flow_transition.architecture_review_verdict() — вердикт последней
    итерации (review-NNN с максимальным NNN) решает; неоднозначность →
    (False, files).

Табличные тесты переходов: approve→return, return→approve,
approve→return→approve, независимые задачи 1.2/1.3.
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

META = "Reviewer-Delegation: deleg_testreviewer0000\n"


def review(verdict: str, meta: bool = True) -> str:
    text = f"# Review\n\n## Вердикт: {verdict}\n"
    return text + (META if meta else "")


def make_cr(tmp_path: Path, change: str, files: dict[str, str],
            mapping: dict | None = None) -> Path:
    repo = tmp_path / "proj"
    cr = repo / "code-reviews" / change
    cr.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (cr / name).write_text(text, encoding="utf-8")
    if mapping is not None:
        (cr / "review-mapping.json").write_text(
            json_dumps(mapping), encoding="utf-8")
    return repo


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


# ------------------------- flow_check.approved_review_tasks (переходы задач)


class TestApprovedReviewTaskIterations:
    def test_approve_then_return_not_covered(self, tmp_path):
        """TC-AF-RECHECK-003-01: approve→return — недействительно (поздний
        return отменяет старое разрешение)."""
        repo = make_cr(tmp_path, "ch", {
            "review-001-1.2.md": review("approve"),
            "review-002-1.2.md": review("return"),
        })
        assert flow_check.approved_review_tasks(repo, "ch") == {}

    def test_return_then_approve_covered(self, tmp_path):
        """TC-AF-RECHECK-003-02: return→approve — действительно."""
        repo = make_cr(tmp_path, "ch", {
            "review-001-1.2.md": review("return"),
            "review-002-1.2.md": review("approve"),
        })
        covered = flow_check.approved_review_tasks(repo, "ch")
        assert covered == {"1.2": "review-002-1.2.md"}

    def test_approve_return_approve_covered_by_last(self, tmp_path):
        """TC-AF-RECHECK-003-03: approve→return→approve — последняя
        применимая итерация."""
        repo = make_cr(tmp_path, "ch", {
            "review-001-1.2.md": review("approve"),
            "review-002-1.2.md": review("return"),
            "review-003-1.2.md": review("approve"),
        })
        covered = flow_check.approved_review_tasks(repo, "ch")
        assert covered == {"1.2": "review-003-1.2.md"}

    def test_task_12_return_does_not_cancel_13(self, tmp_path):
        """TC-AF-RECHECK-003-04: return задачи 1.2 не отменяет approve
        независимой задачи 1.3 (покрытие per-задача, не глобальное)."""
        repo = make_cr(tmp_path, "ch", {
            "review-001-1.2.md": review("approve"),
            "review-001-1.3.md": review("approve"),
            "review-002-1.2.md": review("return"),
        })
        covered = flow_check.approved_review_tasks(repo, "ch")
        assert "1.3" in covered and "1.2" not in covered

    def test_unreadable_latest_not_silently_covered(self, tmp_path):
        """TC-AF-RECHECK-003-05: нечитаемый вердикт последней итерации —
        задача НЕ покрыта + WARNING в списке warns (не молча)."""
        repo = make_cr(tmp_path, "ch", {
            "review-001-1.2.md": review("approve"),
            "review-002-1.2.md": "# без строки вердикта\n",
        })
        wl: list[str] = []
        assert flow_check.approved_review_tasks(repo, "ch", wl) == {}
        assert wl and "1.2" in wl[0]

    def test_conflicting_verdicts_same_iteration_not_covered(self, tmp_path):
        """TC-AF-RECHECK-003-06: противоречивые вердикты одной итерации —
        НЕ покрыто + WARNING (человек решает)."""
        repo = make_cr(tmp_path, "ch", {
            "review-002-1.2.md": review("approve"),
            "review-1.2-002.md": review("return"),
        })
        wl: list[str] = []
        assert flow_check.approved_review_tasks(repo, "ch", wl) == {}
        assert wl

    def test_mapping_iteration_decides(self, tmp_path):
        """TC-AF-RECHECK-003-07: review-mapping.json (исторические имена Ф4)
        участвует в итерациях: approve(rev2)→return(rev3, mapping) — не
        покрыто; return→approve — покрыто."""
        repo = make_cr(tmp_path, "ch", {
            "review-002.md": review("approve"),
            "review-003.md": review("return"),
        }, mapping={"review-002.md": ["1.1"], "review-003.md": ["1.1"]})
        assert flow_check.approved_review_tasks(repo, "ch") == {}
        repo2 = make_cr(tmp_path, "ch2", {
            "review-002.md": review("return"),
            "review-003.md": review("approve"),
        }, mapping={"review-002.md": ["1.1"], "review-003.md": ["1.1"]})
        assert flow_check.approved_review_tasks(repo2, "ch2") == {"1.1": "review-003.md"}

    def test_binding_copies_same_iteration_ok(self, tmp_path):
        """TC-AF-RECHECK-003-08: копии-привязки одной итерации (ревью без
        task-id в имени + review-<task>-NNN.md копии): одинаковый rev —
        ОДНА итерация; мета достаточна хотя бы у одного файла (у источника)."""
        source = ("# Review-00002\n\n## Вердикт: **APPROVE**\n\n"
                  "## Reviewer-Delegation: deleg_abc1230000\n")
        repo = make_cr(tmp_path, "ch", {
            "review-002.md": source,
            "review-1.1-002.md": source.replace("deleg_abc1230000\n", ""),
        }, mapping={"review-002.md": ["1.1"]})
        covered = flow_check.approved_review_tasks(repo, "ch")
        assert covered == {"1.1": "review-002.md"}

    def test_meta_is_event_level_property(self, tmp_path):
        """TC-AF-RECHECK-003-10б: мета Reviewer-Delegation — свойство события
        ревью (rev): задача 3.1 привязана копией review-3.1-004.md без меты к
        событию 004, источник которого (review-004.md) мету несет — задача
        покрыта."""
        repo = make_cr(tmp_path, "ch", {
            "review-004.md": review("approve"),
            "review-3.1-004.md": review("approve", meta=False),
        }, mapping={"review-004.md": ["4.1"]})
        covered = flow_check.approved_review_tasks(repo, "ch")
        assert covered["3.1"] == "review-3.1-004.md"
        assert covered["4.1"] == "review-004.md"

    def test_check_prints_warning_not_silent(self, tmp_path, capsys):
        """TC-AF-RECHECK-003-09: сквозной check(): нечитаемая последняя
        итерация закрытой задачи → FLOW-WARNING в выводе + FLOW-ERROR о
        непокрытой задаче (не молчаливое покрытие)."""
        repo = tmp_path / "proj"
        (repo / "openspec/changes/ch").mkdir(parents=True)
        (repo / "code-reviews/ch").mkdir(parents=True)
        (repo / "openspec/changes/ch/tasks.md").write_text(
            "# Tasks\n\n- [x] 1.1 сделано\n", encoding="utf-8")
        (repo / "openspec/changes/ch/proposal.md").write_text("# p\n",
                                                              encoding="utf-8")
        (repo / "openspec/changes/ch/design.md").write_text("# d\n",
                                                            encoding="utf-8")
        (repo / "code-reviews/ch/review-001-1.1.md").write_text(
            review("approve"), encoding="utf-8")
        (repo / "code-reviews/ch/review-002-1.1.md").write_text(
            "# вердикта нет\n", encoding="utf-8")
        flow_check.check(repo)
        out = capsys.readouterr().out
        assert "FLOW-WARNING" in out and "1.1" in out
        assert "без code-review" in out or "без review-файла" in out


# ------------------- flow_transition.architecture_review_verdict (J46)


def make_arch(tmp_path: Path, change: str,
              files: dict[str, str]) -> Path:
    repo = tmp_path / "proj"
    rd = repo / "test-model" / "reviews" / change
    rd.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (rd / name).write_text(text, encoding="utf-8")
    return repo


class TestArchitectureReviewVerdictIterations:
    def test_approve_then_return_denied(self, tmp_path):
        """TC-AF-RECHECK-003-10: approve(001)→return(002) — разрешения НЕТ
        (раньше возвращался первый approve)."""
        repo = make_arch(tmp_path, "ch", {
            "review-001-architecture.md": review("approve"),
            "review-002-architecture.md": review("return"),
        })
        ok, files = ft.architecture_review_verdict(repo, "ch")
        assert ok is False and len(files) == 2

    def test_return_then_approve_allowed(self, tmp_path):
        """TC-AF-RECHECK-003-11: return(001)→approve(002) — действует."""
        repo = make_arch(tmp_path, "ch", {
            "review-001-architecture.md": review("return"),
            "review-002-architecture.md": review("approve"),
        })
        ok, _ = ft.architecture_review_verdict(repo, "ch")
        assert ok is True

    def test_approve_return_approve_last_wins(self, tmp_path):
        """TC-AF-RECHECK-003-12: approve→return→approve — последняя итерация."""
        repo = make_arch(tmp_path, "ch", {
            "review-001-architecture.md": review("approve"),
            "review-002-architecture.md": review("return"),
            "review-003-architecture.md": review("approve"),
        })
        ok, _ = ft.architecture_review_verdict(repo, "ch")
        assert ok is True

    def test_first_approve_alone_still_works(self, tmp_path):
        """TC-AF-RECHECK-003-13: единственное approve(001) — по-прежнему
        достаточно (регресс старого поведения)."""
        repo = make_arch(tmp_path, "ch", {
            "review-001-architecture.md": review("approve")})
        ok, _ = ft.architecture_review_verdict(repo, "ch")
        assert ok is True

    def test_ambiguous_max_rev_denied(self, tmp_path):
        """TC-AF-RECHECK-003-14: неоднозначность — файл вне канонической схемы
        review-NNN-architecture.md (номер итерации неопределим) → (False,
        files), решает человек."""
        repo = make_arch(tmp_path, "ch", {
            "review-001-architecture.md": review("approve"),
            "review-2-architecture.md": review("approve"),
        })
        ok, files = ft.architecture_review_verdict(repo, "ch")
        assert ok is False and len(files) == 2

    def test_gate_blocks_after_late_return(self, tmp_path):
        """TC-AF-RECHECK-003-15: сквозные ворота (check_action): поздний
        return архитектуры закрывает ранее разрешенную dev_task → DENY
        ARCH_REVIEW_MISSING с диагностикой актуальной итерации."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)  # conftest-фикстура уже создала каталог
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        for rel, text in {
            "requirements.md": ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: "
                                "ba_agent | История: r1\n\n## Описание\nx\n\n"
                                "## Аудитория\ny\n\n## Функциональные "
                                "требования\n- FR-1 x\n\n## Нефункциональные "
                                "требования\n- NFR-1 y\n\n## Приоритеты\n- P1\n\n"
                                "## Ограничения\n- z\n\n## Открытые вопросы\n- нет\n"),
            "openspec/changes/add-widget/proposal.md": "# p\n",
            "openspec/changes/add-widget/design.md": "# d\n",
            "openspec/changes/add-widget/tasks.md": "- [ ] 1.1 x\n",
            "openspec/changes/add-widget/specs/w/spec.md":
                "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n",
            "sdd.md": "# SDD\n",
        }.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        rd = repo / "test-model/reviews/add-widget"
        rd.mkdir(parents=True)
        (rd / "review-001-architecture.md").write_text(
            review("approve"), encoding="utf-8")
        (rd / "review-002-architecture.md").write_text(
            review("return"), encoding="utf-8")
        import flow_state
        reg = tmp_path / "reg.json"
        reg.write_text('{"sessions": []}', encoding="utf-8")
        snap = flow_state.inspect(repo_arg=str(repo), project="proj", flow=1,
                                  change_id="add-widget", task_id="1.2",
                                  registry=str(reg))
        act = ft.ActionRequest(actor_role="dev", requested_action="dev_task",
                               task_id="1.2", paths=("backend/app/w.py",))
        d = ft.check_action(snap, act)
        assert d.status == "DENY"
        assert ft.ARCH_REVIEW_MISSING in d.blocking_reasons
        assert any("актуальной итерации" in x for x in d.details)
