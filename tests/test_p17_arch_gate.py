# -*- coding: utf-8 -*-
"""P17 (реш. 2026-10-08-arch-review-policy): SDD-ворота этапа architecture.

1) отсутствие sdd.md на пакете с обязательным arch-этапом — явный
   INVALID_GATE, не тихий generic MISSING_INPUT;
2) явный skip-решение (sdd-skip.md с «approved_by: <кто>» → факт
   sdd.approved_skip) — проход без sdd.md, но НЕ молчаливый: в гейт-выводе
   строка «arch: sdd skipped by <кто>»;
3) sdd.md ready — прежнее поведение (ALLOW, skip-строки нет).
"""
from __future__ import annotations

from test_flow_transition import (  # noqa: E402
    act,
    commit_all,
    make_registry,
    make_repo,
    snapshot_for,
)
import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402

SKIP_TEXT = "# SDD skip\n\napproved_by: pm\n"


def _dev_decision(repo, reg):
    s = snapshot_for(repo, reg, task_id="1.2")
    return ft.check_action(s, act(task_id="1.2"))


def _write_skip(repo, text=SKIP_TEXT):
    (repo / "sdd-skip.md").write_text(text, encoding="utf-8")
    commit_all(repo)


class TestP17SddGate:
    def test_missing_sdd_is_invalid_gate(self, tmp_path):
        """TC-P17-01: sdd.md=MISSING → именованный INVALID_GATE, не тихий skip."""
        repo = make_repo(tmp_path, with_sdd=False)
        reg = make_registry(tmp_path)
        d = _dev_decision(repo, reg)
        assert d.status == "DENY"
        assert ft.INVALID_GATE in d.blocking_reasons
        assert any("sdd.md отсутствует" in x for x in d.details), d.details

    def test_missing_sdd_lists_explicit_skip_path(self, tmp_path):
        """TC-P17-02: DENY называет механизм явного skip (sdd-skip.md / approved_by)."""
        repo = make_repo(tmp_path, with_sdd=False)
        reg = make_registry(tmp_path)
        d = _dev_decision(repo, reg)
        assert any("sdd-skip.md" in x and "approved_by" in x for x in d.details)

    def test_explicit_skip_passes_with_record(self, tmp_path):
        """TC-P17-03: Явный skip: проход без sdd.md, но с записью «arch: sdd skipped by»."""
        repo = make_repo(tmp_path, with_sdd=False)
        _write_skip(repo)
        reg = make_registry(tmp_path)
        d = _dev_decision(repo, reg)
        assert d.status == "ALLOW", d.details
        assert any(g.startswith("arch: sdd skipped by pm") for g in d.required_gates), (
            d.required_gates)

    def test_skip_without_actor_is_invalid(self, tmp_path):
        """TC-P17-04: sdd-skip.md без approved_by — не решение: INVALID_GATE, не проход."""
        repo = make_repo(tmp_path, with_sdd=False)
        _write_skip(repo, "# SDD skip\n\nбез автора\n")
        reg = make_registry(tmp_path)
        d = _dev_decision(repo, reg)
        assert d.status == "DENY"
        assert any("sdd.md отсутствует" in x for x in d.details)

    def test_sdd_ready_unchanged(self, tmp_path):
        """TC-P17-05: sdd ready — прежнее поведение: ALLOW без skip-строки."""
        repo = make_repo(tmp_path)
        reg = make_registry(tmp_path)
        d = _dev_decision(repo, reg)
        assert d.status == "ALLOW", d.details
        assert not any("sdd skipped" in g for g in d.required_gates)


class TestP17SddSkipFact:
    def test_fact_missing(self, tmp_path):
        """TC-P17-06: факт sdd.approved_skip отсутствует — STATUS_MISSING, нормальный путь."""
        problems: list = []
        f = flow_state.sdd_skip_fact(tmp_path, problems)
        assert f.status == flow_state.STATUS_MISSING

    def test_fact_ready_with_actor(self, tmp_path):
        """TC-P17-07: sdd-skip.md с approved_by — факт ready с автором."""
        (tmp_path / "sdd-skip.md").write_text(SKIP_TEXT, encoding="utf-8")
        f = flow_state.sdd_skip_fact(tmp_path, [])
        assert f.status == flow_state.STATUS_READY
        assert f.value == {"approved_by": "pm"}

    def test_fact_invalid_without_actor(self, tmp_path):
        """TC-P17-08: sdd-skip.md без approved_by — STATUS_INVALID."""
        (tmp_path / "sdd-skip.md").write_text("решение без автора\n", encoding="utf-8")
        f = flow_state.sdd_skip_fact(tmp_path, [])
        assert f.status == flow_state.STATUS_INVALID
