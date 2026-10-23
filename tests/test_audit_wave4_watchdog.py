# -*- coding: utf-8 -*-
"""АУД волна 4, хвост Н18: эвристика bypass delegate_watchdog.

Делегации ПМ через delegate_task (tool) НЕ регистрируются в реестре flowctl —
и это НОРМА. Вотчдог флагает bypass ТОЛЬКО для делегаций с непустым project,
отсутствующих в реестре (с учетом gated_map/baseline) и не отмеченных в ack.
Прецедент ложных срабатываний: 23 bypass с project="" на прогоне 2026-10-23.

Трассировка (rule 6):
  TC-AUD-101  делегация без project вне flowctl — НЕ bypass (норма ПМ-диспатча)
  TC-AUD-102  делегация без project в running — НЕ stale (норма ПМ-диспатча)
  TC-AUD-103  делегация с project вне flowctl — BYPASS (эвристика прежняя)
  TC-AUD-104  делегация с project в реестре flowctl — чисто
  TC-AUD-105  gated_map: платформенный id ворот с живой flowctl-записью — чисто
  TC-AUD-106  baseline: делегация старше installed_at — история, не инцидент
"""
from __future__ import annotations

import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import delegate_watchdog as dw  # noqa: E402

NOW = 1_800_000_000.0
OLD = NOW - 10 * dw.GRACE_SECONDS  # старше grace-окна


def delegation(did, project=None, state="completed", created=OLD):
    d = {"delegation_id": did, "state": state, "created_at": created,
         "dispatched_at": created, "completed_at": None}
    if project is not None:
        d["scope"] = {"project": project}
    return d


def flow_run(cid, delegation_id, status="completed"):
    return {cid: {"status": status, "delegation_id": delegation_id,
                  "scope": {"project": "proj"}}}


# TC-AUD-101: делегация без project (ПМ через delegate_task) — не bypass
def test_no_project_delegation_is_not_bypass():
    delegations = [delegation("deleg_pm_1", project=None)]
    flow = {"runs": flow_run("c1", "deleg-other")}
    bypasses, stale = dw._scan(delegations, flow, now=NOW)
    assert bypasses == []
    assert stale == []


# TC-AUD-102: активная делегация без project — не stale
def test_no_project_running_delegation_is_not_stale():
    delegations = [delegation("deleg_pm_2", project=None, state="running")]
    flow = {"runs": {}}
    bypasses, stale = dw._scan(delegations, flow, now=NOW)
    assert bypasses == []
    assert stale == []


# TC-AUD-103: делегация С project вне flowctl — bypass (эвристика прежняя)
def test_project_delegation_without_flowctl_is_bypass():
    delegations = [delegation("deleg_x1", project="ekotov-wiki"),
                   delegation("deleg_x2", project="ekotov-wiki", state="running")]
    flow = {"runs": {}}
    bypasses, stale = dw._scan(delegations, flow, now=NOW)
    assert [b["delegation_id"] for b in bypasses] == ["deleg_x1"]
    assert [s["delegation_id"] for s in stale] == ["deleg_x2"]


# TC-AUD-104: делегация с project, покрытая flowctl-записью, — чисто
def test_project_delegation_gated_by_flowctl_is_clean():
    delegations = [delegation("deleg-gatedflow", project="ekotov-wiki")]
    flow = {"runs": flow_run("sess1", "deleg-gatedflow")}
    bypasses, stale = dw._scan(delegations, flow, now=NOW)
    assert bypasses == []
    assert stale == []


# TC-AUD-105: gated_map — платформенный id ворот с живой flowctl-записью
def test_gated_map_platform_id_is_clean():
    delegations = [delegation("deleg_mapped", project="ekotov-wiki")]
    flow = {"runs": flow_run("sess2", "deleg-corr", status="running")}
    bypasses, stale = dw._scan(delegations, flow,
                               gated_map={"deleg_mapped": "deleg-corr"},
                               now=NOW)
    assert bypasses == []
    assert stale == []


# TC-AUD-106: baseline — делегация старше внедрения gate — история
def test_baseline_excludes_pre_gate_delegations():
    delegations = [delegation("deleg_old", project="ekotov-wiki",
                              created=OLD)]
    flow = {"runs": {}}
    baseline = {"installed_at": OLD + 60}
    bypasses, _ = dw._scan(delegations, flow, baseline=baseline, now=NOW)
    assert bypasses == []
