# -*- coding: utf-8 -*-
"""BUG-AF-RECHECK-002: строка bypass в goal выдавала себя за решение Заказчика.

Фикс: маркер 'flow: bypass --by customer' — только ЗАЯВКА (goal формирует
оркестратор; цитата маркера неотличима от распоряжения). Обход действует
ТОЛЬКО при действующей записи в реестре решений Заказчика
~/.hermes/state/flow-bypass-decisions.json ([{repo, scope, action,
decision_ref, expires}], expires — UTC ISO), найденной по
(repo, scope, action). Нет записи / просрочена / другой scope или action →
bypass-ветка не срабатывает (обычная проверка, как правило DENY). Аудит
log_bypass дополнен decision_ref + match.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402

MARKER = enforcer.BYPASS_MARKER
REPO = "/tmp/bypass-proj"
SCOPE = "add-widget"
ACTION = "dev_task"


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи/реестр в tmp (реальный ~/.hermes не используется)."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(tmp_path / "state" / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
    monkeypatch.delenv("FLOW_BYPASS_REGISTRY", raising=False)
    yield state


def delegate_args(goal: str) -> dict:
    return {"goal": goal}


def write_registry(tmp_path: Path, entries: list[dict]) -> Path:
    """Фикстура реестра: tmp-файл через env FLOW_BYPASS_REGISTRY (изоляция)."""
    p = tmp_path / "state" / "flow-bypass-decisions.json"
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return p


def future(hours: float = 1.0) -> str:
    return (datetime.now(timezone.utc) +
            timedelta(hours=hours)).isoformat()


def past(hours: float = 1.0) -> str:
    return (datetime.now(timezone.utc) -
            timedelta(hours=hours)).isoformat()


def bypass_goal(extra: str = "") -> str:
    return (f"flow: flow=1 role=dev repo={REPO} scope={SCOPE} "
            "paths=src/x.py\n"
            f"{MARKER}\n{extra}")


def goal_with_quoted_marker() -> str:
    """Цитата маркера внутри текста задачи (не строка-распоряжение)."""
    return (f"flow: flow=1 role=dev repo={REPO} scope={SCOPE} "
            "paths=src/x.py\n"
            f"Задача: документируй, почему строка «{MARKER}» запрещена.\n")


def install_fake_run(monkeypatch, rc: int = 0) -> list:
    calls: list[list[str]] = []

    def _fake(argv, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess([], rc, "ok", "")

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    return calls


def _log_entries(plugin_env) -> list[dict]:
    return [json.loads(l) for l in
            (plugin_env / "flow-enforcer.log").read_text("utf-8").splitlines()
            if l.strip()]


# ------------------------------------------------------------ unit: реестр


def test_find_decision_matches_and_expires(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-01: запись по (repo, scope, action) находится;
    истекшая/чужая — нет; битый/отсутствующий expires — не действует
    (fail-closed)."""
    reg = write_registry(tmp_path, [
        {"repo": REPO, "scope": SCOPE, "action": ACTION,
         "decision_ref": "ОВ-42", "expires": future()},
        {"repo": REPO, "scope": SCOPE, "action": ACTION,
         "decision_ref": "старое", "expires": past()},
        {"repo": REPO, "scope": "other-change", "action": ACTION,
         "decision_ref": "чужой scope", "expires": future()},
        {"repo": REPO, "scope": SCOPE, "action": "code_review",
         "decision_ref": "чужой action", "expires": future()},
        {"repo": REPO, "scope": SCOPE, "action": ACTION,
         "decision_ref": "без срока"},
    ])
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    d = enforcer.find_bypass_decision(REPO, SCOPE, ACTION)
    assert d is not None and d["decision_ref"] == "ОВ-42"
    # действие, на которое решений нет вообще
    assert enforcer.find_bypass_decision(REPO, SCOPE, "design_task") is None
    # чужой repo
    assert enforcer.find_bypass_decision("/tmp/other", SCOPE, ACTION) is None


def test_missing_or_broken_registry_is_no_bypass(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-02: нет файла / битый JSON / не список — обхода нет
    (ошибка проверки решения не превращается в разрешение)."""
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY",
                       str(tmp_path / "state" / "absent.json"))
    assert enforcer.find_bypass_decision(REPO, SCOPE, ACTION) is None
    bad = tmp_path / "state" / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(bad))
    assert enforcer.find_bypass_decision(REPO, SCOPE, ACTION) is None
    notlist = tmp_path / "state" / "dict.json"
    notlist.write_text('{"repo": "%s"}' % REPO, encoding="utf-8")
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(notlist))
    assert enforcer.find_bypass_decision(REPO, SCOPE, ACTION) is None


# --------------------------------------------------------- хук: bypass-ветка


def test_marker_without_decision_blocks(monkeypatch):
    """TC-AF-RECHECK-002-03: bypass-текст БЕЗ подтвержденного решения →
    отклонение (обычная проверка prepare, fixture-repo не git → block)."""
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(bypass_goal()), "b1")
    assert res is not None and res["action"] == "block"
    assert "flowctl prepare отклонил" in res["message"]


def test_quoted_marker_without_decision_is_inert(monkeypatch):
    """TC-AF-RECHECK-002-04: цитирование маркера в описании само по себе
    ничего не меняет — та же обычная проверка, без bypass-лога."""
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(goal_with_quoted_marker()), "b2")
    assert res is not None and res["action"] == "block"


def test_marker_with_decision_passes_and_logs(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-05: с действующей записью реестра — пропуск;
    bypass-лог несет decision_ref и match (что именно совпало)."""
    reg = write_registry(tmp_path, [
        {"repo": REPO, "scope": SCOPE, "action": ACTION,
         "decision_ref": "ОВ-42/2026-10-13", "expires": future()}])
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(bypass_goal()), "b3")
    assert res is None  # bypass: prepare даже не понадобился
    blog = plugin_env_path(tmp_path) / "flow-enforcer-bypass.log"
    assert blog.is_file()
    entry = json.loads(blog.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["task_id"] == "b3"
    assert entry["decision_ref"] == "ОВ-42/2026-10-13"
    assert entry["match"] == {"repo": REPO, "scope": SCOPE,
                              "action": ACTION}


def plugin_env_path(tmp_path) -> Path:
    import os
    return Path(os.environ["FLOW_ENFORCER_STATE_DIR"])


def test_expired_decision_does_not_pass(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-06: истекшее решение — bypass-ветка не срабатывает
    (WARNING bypass_denied в логе, обычный DENY)."""
    reg = write_registry(tmp_path, [
        {"repo": REPO, "scope": SCOPE, "action": ACTION,
         "decision_ref": "истекшее", "expires": past()}])
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(bypass_goal()), "b4")
    assert res is not None and res["action"] == "block"
    assert not (plugin_env_path(tmp_path) /
                "flow-enforcer-bypass.log").exists()
    events = [e.get("event") for e in _log_entries(plugin_env_path(tmp_path))]
    assert "bypass_denied" in events


def test_decision_other_scope_does_not_pass(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-07: решение чужого scope — отклонение (исключение
    действует только на указанный scope/действие)."""
    reg = write_registry(tmp_path, [
        {"repo": REPO, "scope": "other-change", "action": ACTION,
         "decision_ref": "чужой scope", "expires": future()}])
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(bypass_goal()), "b5")
    assert res is not None and res["action"] == "block"


def test_bypass_with_broken_registry_fails_closed(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-08: битый реестр при маркере bypass — не разрешение:
    обычная проверка ворот (block), bypass-лога нет."""
    bad = tmp_path / "state" / "bad.json"
    bad.write_text("не json", encoding="utf-8")
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(bad))
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(bypass_goal()), "b6")
    assert res is not None and res["action"] == "block"
    assert not (plugin_env_path(tmp_path) /
                "flow-enforcer-bypass.log").exists()


def test_bypass_skips_prepare_and_paths_gate(tmp_path, monkeypatch):
    """TC-AF-RECHECK-002-09: действующий bypass идет ДО kind/paths-ворот и
    prepare: без путей в маркере и с несуществующим repo — пропуск."""
    reg = write_registry(tmp_path, [
        {"repo": "/tmp/never-prepared", "scope": SCOPE, "action": ACTION,
         "decision_ref": "ОВ-43", "expires": future()}])
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    goal = (f"flow: flow=1 role=dev repo=/tmp/never-prepared scope={SCOPE}\n"
            f"{MARKER}\n")  # без paths → без bypass был бы PATHS_MISSING
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "b7")
    assert res is None


# ---------------------------------------- формат scope Флоу 2 (BUG-...-NNN)
#
# Синхронизация validate_scope_for_flow с правилом имен репортов
# test-model/bugs/ расширенным в 5c21489: BUG-<КОМПЛЕКС>-NNN
# (канонично r'^BUG-(?:[A-Z0-9]+-)*\d{3}$').


@pytest.mark.parametrize("scope", ["BUG-AF-RECHECK-001", "BUG-001"])
def test_flow2_scope_bug_complex_valid(scope):
    """Ф2 scope: BUG-<КОМПЛЕКС>-NNN и классический BUG-NNN оба валидны."""
    enforcer.validate_scope_for_flow(2, scope)  # не бросает


@pytest.mark.parametrize("scope", [
    "bug-001",                # lowercase — отклонение (нет IGNORECASE)
    "BUG-AF_RECHECK-001",     # underscore — не дефис-разделитель
    "BUG-AF-RECHECK-001A",    # мусорный суффикс после NNN
    "BUG-AF-RECHECK-",        # нет финального NNN
    "AF-RECHECK-001",         # нет префикса BUG-
])
def test_flow2_scope_bug_complex_invalid(scope):
    """Ф2 scope: lowercase / underscore / суффикс / отсутствие NNN —
    отклонение (FlowMarkerError → block FLOW_MARKER_INVALID)."""
    with pytest.raises(enforcer.FlowMarkerError):
        enforcer.validate_scope_for_flow(2, scope)
