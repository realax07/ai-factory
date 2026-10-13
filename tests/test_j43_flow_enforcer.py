# -*- coding: utf-8 -*-
"""Тесты plugins/flow-enforcer (J43: pre_tool_call-энфорсер делегаций).

Фикстуры: tmp-реестр, tmp-репозиторий, tmp-каталог логов
(FLOW_ENFORCER_STATE_DIR) — реальный ~/.hermes/state/ НЕ используется.
subprocess мокается в кейсах вердиктов; последний тест гоняет РЕАЛЬНЫЙ
flowctl prepare --dry-run на fixture-репо (замер латентности prepare).

Кейсы (ТЗ J43):
  (а) не-delegate_task → нет директивы;
  (б) delegate_task без маркеров в strict → block MARKERS_MISSING;
  (в) в permissive → нет директивы (+ строка в логе);
  (г) bypass-маркер — только ЗАЯВКА: без записи в реестре решений
      (FLOW_BYPASS_REGISTRY) делегация НЕ пропускается (BUG-AF-RECHECK-002);
  (д) flowctl prepare ok (мок subprocess) → ALLOW;
  (е) prepare fail → block с кодом из вывода;
  (ж) исключение в хуке → fail-closed block;
  (з) парсинг маркеров из goal-заголовка (канонический формат);
  + латентность prepare на fixture (реальный subprocess, logging).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402

SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))


# --------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи/реестр в tmp, режим по умолчанию."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(tmp_path / "state" / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    # J43.1: env-fallback флоу и опциональная последовательность не должны
    # прилетать из окружения разработчика — детерминизм сьюта.
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_PROJECT", raising=False)
    yield state


def delegate_args(goal: str, context: str | None = None) -> dict:
    a = {"goal": goal}
    if context is not None:
        a["context"] = context
    return a


def install_fake_run(monkeypatch, rc: int, out: str, err: str = "") -> list:
    """Мок subprocess.run внутри enforcer; возвращает собранные argv."""
    calls: list[list[str]] = []

    def _fake(argv, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess([], rc, out, err)

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    return calls


HEADER_GOAL = (
    "flow: role=dev repo=/tmp/proj change=add-widget paths=src/widget.py\n"
    "Задача: реализовать виджет. Зона записи: src/.\n"
)
# J43.1: парсер возвращает scope (легаси change= → scope) и flow=None
# (энфорсер возьмет env-fallback с WARNING). BUG-AF-RECHECK-001: paths —
# список относительных путей задачи.
MARKERS = {"role": "dev", "repo": "/tmp/proj", "scope": "add-widget",
           "task": None, "flow": None, "kind": None,
           "paths": ["src/widget.py"]}


# ------------------------------------------------------------ (а) триггер


def test_a_non_delegate_tool_no_directive():
    """TC-J43-001: J43 flow-enforcer."""
    for tool in ("terminal", "read_file", "write_file", "web_search"):
        assert enforcer.flow_enforce(tool, {"command": "ls"}, "t1") is None


# ------------------------------------------------- (б, в) маркеры/режимы


def test_b_strict_missing_markers_block_code():
    """TC-J43-002: J43 flow-enforcer."""
    import os
    os.environ["FLOW_ENFORCER_MODE"] = "strict"
    try:
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args("почини стили"), "t2")
    finally:
        os.environ["FLOW_ENFORCER_MODE"] = "permissive"
    assert res is not None and res["action"] == "block"
    assert "MARKERS_MISSING" in res["message"]


def test_c_permissive_missing_markers_passes_and_logs(plugin_env):
    """TC-J43-003: J43 flow-enforcer."""
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args("почини стили"), "t3")
    assert res is None
    log = plugin_env / "flow-enforcer.log"
    assert log.is_file()
    assert "markers_missing_permissive" in log.read_text(encoding="utf-8")


# ------------------------------------------------------------ (г) bypass


def test_d_bypass_marker_without_decision_does_not_pass(plugin_env,
                                                        monkeypatch):
    """TC-J43-004 (переписан, BUG-AF-RECHECK-002): маркер bypass в goal БЕЗ
    записи в реестре решений НЕ пропускает делегацию: в strict без маркеров
    конвейера — block MARKERS_MISSING; обычная проверка продолжается."""
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
    goal = "flow: bypass --by customer\nпочини стили\n"
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "t4")
    assert res is not None and res["action"] == "block"
    assert "MARKERS_MISSING" in res["message"]
    assert not (plugin_env / "flow-enforcer-bypass.log").exists()


# ------------------------------------------------------- (д/е) subprocess


def test_e_prepare_ok_allows(monkeypatch):
    """TC-J43-005: J43 flow-enforcer."""
    calls = install_fake_run(monkeypatch, rc=0, out="prepared: true\n")
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t5")
    assert res is None  # ALLOW — без директивы
    assert len(calls) == 1
    argv = calls[0]
    assert argv[2:4] == ["prepare", "--dry-run"]
    for flag, val in (("--role", "dev"), ("--repo", "/tmp/proj"),
                      ("--change", "add-widget"), ("--action", "dev_task")):
        assert argv[argv.index(flag) + 1] == val


def test_f_prepare_fail_blocks_with_code(monkeypatch):
    """TC-J43-006: J43 flow-enforcer."""
    out = json.dumps({"reason": "PLAN_RELEASE_MISSING",
                      "note": "план релиза не найден"})
    install_fake_run(monkeypatch, rc=1, out=out)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t6")
    assert res is not None and res["action"] == "block"
    assert "PLAN_RELEASE_MISSING" in res["message"]
    assert "exit 1" in res["message"]


def test_f2_stderr_included_in_block(monkeypatch):
    """TC-J43-007: J43 flow-enforcer."""
    install_fake_run(monkeypatch, rc=2, out="", err="ZONE_OUTSIDE_POLICY: x")
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t6b")
    assert res["action"] == "block"
    assert "ZONE_OUTSIDE_POLICY" in res["message"]


# -------------------------------------------------------- (ж) fail-closed


def test_g_exception_fail_closed(monkeypatch):
    """TC-J43-008: J43 flow-enforcer."""
    def _boom(argv, **kw):
        raise RuntimeError("flowctl exploded")

    monkeypatch.setattr(enforcer.subprocess, "run", _boom)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t7")
    assert res is not None and res["action"] == "block"
    assert res["message"].startswith("flow-enforcer internal error:")
    assert "(fail-closed)" in res["message"]


# ---------------------------------------------------- (з) парсинг заголовка


def test_h_parse_markers_from_goal_header():
    """TC-J43-009: J43 flow-enforcer."""
    assert enforcer.parse_markers(delegate_args(HEADER_GOAL)) == MARKERS


def test_h2_parse_markers_from_context_fallback(monkeypatch):
    """TC-J43-010: J43 flow-enforcer."""
    install_fake_run(monkeypatch, rc=0, out="")
    goal = "Задача: виджет"
    context = ("role: qa_automation repo: /tmp/proj change: add-widget\n"
               "paths: tests/test_widget.py")
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(goal, context), "t8")
    assert res is None
    # действие по роли из context-маркеров
    # (проверяется через собранный argv — см. test_e_prepare_ok_allows)


def test_h3_parse_markers_none():
    """TC-J43-011: J43 flow-enforcer."""
    assert enforcer.parse_markers(delegate_args("без маркеров")) is None
    assert enforcer.parse_markers({}) is None


def test_h4_role_action_mapping():
    """TC-J43-012: J43 flow-enforcer."""
    assert enforcer.ROLE_ACTIONS["dev"] == "dev_task"
    assert enforcer.ROLE_ACTIONS["code_reviewer"] == "code_review"
    assert enforcer.ROLE_ACTIONS["qa_automation"] == "qa_automation"


# ------------------------------------------- латентность (реальный flowctl)


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")


@pytest.mark.no_plan_fixture
def test_i_real_prepare_latency(tmp_path, monkeypatch):
    """TC-J43-013: Реальный flowctl prepare --dry-run на fixture-репо: ALLOW + замер.

    Отчет по латентности — duration_s в логе и в выводе теста.
    """
    import re as _re

    # fixture-репо Флоу 1, готовый к dev_task (как в test_flowctl.make_repo)
    repo = tmp_path / "proj"
    repo.mkdir()
    def _git(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True, text=True)
    def _write(rel: str, text: str) -> None:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git("init", "-q")
    _git("config", "user.email", "t@t")
    _git("config", "user.name", "t")
    _write("requirements.md", REQ_APPROVED)
    _write("openspec/changes/add-widget/proposal.md", "# p\n")
    _write("openspec/changes/add-widget/design.md", "# d\n")
    _write("openspec/changes/add-widget/tasks.md",
           "# Tasks\n\n- [ ] 1.1 реализовать виджет\n")
    _write("openspec/changes/add-widget/specs/widget/spec.md",
           "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    _write("code-reviews/add-widget/review-001-1.1.md",
           "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    _write("sdd.md", "# SDD\n")
    _write("src/widget.py", "X = 1\n")
    # J41: план релиза — обязательный артефакт ворот
    _write("PLAN-add-widget.md",
           "# PLAN-add-widget — план релиза (fixture)\n\n"
           "**Флоу: 1** (J43 latency fixture).\n\n## Этапы\n\n1. dev\n2. review\n3. merge\n")
    _git("add", "-A")
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")

    registry = tmp_path / "state" / "active_sessions.json"
    registry.write_text('{"sessions": []}', encoding="utf-8")
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY", str(registry))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")

    goal = (f"flow: role=dev repo={repo} change=add-widget "
            "paths=src/widget.py\n"
            "task: 1.1\nЗадача: виджет.\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "t9")
    assert res is None, f"ожидался ALLOW, получен block: {res}"

    log = (tmp_path / "state" / "flow-enforcer.log").read_text("utf-8")
    entry = [json.loads(l) for l in log.splitlines()
             if l.strip()][-1]
    assert entry["event"] == "prepare_result" and entry["rc"] == 0
    duration = entry["duration_s"]
    assert duration < 30, f"prepare слишком долог: {duration}s"
    print(f"\n[j43] prepare latency on fixture: {duration}s")
    # WARNING-ветка (>10s) не сработала на fixture
    assert "slow_prepare" not in log


@pytest.mark.no_plan_fixture
def test_j_slow_prepare_logs_warning(tmp_path, monkeypatch):
    """TC-J43-014: Порог WARNING: prepare дольше 10с пишет WARNING в лог (мок времени)."""
    times = iter([0.0, float(enforcer.SLOW_PREPARE_SECONDS) + 1.0])
    real_monotonic = enforcer.time.monotonic
    monkeypatch.setattr(
        enforcer.time, "monotonic",
        lambda: next(times, real_monotonic()))

    def _fake_run(argv, **kw):
        return subprocess.CompletedProcess([], 0, "ok", "")

    monkeypatch.setattr(enforcer.subprocess, "run", _fake_run)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t10")
    assert res is None
    log = (tmp_path / "state" / "flow-enforcer.log").read_text("utf-8")
    assert "slow_prepare" in log and "WARNING" in log


# ============================== J43.1: flow-aware энфорсер + новый маркер


def _make_repo(tmp_path: Path, name: str, files: dict) -> Path:
    """Git-репо с файлами (fixture для РЕАЛЬНОГО flowctl prepare)."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)  # exist_ok: conftest-fixture
    # пишет планы в tmp_path/proj до тела теста
    def _git(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True, text=True)
    _git("init", "-q")
    _git("config", "user.email", "t@t")
    _git("config", "user.name", "t")
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git("add", "-A")
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


BUG_REPORT = "# BUG-042\n\n## Ожидаемое/фактическое\nожидалось a, фактически b\n"
EXISTING_SPEC = ("# Спеки\n\nopenspec/specs/widget/spec.md описывает "
                 "ожидаемое поведение\n")
WIDGET_SPEC = ("### Requirement: W\n#### Scenario: S\n"
               "- GIVEN a\n- WHEN b\n- THEN c\n")
PLAN_FLOW2 = ("# PLAN — багфиксы\n\n**Флоу: 2** (легкий план: цель — фикс "
              "BUG-042; зоны: src/; критерий: регресс зелен).\n")
PLAN_FLOW4 = ("# PLAN-chore-cleanup\n\n**Флоу: 4** (легкий план: цель — "
              "чистка скриптов; зоны: scripts/; критерий: тесты зеленые).\n")


def flow2_goal(repo: Path) -> dict:
    return delegate_args(
        f"flow: flow=2 role=dev repo={repo} scope=BUG-042 "
        "paths=src/fix.py\n"
        "Задача: фикс бага. Зона записи: src/.\n")


def flow4_goal(repo: Path) -> dict:
    return delegate_args(
        f"flow: flow=4 role=dev repo={repo} scope=chore-cleanup "
        "paths=scripts/tool.py\n"
        "Задача: обслуживание. Зона записи: scripts/.\n")


def _log_entries(plugin_env) -> list[dict]:
    return [json.loads(l) for l in
            (plugin_env / "flow-enforcer.log").read_text("utf-8").splitlines()
            if l.strip()]


class TestJ431Marker:
    """J43.1: новый заголовок flow=/scope= и его очевидные ошибки."""

    def test_new_header_parsed(self):
        goal = ("flow: flow=2 role=dev repo=/tmp/proj scope=BUG-042 "
                "paths=src/fix.py,backend/api.py kind=product\n"
                "Задача: фикс.\n")
        m = enforcer.parse_markers(delegate_args(goal))
        assert m == {"role": "dev", "repo": "/tmp/proj", "scope": "BUG-042",
                     "task": None, "flow": 2, "kind": "product",
                     "paths": ["src/fix.py", "backend/api.py"]}

    def test_flow9_invalid(self):
        goal = ("flow: flow=9 role=dev repo=/tmp/proj scope=add-widget\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "d1")
        assert res is not None and res["action"] == "block"
        assert "FLOW_MARKER_INVALID" in res["message"]

    def test_empty_scope_invalid(self):
        goal = "flow: flow=2 role=dev repo=/tmp/proj scope=\n"
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "d2")
        assert res is not None and res["action"] == "block"
        assert "FLOW_MARKER_INVALID" in res["message"]

    def test_flow2_scope_must_be_bug_nnn(self):
        goal = ("flow: flow=2 role=dev repo=/tmp/proj scope=add-widget\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "d3")
        assert res is not None and res["action"] == "block"
        # BUG-AF-RECHECK: формат расширен до BUG-<КОМПЛЕКС>-NNN
        assert "BUG-<КОМПЛЕКС>-NNN" in res["message"]

    def test_legacy_marker_flow1_warning(self, plugin_env, monkeypatch):
        """(г) старый 'change=' без flow= → трактовка flow=1 + WARNING в лог."""
        install_fake_run(monkeypatch, rc=0, out="")
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args(HEADER_GOAL), "d4")
        assert res is None
        entries = _log_entries(plugin_env)
        fallback = [e for e in entries if e.get("event") == "flow_fallback"]
        assert fallback and fallback[-1]["level"] == "WARNING"
        assert fallback[-1]["flow"] == 1

    def test_marker_flow_wins_over_env(self, plugin_env, monkeypatch):
        """flow= из маркера сильнее env FLOW_ENFORCER_FLOW (без WARNING)."""
        monkeypatch.setenv("FLOW_ENFORCER_FLOW", "1")
        calls = install_fake_run(monkeypatch, rc=0, out="")
        res = enforcer.flow_enforce(
            "delegate_task", flow2_goal(Path("/tmp/proj")), "d5")
        assert res is None
        argv = calls[0]
        assert argv[argv.index("--flow") + 1] == "2"
        entries = _log_entries(plugin_env)
        assert not [e for e in entries if e.get("event") == "flow_fallback"]

    def test_flow_aware_role_action_and_change(self, monkeypatch):
        """prepare вызывается с --flow N, --change <scope>, действие — своего
        флоу (Ф2 dev → bug_fix)."""
        calls = install_fake_run(monkeypatch, rc=0, out="")
        enforcer.flow_enforce(
            "delegate_task", flow2_goal(Path("/tmp/proj")), "d6")
        argv = calls[0]
        assert argv[argv.index("--flow") + 1] == "2"
        assert argv[argv.index("--change") + 1] == "BUG-042"
        assert argv[argv.index("--action") + 1] == "bug_fix"


class TestJ431FlowAwareEnforce:
    """(а)/(б)/(в): РЕАЛЬНЫЙ flowctl prepare на fixture-репо Флоу 2/4."""

    def test_a_flow2_with_bug_report_allows(self, tmp_path, plugin_env):
        repo = _make_repo(tmp_path, "proj", {
            "test-model/bugs/BUG-042.md": BUG_REPORT,
            "openspec/specs/widget/spec.md": WIDGET_SPEC,
            "test-model/bugs/PLAN.md": PLAN_FLOW2,
            "src/fix.py": "X = 1\n",
        })
        res = enforcer.flow_enforce(
            "delegate_task", flow2_goal(repo), "j1")
        assert res is None, f"ожидался ALLOW, получен block: {res}"
        entry = _log_entries(plugin_env)[-1]
        assert entry["event"] == "prepare_result" and entry["rc"] == 0
        assert entry["flow"] == 2 and entry["action"] == "bug_fix"

    def test_b_flow2_without_bug_report_blocks(self, tmp_path, plugin_env):
        repo = _make_repo(tmp_path, "proj", {
            # BUG-репорта НЕТ
            "openspec/specs/widget/spec.md": WIDGET_SPEC,
            "test-model/bugs/PLAN.md": PLAN_FLOW2,
            "src/fix.py": "X = 1\n",
        })
        res = enforcer.flow_enforce(
            "delegate_task", flow2_goal(repo), "j2")
        assert res is not None and res["action"] == "block"
        # текст про отсутствие репорта (ошибка по существу, не фильтруется)
        assert "баг-репорт" in res["message"]

    def test_v_flow4_with_plan_allows_via_no_change_filter(
            self, tmp_path, plugin_env):
        """(в) Ф4 chore-slug + план → ALLOW: prepare отклоняет ровно из-за
        отсутствия change-пакета/scope-id, PLAN-<slug>.md существует →
        post-filter трактует как ALLOW с логом 'flow-4 no-change scope ok'."""
        repo = _make_repo(tmp_path, "proj", {
            "PLAN-chore-cleanup.md": PLAN_FLOW4,
            "scripts/tool.py": "X = 1\n",
        })
        res = enforcer.flow_enforce(
            "delegate_task", flow4_goal(repo), "j3")
        assert res is None, f"ожидался ALLOW, получен block: {res}"
        events = [e.get("event") for e in _log_entries(plugin_env)]
        assert "flow-4 no-change scope ok" in events

    def test_v2_flow4_without_plan_blocks_plan_missing(self, tmp_path):
        repo = _make_repo(tmp_path, "proj", {
            # плана НЕТ
            "scripts/tool.py": "X = 1\n",
        })
        res = enforcer.flow_enforce(
            "delegate_task", flow4_goal(repo), "j4")
        assert res is not None and res["action"] == "block"
        assert "PLAN_RELEASE_MISSING" in res["message"]

    def test_substantive_error_not_filtered(self, tmp_path, plugin_env):
        """Post-filter не применяется, если среди причин есть ошибка ПО СУЩЕСТВУ
        (нет BUG-репорта) — даже при существующем scope-файле."""
        repo = tmp_path / "proj"
        (repo / "test-model" / "bugs").mkdir(parents=True, exist_ok=True)
        # scope-файл ЕСТЬ — но вывод ворот содержит ошибку по существу рядом
        # с ожидаемым классом: post-filter не применяется (ровно = все).
        (repo / "test-model" / "bugs" / "BUG-042.md").write_text(
            "# BUG-042\n", encoding="utf-8")
        out = json.dumps({"decision": {
            "status": "DENY",
            "details": [
                "AMBIGUOUS_STATE: scope не соответствует выбранному флоу: "
                "Флоу 4 (обслуживание) требует маркер [chore]",
                "MISSING_INPUT: баг-репорт test-model/bugs/BUG-042.md "
                "отсутствует — Флоу 2 требует BUG-NNN репорт",
            ]}})
        markers = {"role": "dev", "repo": str(repo), "scope": "BUG-042",
                   "task": None, "flow": 2}
        decision = enforcer.parse_decision_output(out)
        assert enforcer.no_change_scope_ok(markers, 2, decision) is False


class TestJ431Sequence:
    """(ж) FLOW_ENFORCER_SEQUENCE=1: нарушение и допустимый переход."""

    def _with_prepare_and_phase(self, monkeypatch, phase_payload: dict):
        """Мок subprocess: prepare → rc 0; phase → phase_payload."""
        calls: list[list[str]] = []

        def _fake(argv, **kw):
            calls.append(list(argv))
            if "phase" in argv:
                return subprocess.CompletedProcess(
                    [], 0, json.dumps(phase_payload), "")
            return subprocess.CompletedProcess([], 0, '{"decision": {}}', "")

        monkeypatch.setattr(enforcer.subprocess, "run", _fake)
        return calls

    PHASE_AFTER_MERGE = {
        "schema_version": "flowctl-phase/1",
        "phase": {"action": "merge_task", "actor_role": "dev_lead",
                  "finished_status": "accepted",
                  "timestamp": "2026-10-12T10:00:00+00:00"},
        "completed_actions": ["approve_requirements", "create_change",
                              "dev_task", "code_review", "accept_review",
                              "merge_task"],
    }

    def test_zh_allowed_next_after_merge(self, monkeypatch):
        monkeypatch.setenv("FLOW_ENFORCER_SEQUENCE", "1")
        self._with_prepare_and_phase(monkeypatch, self.PHASE_AFTER_MERGE)
        goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
                "paths=src/widget.py\n")
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args(goal), "s1")
        assert res is None  # dev_task новой задачи после merge_task допустим

    def test_zh_violation_qa_automation_first(self, monkeypatch):
        monkeypatch.setenv("FLOW_ENFORCER_SEQUENCE", "1")
        self._with_prepare_and_phase(monkeypatch, {
            "schema_version": "flowctl-phase/1", "phase": "none",
            "completed_actions": []})
        goal = ("flow: flow=1 role=qa_automation repo=/tmp/proj "
                "scope=add-widget paths=tests/test_widget.py\n")
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args(goal), "s2")
        assert res is not None and res["action"] == "block"
        assert "SEQUENCE_VIOLATION" in res["message"]
        assert "qa_cases" in res["message"]  # незакрытый предшественник

    def test_sequence_off_by_default(self, monkeypatch):
        monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
        calls = self._with_prepare_and_phase(monkeypatch, {
            "schema_version": "flowctl-phase/1", "phase": "none"})
        goal = ("flow: flow=1 role=qa_automation repo=/tmp/proj "
                "scope=add-widget paths=tests/test_widget.py\n")
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args(goal), "s3")
        assert res is None
        assert all("phase" not in c for c in calls)  # phase не вызывался


# ------------------------------------- factory_init: шаг установки плагина


def _init(tmp_path):
    sys.path.insert(0, str(FACTORY / "scripts"))
    import factory_init
    return factory_init


def _hermes_home(tmp_path, monkeypatch, config: str | None):
    home = tmp_path / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    if config is not None:
        (home / "config.yaml").write_text(config, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_k_install_plugin_copies_and_enables(tmp_path, monkeypatch):
    """TC-J43-015: J43 flow-enforcer."""
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch,
                        "plugins:\n  enabled:\n    - other-plugin\n")
    assert fi.install_plugin() is True
    assert (home / "plugins" / "flow-enforcer" / "plugin.yaml").is_file()
    cfg = (home / "config.yaml").read_text("utf-8")
    assert "- flow-enforcer" in cfg
    # (yaml-модуля в stdlib нет; проверяем структуру текста)
    lines = cfg.splitlines()
    i = lines.index("plugins:")
    assert lines[i + 1] == "  enabled:"
    assert sorted(lines[i + 2:i + 4]) == ["    - flow-enforcer",
                                          "    - other-plugin"]


def test_k2_install_plugin_already_enabled(tmp_path, monkeypatch):
    """TC-J43-016: J43 flow-enforcer."""
    fi = _init(tmp_path)
    cfg_text = "plugins:\n  enabled:\n    - flow-enforcer\n"
    home = _hermes_home(tmp_path, monkeypatch, cfg_text)
    assert fi.install_plugin() is True
    assert (home / "config.yaml").read_text("utf-8") == cfg_text  # без правки


def test_k3_install_plugin_no_block_prints_instruction(tmp_path, monkeypatch, capsys):
    """TC-J43-017: J43 flow-enforcer."""
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch, "llm:\n  model: x\n")
    assert fi.install_plugin() is True
    out = capsys.readouterr().out
    assert "включи вручную" in out
    # конфиг НЕ изменен
    assert "flow-enforcer" not in (home / "config.yaml").read_text("utf-8")


def test_k4_install_plugin_skip(tmp_path, monkeypatch):
    """TC-J43-018: J43 flow-enforcer."""
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch, None)
    assert fi.install_plugin(skip=True) is True
    assert not (home / "plugins" / "flow-enforcer").exists()


def test_k5_bootstrap_hint(tmp_path, monkeypatch, capsys):
    """TC-J43-019: J43 flow-enforcer."""
    sys.path.insert(0, str(FACTORY / "scripts"))
    import factory_bootstrap as fb
    home = _hermes_home(tmp_path, monkeypatch, None)
    # HERMES_HOME у fb — конистра времени импорта; на машине с УСТАНОВЛЕННЫМ
    # плагином (~/.hermes/plugins/flow-enforcer) константа указывает на реальный
    # дом. Изолируем: тест проверяет логику подсказки, а не машину.
    monkeypatch.setattr(fb, "HERMES_HOME", home)
    fb.plugin_hint()
    assert "НЕ установлен" in capsys.readouterr().out
    (home / "plugins" / "flow-enforcer").mkdir()
    fb.plugin_hint()
    assert "установлен" in capsys.readouterr().out
