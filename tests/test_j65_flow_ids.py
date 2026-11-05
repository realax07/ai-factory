# -*- coding: utf-8 -*-
"""J65.3: единая грамматика scope флоу (scripts/flow_ids.py).

До J65.3 энфорсер и движок расходились: Ф2 BUG-AF-RECHECK-001 энфорсер
пропускал, движок отвечал FLOW_ID_INVALID; Ф3 S1-… энфорсер требовал, движок
не принимал; Ф5 однословный slug — наоборот. Грамматика (решения Заказчика
2026-11-05): Ф1 change-id, Ф2 имя репорта, Ф3 incident-ref (+ легаси BUG в
движке), Ф4/Ф5 kebab-slug.

Трассировка:
  TC-J65-FID-001  таблица примеров: flow_ids.valid_scope (движок, legacy)
  TC-J65-FID-002  та же таблица: маркер энфорсера = valid_scope(legacy=False)
  TC-J65-FID-003  движок (flow_state.check_flow_identifier) = flow_ids
  TC-J65-FID-004  fallback-копия энфорсера и литерал flow_check совпадают с
                  модулем (автономные копии не расходятся)
  TC-J65-FID-005  Ф3: scope маркера передается движку как --change — incident-ref
                  проходит и энфорсер, и движок (раньше движок отказывал)
  TC-J65-FID-006  incident_severity и SEVERITY_PREFIX_RE flow_transition — из
                  flow_ids (один allowlist)
  TC-J65-FID-007  отказ маркера называет источник грамматики (flow_ids/fallback);
                  flow вне 1–5 — отказ (fail-closed)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "plugins" / "flow-enforcer"))
sys.path.insert(0, str(FACTORY / "scripts"))

import enforcer  # noqa: E402
import flow_check  # noqa: E402
import flow_ids  # noqa: E402
import flow_state  # noqa: E402
import flow_transition as ft  # noqa: E402

# (flow, scope, движок принимает, маркер принимает)
TABLE = [
    (1, "add-widget", True, True),
    (1, "widget", False, False),
    (1, "Add-Widget", False, False),
    (1, "BUG-001", False, False),
    (2, "BUG-001", True, True),
    (2, "BUG-AF-RECHECK-001", True, True),
    (2, "BUG-001-search-card", True, True),
    (2, "bug-001", False, False),
    (2, "BUG-01", False, False),
    (2, "add-widget", False, False),
    (3, "S1-prod-down", True, True),
    (3, "S3-cosmetic", True, True),
    (3, "S4-future", False, False),
    (3, "S1-", False, False),
    (3, "S1-Prod", False, False),
    (3, "BUG-042", True, False),       # легаси: только движок
    (3, "prod-down", False, False),
    (4, "chore", True, True),
    (4, "repo-cleanup", True, True),
    (4, "Repo_Cleanup", False, False),
    (5, "typo", True, True),
    (5, "fix-typo", True, True),
    (5, "fix typo", False, False),
    (5, "", False, False),
    (1, "add-widget\n", False, False),  # fullmatch: перевод строки — отказ
    (2, "BUG-001\n", False, False),
    (3, "S1-prod-down\n", False, False),
]


@pytest.mark.parametrize("flow,scope,engine,_marker", TABLE)
def test_valid_scope_engine_table(flow, scope, engine, _marker):
    """TC-J65-FID-001: грамматика движка по таблице примеров."""
    assert flow_ids.valid_scope(flow, scope) is engine


@pytest.mark.parametrize("flow,scope,_engine,marker", TABLE)
def test_marker_scope_table(flow, scope, _engine, marker):
    """TC-J65-FID-002: маркер энфорсера = valid_scope(legacy=False)."""
    assert flow_ids.valid_scope(flow, scope, legacy=False) is marker
    assert enforcer.marker_scope_valid(flow, scope) is marker
    if scope and not marker:
        with pytest.raises(enforcer.FlowMarkerError):
            enforcer.validate_scope_for_flow(flow, scope)
    elif scope:
        enforcer.validate_scope_for_flow(flow, scope)  # не бросает


@pytest.mark.parametrize("flow,scope,engine,_marker",
                         [row for row in TABLE if row[1]])
def test_engine_uses_flow_ids(flow, scope, engine, _marker):
    """TC-J65-FID-003: flow_state.check_flow_identifier отказывает ровно там,
    где flow_ids.valid_scope (FLOW_ID_INVALID)."""
    problems: list = []
    flow_state.check_flow_identifier(FACTORY, flow, scope, problems)
    codes = {p.code for p in problems}
    assert ("FLOW_ID_INVALID" in codes) is (not engine)


def test_autonomous_copies_match_module():
    """TC-J65-FID-004: fallback-копия энфорсера и литерал flow_check
    (копируется в проекты) совпадают с flow_ids."""
    for key, value in enforcer._FLOW_IDS_FALLBACK.items():
        assert value == getattr(flow_ids, key), key
    assert flow_check.BUG_ID_PATTERN == flow_ids.BUG_ID_PATTERN
    assert enforcer.INCIDENT_REF_RE.pattern == flow_ids.INCIDENT_REF_PATTERN


def test_flow3_incident_ref_passes_marker_and_engine():
    """TC-J65-FID-005: incident-ref из маркера проходит и энфорсер, и движок
    (prepare_command передает scope Ф3 как --change)."""
    scope = "S1-prod-down"
    enforcer.validate_scope_for_flow(3, scope)
    problems: list = []
    flow_state.check_flow_identifier(FACTORY, 3, scope, problems)
    assert not [p for p in problems if p.code == "FLOW_ID_INVALID"]


def test_severity_from_flow_ids():
    """TC-J65-FID-006: allowlist severity — один, из flow_ids."""
    assert ft.SEVERITY_PREFIXES is flow_ids.SEVERITY_PREFIXES
    assert ft.SEVERITY_PREFIX_RE is flow_ids.SEVERITY_PREFIX_RE
    assert ft.incident_severity("S2-login-500") == "S2"
    assert flow_ids.incident_severity("S4-x") is None
    assert enforcer._severity_prefixes() == flow_ids.SEVERITY_PREFIXES


def test_marker_error_names_grammar_source():
    """TC-J65-FID-007: источник грамматики виден в отказе; flow вне 1–5 —
    отказ без опоры на порядок вызовов."""
    assert enforcer.GRAMMAR_SOURCE in ("flow_ids", "fallback")
    with pytest.raises(enforcer.FlowMarkerError) as ei:
        enforcer.validate_scope_for_flow(3, "S1-Prod")
    assert f"грамматика: {enforcer.GRAMMAR_SOURCE}" in str(ei.value)
    assert "строчные" in str(ei.value)
    with pytest.raises(enforcer.FlowMarkerError):
        enforcer.validate_scope_for_flow(9, "add-widget")
