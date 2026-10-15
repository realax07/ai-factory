# -*- coding: utf-8 -*-
"""Тесты J48 — инцидент-протокол Флоу 3 (change add-incident-protocol).

Покрывает: severity-префикс внутри incident_ref (FR-4/design D1), DENY
неклассифицированного инцидента (tasks 1.2), этапы post_mortem/archive_change
STAGE_TABLE[3] (design D3), ворота архивации check_archive_flow3 (FR-3/design
D2 — severity перепарсивается из action.incident_ref сам, I-2), валидацию
маркера в enforcer (FLOW_MARKER_INVALID), append-only хранилища
test-model/incidents/ (NFR-2), изоляцию Флоу 1/2/4/5 (NFR-3).

Трассировка: TC-J48-001…TC-J48-019 (спека-дельта incident-protocol: Severity-
классификация, Initial response, Post-mortem и ворота архивации, Severity в
маркере делегации; design.md D1–D4; review-001-architecture M-1/M-3/I-2).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402

SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))

import flow_transition as ft  # noqa: E402

# Переиспользуем fixture-хелперы поставки 03 (make_repo, snapshot_for, act):
import test_flow_transition as base  # noqa: E402


POST_MORTEM_MD = """# 2026-10-15 — S2-login-degraded

## Таймлайн

- 2026-10-15T10:00Z — инцидент начат (initial response старт)
- 2026-10-15T10:07Z — стабилизация (initial response 7 мин, порог ≤15 соблюден)

## Root cause

Регрессия релиза R: таймаут внешнего API без ретрая.

## Action items

- добавить ретрай в client (change-пакет add-retry)
"""


def write_post_mortem(repo: Path, incident_ref: str,
                      text: str = POST_MORTEM_MD) -> Path:
    d = repo / "test-model" / "incidents"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"2026-10-15-{incident_ref}.md"
    p.write_text(text, encoding="utf-8")
    return p


def hotfix_snapshot(tmp_path: Path, **kw) -> tuple[Path, dict]:
    repo = base.make_repo(tmp_path)
    reg = base.make_registry(tmp_path)
    s = base.snapshot_for(repo, reg, flow=3, change_id="BUG-042", **kw)
    return repo, s


# ------------------------------------------------- D1: severity в incident_ref


class TestSeverityPrefix:
    def test_severity_extraction_s1_s2_s3(self):
        """TC-J48-001: разбор префикса ^S[123]- (FR-4): S1-/S2-/S3- извлечены;
        без префикса / чужой уровень (S4-, s1-) — неклассифицирован (None)."""
        assert ft.incident_severity("S1-prod-down") == "S1"
        assert ft.incident_severity("S2-login-degraded") == "S2"
        assert ft.incident_severity("S3-cosmetic") == "S3"
        assert ft.incident_severity("incident-1") is None
        assert ft.incident_severity("S4-unknown-level") is None
        assert ft.incident_severity("s1-lowercase") is None
        assert ft.incident_severity("S1") is None
        assert ft.incident_severity(None) is None

    def test_emergency_stabilize_delivers_severity_via_ctx(self):
        """TC-J48-002 (D1): разобранный severity доступен последующим
        check-функциям через ctx одного check_action-вызова."""
        ctx = {"checked": set(), "evidence": set(), "extra_gates": []}
        action = base.act(requested_action="emergency_stabilize",
                          incident_ref="S1-prod-down")
        out = ft.check_emergency_stabilize({}, action, ctx, 3)
        assert ctx["incident_severity"] == "S1"
        assert not [f for f in out if not f.unknown]

    def test_emergency_unclassified_deny(self, tmp_path):
        """TC-J48-003 (tasks 1.2): incident_ref БЕЗ префикса → Finding
        MISSING_INPUT «инцидент неклассифицирован» (DENY, не UNKNOWN —
        отсутствие входа классификации; design D1)."""
        _, s = hotfix_snapshot(tmp_path)
        d = ft.check_action(s, base.act(requested_action="emergency_stabilize",
                                        incident_ref="incident-2026-10-01"))
        assert d.status == "DENY"
        assert base.has_code(d, ft.MISSING_INPUT)
        assert any("неклассифицирован" in x for x in d.details)

    def test_emergency_flows_1_2_4_5_unaffected(self):
        """TC-J48-004 (NFR-3): проверка префикса — ТОЛЬКО Флоу 3 (flow==3);
        direct-вызов check_emergency_stabilize с flow=1/2/4/5 не добавляет
        неклассифицированных находок (поведение прочих флоу не изменилось)."""
        for flow in (1, 2, 4, 5):
            ctx = {"checked": set(), "evidence": set(), "extra_gates": []}
            action = base.act(requested_action="emergency_stabilize",
                              incident_ref="incident-1")
            out = ft.check_emergency_stabilize({}, action, ctx, flow)
            assert not [f for f in out if not f.unknown], flow
            # D1: ctx-доставка только разобранного severity; неклассифицированный
            # ref (префикса нет) ctx не помечает (ворота перечитают сами, I-2).
            assert "incident_severity" not in ctx


# ------------------------------------------ D2/D3: ворота и этапы архивации


class TestArchiveGate:
    def test_archive_s1_without_post_mortem_deny(self, tmp_path):
        """TC-J48-005 (FR-3): архивация Флоу 3 S1 без post-mortem в
        test-model/incidents/ → DENY (ненулевой exit семантика), DENY-код
        MISSING_INPUT; check_action целиком DENY."""
        repo, s = hotfix_snapshot(tmp_path)
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S1-prod-down")
        findings = ft.check_archive_flow3(s, action,
                                          {"checked": set(),
                                           "evidence": set()}, 3)
        assert findings and not findings[0].unknown
        d = ft.check_action(s, action)
        assert d.status == "DENY"
        assert base.has_code(d, ft.MISSING_INPUT)
        assert (repo / "test-model" / "incidents").exists() is False or not [
            p for p in (repo / "test-model" / "incidents").glob("*.md")
            if "S1-prod-down" in p.name]

    def test_archive_s2_with_post_mortem_passes(self, tmp_path):
        """TC-J48-006 (FR-3): S2 с post-mortem (таймлайн/root cause/action
        items) — ворот не добавляет находок; check_action по воротам ALLOW."""
        repo, s = hotfix_snapshot(tmp_path)
        write_post_mortem(repo, "S2-login-degraded")
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S2-login-degraded")
        assert ft.check_archive_flow3(s, action,
                                      {"checked": set(),
                                       "evidence": set()}, 3) == []
        d = ft.check_action(s, action)
        assert d.status == "ALLOW", d.details

    def test_archive_s3_protocol_not_applied(self, tmp_path):
        """TC-J48-007 (FR-1/S3): протокол Флоу 3 к S3 НЕ применяется —
        архивация S3 без post-mortem проходит (и этап, и ворота)."""
        repo, s = hotfix_snapshot(tmp_path)
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S3-cosmetic")
        assert ft.check_archive_flow3(s, action,
                                      {"checked": set(),
                                       "evidence": set()}, 3) == []
        assert ft.check_post_mortem(s, action,
                                    {"checked": set(),
                                     "evidence": set()}, 3) == []
        d = ft.check_action(s, action)
        assert d.status == "ALLOW", d.details

    def test_archive_unclassified_deny_missing_input(self, tmp_path):
        """TC-J48-008 (tasks 2.2): неклассифицированный incident_ref
        архивацию НЕ разрешает — DENY MISSING_INPUT."""
        _, s = hotfix_snapshot(tmp_path)
        for ref in ("incident-1", None):
            action = base.act(requested_action="archive_change",
                              actor_role="sa", incident_ref=ref)
            findings = ft.check_archive_flow3(s, action,
                                              {"checked": set(),
                                               "evidence": set()}, 3)
            assert findings, ref
            assert findings[0].code == ft.MISSING_INPUT
            assert not findings[0].unknown
            d = ft.check_action(s, action)
            assert d.status == "DENY", ref
            assert base.has_code(d, ft.MISSING_INPUT)

    def test_post_mortem_incomplete_sections_deny(self, tmp_path):
        """TC-J48-009 (D4): файл без обязательных секций (таймлайн/root cause/
        action items) — DENY INVALID_GATE и на этапе post_mortem, и в воротах."""
        repo, s = hotfix_snapshot(tmp_path)
        write_post_mortem(repo, "S2-login-degraded",
                          "# без секций\n\nтолько текст\n")
        ctx = {"checked": set(), "evidence": set()}
        action = base.act(requested_action="post_mortem", actor_role="dev",
                          incident_ref="S2-login-degraded")
        findings = ft.check_post_mortem(s, action, ctx, 3)
        assert findings and findings[0].code == ft.INVALID_GATE
        assert not findings[0].unknown
        gate = ft.check_archive_flow3(s, action,
                                      {"checked": set(),
                                       "evidence": set()}, 3)
        assert gate and gate[0].code == ft.INVALID_GATE

    def test_post_mortem_stage_s1_with_file_no_findings(self, tmp_path):
        """TC-J48-010 (D3): этап post_mortem S1 с полным post-mortem — без
        находок (производство артефакта подтверждено)."""
        repo, s = hotfix_snapshot(tmp_path)
        write_post_mortem(repo, "S1-prod-down")
        ctx = {"checked": set(), "evidence": set()}
        action = base.act(requested_action="post_mortem", actor_role="devops",
                          incident_ref="S1-prod-down")
        assert ft.check_post_mortem(s, action, ctx, 3) == []

    def test_gate_reparses_severity_from_action(self, tmp_path):
        """TC-J48-011 (I-2 ревью): ворота перепарсивают severity из
        action.incident_ref САМИ — ctx с чужим/протухшим severity (в т.ч.
        от emergency_stabilize, D1) не переносится и не влияет на вердикт."""
        repo, s = hotfix_snapshot(tmp_path)
        # post-mortem есть только для S2-инцидента:
        write_post_mortem(repo, "S2-login-degraded")
        # ctx претендует, что инцидент классифицирован S2 (перенос D1-ctx):
        poisoned = {"checked": set(), "evidence": set(),
                    "incident_severity": "S2"}
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S1-prod-down")  # а fact — S1
        findings = ft.check_archive_flow3(s, action, poisoned, 3)
        assert findings and findings[0].code == ft.MISSING_INPUT
        assert not findings[0].unknown

    def test_correlation_rejects_foreign_incident_file(self, tmp_path):
        """TC-J48-021 (MIN-2 ревью 4.1; согласован с TC-PMG-006): корреляция
        по имени файла — по ГРАНИЦАМ, не сырой подстрокой: ref S1-prod-down
        НЕ удовлетворяется чужим файлом с надстрокой (S1-prod-down-2.md) и
        наоборот (ref S1-prod vs 2026-10-15-S1-prod-down.md) → MISSING_INPUT."""
        repo, s = hotfix_snapshot(tmp_path)
        # чужой файл: ref является ПОДСТРОКОЙ имени, но не совпадает по
        # границам (после ref идет «-2», не «.»/конец имени):
        write_post_mortem(repo, "S1-prod-down-2")
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S1-prod-down")
        findings = ft.check_archive_flow3(s, action,
                                          {"checked": set(),
                                           "evidence": set()}, 3)
        assert findings and findings[0].code == ft.MISSING_INPUT
        # и обратный случай из ревью: короткий ref S1-prod против полного
        # файла чужого инцидента S1-prod-down.md:
        for p in (repo / "test-model" / "incidents").glob("*.md"):
            p.unlink()
        write_post_mortem(repo, "S1-prod-down")
        short = base.act(requested_action="archive_change", actor_role="sa",
                         incident_ref="S1-prod")
        findings = ft.check_archive_flow3(s, short,
                                          {"checked": set(),
                                           "evidence": set()}, 3)
        assert findings and findings[0].code == ft.MISSING_INPUT
        # точный файл при этом по-прежнему находится (регресс TC-J48-006):
        exact = base.act(requested_action="archive_change", actor_role="sa",
                         incident_ref="S1-prod-down")
        assert ft.check_archive_flow3(s, exact,
                                      {"checked": set(),
                                       "evidence": set()}, 3) == []

    def test_sections_matched_by_headers_not_prose(self, tmp_path):
        """TC-J48-022 (MIN-3 ревью 4.1; D4): секции проверяются по заголовкам
        ## (регистронезависимо) — «root cause» в прозе без заголовка секцией
        не считается → DENY INVALID_GATE."""
        repo, s = hotfix_snapshot(tmp_path)
        write_post_mortem(repo, "S2-login-degraded", """# Заголовок

## Таймлайн

- 2026-10-15T10:00Z — старт initial response

корень проблемы (root cause) выяснен, action items запланированы — в прозе,
без заголовков секций.
""")
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S2-login-degraded")
        findings = ft.check_archive_flow3(s, action,
                                          {"checked": set(),
                                           "evidence": set()}, 3)
        assert findings and findings[0].code == ft.INVALID_GATE
        assert "root cause" in findings[0].detail
        assert "action items" in findings[0].detail
        # полный файл с заголовками (в т.ч. в другом регистре) проходит:
        for p in (repo / "test-model" / "incidents").glob("*.md"):
            p.unlink()
        write_post_mortem(repo, "S2-login-degraded", """## ТАЙМЛАЙН

- 2026-10-15T10:00Z — старт

## Root Cause

регрессия.

## action items

- ретрай
""")
        assert ft.check_archive_flow3(s, action,
                                      {"checked": set(),
                                       "evidence": set()}, 3) == []

    def test_new_stages_in_stage_table_flow3(self):
        """TC-J48-012 (D3): STAGE_TABLE[3] = … → deploy_rollback → post_mortem
        (dev/devops) → archive_change (sa/dev_lead/integrator); роли
        archive_change зеркалируют Флоу 1 (flow_transition.py:1754)."""
        stages = {s.action: s for s in ft.STAGE_TABLE[3]}
        order = [s.action for s in ft.STAGE_TABLE[3]]
        assert order.index("post_mortem") > order.index("deploy_rollback")
        assert order.index("archive_change") > order.index("post_mortem")
        assert stages["post_mortem"].roles == ("dev", "devops")
        assert stages["archive_change"].roles == \
            ft.STAGE_TABLE[1][-2].roles  # Stage archive_change Флоу 1
        assert stages["post_mortem"].check is ft.check_post_mortem
        assert stages["archive_change"].check is ft.check_archive_flow3


# -------------------------------------------------- enforcer: маркер Флоу 3


class TestEnforcerSeverityMarker:
    def test_invalid_severity_marker_blocked(self):
        """TC-J48-013 (FR-4): невалидный severity в маркере Флоу 3 →
        FlowMarkerError → block FLOW_MARKER_INVALID (без префикса, S4,
        lowercase); валидный S1-/S2-/S3- проходит без ошибки."""
        for bad in ("prod-down", "S4-future", "s1-lower", "INC-1", "S1"):
            with pytest.raises(enforcer.FlowMarkerError) as ei:
                enforcer.validate_scope_for_flow(3, bad)
            assert "S<1|2|3>" in str(ei.value), bad
        for good in ("S1-prod-down", "S2-login-degraded", "S3-cosmetic"):
            enforcer.validate_scope_for_flow(3, good)  # не бросает

    def test_severity_allowlist_synced_with_flow_transition(self):
        """TC-J48-014 (I-1): allowlist enforcer — ТА ЖЕ константа
        flow_transition.SEVERITY_PREFIXES (один источник истины; fallback-копия
        совпадает по составу)."""
        prefixes = enforcer._severity_prefixes()
        assert prefixes == tuple(ft.SEVERITY_PREFIXES)
        for p in ft.SEVERITY_PREFIXES:
            assert enforcer.SEVERITY_PREFIX_RE.match(f"{p}-x")
        # MIN-1 ревью 4.1: ft.SEVERITY_PREFIX_RE выведен из allowlist-тупла —
        # каждый префикс allowlist матчится и извлекается (m.group(1));
        # уровень вне allowlist (S4) — нет.
        for p in ft.SEVERITY_PREFIXES:
            m = ft.SEVERITY_PREFIX_RE.match(f"{p}-x")
            assert m and m.group(1) == p, p
        assert ft.SEVERITY_PREFIX_RE.match("S4-x") is None
        # регресс I-1: incident_severity жив (захват группы не потерян)
        assert ft.incident_severity("S2-login-degraded") == "S2"

    def test_incident_ref_passed_through_unchanged(self):
        """TC-J48-015 (tasks 1.3): scope=incident-id с severity-префиксом
        проходит в --incident-ref БЕЗ искажений (маркер не переписывает код
        инцидента)."""
        markers = {"role": "dev", "repo": "/tmp/repo", "scope": "S1-prod-down",
                   "task": None, "flow": 3, "kind": None, "paths": []}
        argv = enforcer.prepare_command(markers, 3, "emergency_stabilize")
        i = argv.index("--incident-ref")
        assert argv[i + 1] == "S1-prod-down"

    def test_sequence_prereqs_flow3_extended(self):
        """TC-J48-016 (D3): SEQUENCE_PREREQS[3] — производная STAGE_TABLE[3]:
        post_mortem после deploy_rollback, archive_change после post_mortem;
        каждый этап таблицы имеет запись (синхронизация с flow_transition)."""
        order = {s.action: i for i, s in enumerate(ft.STAGE_TABLE[3])}
        prereqs = enforcer.SEQUENCE_PREREQS[3]
        assert set(prereqs) == set(order)
        assert prereqs["post_mortem"] == {"deploy_rollback"}
        assert prereqs["archive_change"] == {"post_mortem"}
        for action, pre in prereqs.items():
            for p in pre:
                assert order[p] < order[action], (action, p)

    def test_role_actions_flow3_cover_stage_table(self):
        """TC-J48-020 (MAJ-1 ревью 4.1): каждый этап STAGE_TABLE[3]
        воспроизводим хотя бы одной ролью через enforcer.action_for_role —
        post_mortem/archive_change не выпадают в фолбэк Флоу 1 (раньше
        sa → create_change) и ни одна роль Флоу 3 не маппится в действие
        вне своей STAGE_TABLE."""
        stages = ft.STAGE_TABLE[3]
        valid_actions = {s.action for s in stages}
        covered = {}
        for stage in stages:
            roles = [r for r in stage.roles
                     if enforcer.action_for_role(r, 3) == stage.action]
            assert roles, f"этап {stage.action} не воспроизводим ни одной " \
                          f"ролью {stage.roles}"
            covered[stage.action] = roles
        assert covered["post_mortem"] == ["devops"]
        assert covered["archive_change"] == ["sa", "dev_lead"]
        assert covered["emergency_stabilize"] == ["dev"]
        # ни одна роль карты Флоу 3 не уводится в чужое действие:
        for role in ("dev", "devops", "code_reviewer", "dev_lead",
                     "integrator", "pm", "sa"):
            assert enforcer.action_for_role(role, 3) in valid_actions, role


# ------------------------------------------- NFR-2: append-only + NFR-3 репрессия


class TestAppendOnlyAndIsolation:
    def test_gate_checks_do_not_mutate_incidents_dir(self, tmp_path):
        """TC-J48-017 (NFR-2): вызовы check_post_mortem/check_archive_flow3 не
        пишут в test-model/incidents/ — существующие файлы не переписываются
        и не удаляются (append-only), новых файлов не появляется."""
        repo, s = hotfix_snapshot(tmp_path)
        pm = write_post_mortem(repo, "S2-login-degraded")
        before = sorted(p.name for p in pm.parent.glob("*"))
        content = pm.read_bytes()
        action = base.act(requested_action="archive_change", actor_role="sa",
                          incident_ref="S2-login-degraded")
        ctx = {"checked": set(), "evidence": set()}
        ft.check_post_mortem(s, action, dict(ctx), 3)
        ft.check_archive_flow3(s, action, dict(ctx), 3)
        assert pm.read_bytes() == content
        assert sorted(p.name for p in pm.parent.glob("*")) == before

    def test_flows_1_2_4_5_stage_tables_unchanged(self):
        """TC-J48-018 (NFR-3/задача 2.5): новые этапы/функции проведены ТОЛЬКО
        в STAGE_TABLE[3]; состав действий Флоу 1/2/4/5 не изменился."""
        expected = {
            1: ("approve_requirements", "create_change", "architecture_review",
                "dev_task", "design_task", "code_review", "accept_review",
                "merge_task", "qa_cases", "qa_review", "qa_impact_analysis",
                "qa_automation", "design_validation", "archive_change",
                "release"),
            2: ("bug_fix", "code_review", "accept_review", "merge_task"),
            4: ("chore_task", "code_review", "accept_review", "merge_task"),
            5: ("express_task", "express_close"),
        }
        for flow, actions in expected.items():
            got = tuple(s.action for s in ft.STAGE_TABLE[flow])
            assert got == actions, flow

    def test_j48_checks_are_flow3_only(self, tmp_path):
        """TC-J48-019 (NFR-3): check_archive_flow3/check_post_mortem на
        Флоу 1/2/4/5 возвращают [] — правило физически недостижимо из других
        флоу (design D2 п.4)."""
        repo, s1 = hotfix_snapshot(tmp_path)
        reg = base.make_registry(tmp_path)
        for flow in (1, 2, 4, 5):
            s = base.snapshot_for(repo, reg, flow=flow,
                                  change_id="add-widget")
            action = base.act(requested_action="archive_change",
                              actor_role="sa", incident_ref="S1-prod-down")
            ctx = {"checked": set(), "evidence": set()}
            assert ft.check_archive_flow3(s, action, ctx, flow) == [], flow
            assert ft.check_post_mortem(s, action, ctx, flow) == [], flow
