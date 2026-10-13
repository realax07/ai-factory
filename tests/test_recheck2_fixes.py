# -*- coding: utf-8 -*-
"""Фиксы ревью BUG-AF-RECHECK (итерация 2, ветка pipeline/bug-af-recheck).

Покрывает:
  - BLK-1: BUG_NAME_RE/BUG_ID_RE допускает суффикс-slug после NNN
    (BUG-001-search-card-click.md — исторические репорты ekotov-wiki);
  - MIN-3: единая грамматика scope Ф2 / имени репорта (BUG_ID_PATTERN из
    scripts/flow_check.py, enforcer импортирует; fallback синхронен);
  - MAJ-1: kind=docs без paths — только docs_task/chore_task (dev_task —
    PATHS_MISSING; основные кейсы в test_bug_af_recheck_001.py);
  - MAJ-2: --path отвергает '..' и абсолютные пути (fail-closed на границе
    энфорсера); product_paths матчит после канонизации ('backendx/evil' —
    не 'backend');
  - MAJ-3: реестр bypass — naive expires невалидна; несколько действующих
    записей — отказ;
  - MIN-1: bypass-заявка без маркеров (permissive) — bypass_requested_
    unfulfilled в bypass-логе;
  - MIN-2: parse_markers разбирает kind/paths по ВСЕМ текстам;
  - MIN-4: warns approved_review_tasks пробрасываются в диагностику
    (_deps_findings и pr_validate.check_change).
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
sys.path.insert(0, str(FACTORY / "scripts"))

import enforcer  # noqa: E402
import flow_check  # noqa: E402
import flow_transition as ft  # noqa: E402
import pr_validate  # noqa: E402


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
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_BYPASS_REGISTRY", raising=False)
    yield state


def delegate_args(goal: str, context: str | None = None) -> dict:
    a = {"goal": goal}
    if context is not None:
        a["context"] = context
    return a


# ------------------------------------------------- BLK-1 + MIN-3: грамматика

VALID_BUG_IDS = (
    "BUG-001",
    "BUG-AF-RECHECK-001",
    "BUG-201",
    # исторические репорты ekotov-wiki (реальные имена, ls test-model/bugs/):
    "BUG-001-search-card-click",
    "BUG-002-fast-explicit-null-priority-201",
    "BUG-003-dnd-drop-target-lost-todo-inprogress",
    "BUG-016-flaky-bug014-computed-styles",
)
INVALID_BUG_IDS = (
    "bug-001",            # lowercase ядра
    "BUG-12",             # номер не NNN
    "BUG-001-",           # пустой суффикс
    "BUG-001-Search",     # БУКВА в суффиксе (суффикс — только lowercase)
    "BUG-001_x",          # underscore в суффиксе
    "BUG-AF-recheck-001",  # lowercase сегмент комплекса
    "BUG-001.search",     # суффикс без дефис-разделителя
    "BUGX-001",
)


def test_bug_id_grammar_suffix_slug_table():
    """TC-AF-RECHECK-R2-001: BLK-1 — BUG-NNN[-slug], slug только
    lowercase/digits/dot/dash после NNN; имена исторических репортов
    ekotov-wiki валидны."""
    for good in VALID_BUG_IDS:
        assert flow_check.BUG_NAME_RE.match(good), good
    for bad in INVALID_BUG_IDS:
        assert not flow_check.BUG_NAME_RE.match(bad), bad


def test_enforcer_bug_id_re_uses_shared_pattern():
    """TC-AF-RECHECK-R2-002: MIN-3 — enforcer.BUG_ID_RE это ТА ЖЕ
    регекс-строка, что и правило имен репортов (flow_check.BUG_ID_PATTERN);
    поведение идентично на таблице имен."""
    assert enforcer.BUG_ID_RE.pattern == flow_check.BUG_ID_PATTERN
    for good in VALID_BUG_IDS:
        assert enforcer.BUG_ID_RE.match(good), good
    for bad in INVALID_BUG_IDS:
        assert not enforcer.BUG_ID_RE.match(bad), bad
    # Суффикс-имя легально и как scope Флоу 2 (репорт с суффиксом существует).
    enforcer.validate_scope_for_flow(2, "BUG-001-search-card-click")


def test_flow_check_flags_uppercase_suffix_slug(tmp_path):
    """TC-AF-RECHECK-R2-003: BLK-1 негативный интеграционный —
    BUG-001-Search.md (буква в суффиксе) дает FLOW-ERROR «баг-репорт не
    BUG-NNN», exit != 0."""
    bugs = tmp_path / "test-model" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "BUG-001-Search.md").write_text("# r\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(FACTORY / "scripts" / "flow_check.py"),
         str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "BUG-001-Search.md" in proc.stdout
    assert "баг-репорт не BUG-NNN" in proc.stdout


@pytest.mark.skipif(not Path("/home/openclaw/ekotov-wiki").is_dir(),
                    reason="нужен реальный ekotov-wiki")
def test_flow_check_ekotov_wiki_regression_zero():
    """TC-AF-RECHECK-R2-004: BLK-1 приемка — НОЛЬ регресса на реальном
    проекте: 17 исторических репортов с суффиксами больше не FLOW-ERROR,
    exit 0."""
    proc = subprocess.run(
        [sys.executable, str(FACTORY / "scripts" / "flow_check.py"),
         "/home/openclaw/ekotov-wiki"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "flow_check: OK" in proc.stdout
    assert "баг-репорт не BUG-NNN" not in proc.stdout


# ------------------------------------------------------- MAJ-2: границы --path

def test_path_parent_segment_is_marker_error(monkeypatch):
    """TC-AF-RECHECK-R2-005: MAJ-2 — paths с '..'-сегментом —
    FLOW_MARKER_INVALID (fail-closed до prepare, --path не строится)."""
    calls = []

    def _no_run(argv, **kw):
        calls.append(list(argv))
        raise AssertionError("prepare не должен вызываться")

    monkeypatch.setattr(enforcer.subprocess, "run", _no_run)
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "paths=../evil.py\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "m1")
    assert res is not None and res["action"] == "block"
    assert "FLOW_MARKER_INVALID" in res["message"]
    assert "'..'" in res["message"]
    assert calls == []
    with pytest.raises(enforcer.FlowMarkerError):
        enforcer._split_paths("backend/x.py,../y.py")


def test_path_absolute_is_marker_error():
    """TC-AF-RECHECK-R2-006: MAJ-2 — абсолютный --path —
    FLOW_MARKER_INVALID."""
    for bad in ("/etc/passwd", "C:/tmp/x.py"):
        goal = (f"flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
                f"paths={bad}\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "m2")
        assert res is not None and res["action"] == "block", bad
        assert "FLOW_MARKER_INVALID" in res["message"]
        assert "абсолютный" in res["message"]


def test_product_paths_matches_after_canonicalization():
    """TC-AF-RECHECK-R2-007: MAJ-2 — product_paths матчит после canon-нормализации: 'backend/',
    'backend/./x', 'backend/a/../b' — продуктовые; '../backend/x',
    '/abs/backend/x', 'backendx/evil' — НЕТ (последний не префикс 'backend')."""
    action = ft.ActionRequest(
        actor_role="dev", requested_action="dev_task",
        paths=("../backend/x.py", "/abs/backend/x.py", "backendx/evil.py",
               "backend/", "backend/./x.py", "backend/a/../b.py", "docs/a.md"))
    assert ft.product_paths(action) == [
        "backend/", "backend/./x.py", "backend/a/../b.py"]


# ------------------------------------------------------- MAJ-3: реестр bypass

def _registry(tmp_path, entries, monkeypatch) -> None:
    reg = tmp_path / "state" / "reg.json"
    monkeypatch.setenv("FLOW_BYPASS_REGISTRY", str(reg))
    reg.write_text(json.dumps(entries), encoding="utf-8")


def test_bypass_naive_expires_is_invalid(tmp_path, monkeypatch):
    """TC-AF-RECHECK-R2-008: MAJ-3 — expires БЕЗ таймзоны это невалидная
    запись (не «UTC по умолчанию»): обхода нет."""
    _registry(tmp_path, [{"repo": "/tmp/proj", "scope": "BUG-001",
                          "action": "bug_fix", "decision_ref": "DEC-1",
                          "expires": "2099-01-01T00:00:00"}], monkeypatch)
    assert enforcer.find_bypass_decision(
        "/tmp/proj", "BUG-001", "bug_fix") is None


def test_bypass_multiple_live_entries_is_ambiguous(tmp_path, monkeypatch):
    """TC-AF-RECHECK-R2-009: MAJ-3 — НЕСКОЛЬКО действующих неистекших записей
    дают отказ (неоднозначность, fail-closed)."""
    _registry(tmp_path, [
        {"repo": "/tmp/proj", "scope": "BUG-001", "action": "bug_fix",
         "decision_ref": "DEC-1", "expires": "2099-01-01T00:00:00+00:00"},
        {"repo": "/tmp/proj", "scope": "BUG-001", "action": "bug_fix",
         "decision_ref": "DEC-2", "expires": "2099-06-01T00:00:00+00:00"},
    ], monkeypatch)
    assert enforcer.find_bypass_decision(
        "/tmp/proj", "BUG-001", "bug_fix") is None


def test_bypass_single_live_entry_still_grants(tmp_path, monkeypatch):
    """TC-AF-RECHECK-R2-010: MAJ-3 — одна действующая запись (UTC) работает
    как раньше; naive-сосед не действующая и не создает неоднозначности."""
    _registry(tmp_path, [
        {"repo": "/tmp/proj", "scope": "BUG-001", "action": "bug_fix",
         "decision_ref": "DEC-1", "expires": "2099-01-01T00:00:00+00:00"},
        {"repo": "/tmp/proj", "scope": "BUG-001", "action": "bug_fix",
         "decision_ref": "DEC-BAD", "expires": "2099-01-01T00:00:00"},
    ], monkeypatch)
    d = enforcer.find_bypass_decision("/tmp/proj", "BUG-001", "bug_fix")
    assert d is not None and d["decision_ref"] == "DEC-1"


# ------------------------------------------------- MIN-1: аудит bypass-заявки

def test_bypass_request_without_markers_logged_permissive(plugin_env):
    """TC-AF-RECHECK-R2-011: MIN-1 — permissive + bypass-заявка без маркеров
    дает пропуск, но bypass_requested_unfulfilled в bypass-логе (аудит)."""
    res = enforcer.flow_enforce(
        "delegate_task",
        delegate_args("flow: bypass --by customer\nСделай что-нибудь.\n"),
        "b1")
    assert res is None  # permissive-пропуск
    blog = plugin_env / "flow-enforcer-bypass.log"
    assert blog.is_file()
    entries = [json.loads(l) for l in
               blog.read_text("utf-8").splitlines() if l.strip()]
    assert any(e.get("kind") == "bypass_requested_unfulfilled"
               for e in entries), entries


# ------------------------------------------------- MIN-2: kind/paths во всех
# ------------------------------------------------- текстах

def test_parse_markers_kind_paths_from_other_text():
    """TC-AF-RECHECK-R2-012: MIN-2 — kind/paths в context разбираются вместе
    с role/repo/scope из goal (раньше цикл прерывался раньше их поиска)."""
    m = enforcer.parse_markers(delegate_args(
        "flow: flow=1 role=dev repo=/tmp/proj scope=add-widget\n",
        context="kind: docs\npaths: docs/guide.md\n"))
    assert m is not None
    assert m["kind"] == "docs"
    assert m["paths"] == ["docs/guide.md"]


# ------------------------------------------------- MIN-4: warns в диагностику

def _mini_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / "openspec" / "changes" / "add-widget").mkdir(parents=True)
    (repo / "openspec" / "changes" / "add-widget" / "tasks.md").write_text(
        "# Tasks\n\n- [x] 1.1 сделать\n- [x] 1.2 проверить\n",
        encoding="utf-8")
    cr = repo / "code-reviews" / "add-widget"
    cr.mkdir(parents=True)
    (cr / "review-001-1.1.md").write_text(
        "# Review\n\nЗамечаний нет, но строка вердикта потеряна.\n",
        encoding="utf-8")
    return repo


def test_dep_evidence_warns_reach_deps_findings(tmp_path):
    """TC-AF-RECHECK-R2-013: MIN-4 — нечитаемый вердикт последней итерации:
    warn парсера попадает в evidence зависимости и в диагностику отказа
    _deps_findings."""
    repo = _mini_repo(tmp_path)
    ev = ft._dep_evidence(repo, "add-widget", ("1.1", "1.2"))
    assert ev["1.1"]["review_approved"] is False
    assert ev["1.1"]["review_warning"] is not None
    assert "не читается" in ev["1.1"]["review_warning"]
    assert ev["1.2"]["review_warning"] is None  # нет review-файла — без warn
    findings = ft._deps_findings(
        ft.ActionRequest(
            actor_role="dev", requested_action="dev_task",
            task_dependencies=("1.1",), dependency_evidence=ev),
        {"checked": set()})
    assert findings
    assert any("диагностика: " in f.detail and "не читается" in f.detail
               for f in findings), [f.detail for f in findings]


def test_pr_validate_change_change_prints_review_warns(tmp_path, capfd,
                                                       monkeypatch):
    """TC-AF-RECHECK-R2-014: MIN-4 — pr_validate.check_change выводит warns
    парсера вердиктов в диагностику (stderr FLOW-WARNING), не молчаливо."""
    repo = _mini_repo(tmp_path)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    missing = pr_validate.check_change(
        repo, "add-widget", "[add-widget] Merge задачи 1.1 и 1.2")
    assert isinstance(missing, list)
    err = capfd.readouterr().err
    assert "FLOW-WARNING" in err
    assert "не читается" in err
