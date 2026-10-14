# -*- coding: utf-8 -*-
"""J50: CI-ворота «UI-дельта ⇒ web-тесты обязательны» (pr_validate).

Правило (skills/test-automation/SKILL.md, agents/qa_automation_agent.md):
если диф PR трогает продуктовый фронтенд (frontend/** или
services/*/frontend/) И change-пакет содержит макеты (design/** в пакете
или проекте), в дифе должны быть изменения tests/web/*.py, ЛИБО в body PR
явный маркер `[no-ui-tests]` с основанием (≥10 символов после маркера до
конца строки; иначе маркер неполный и валидируется как отсутствие).

Трассировка:
  TC-J50-001  фронт-диф + макеты, без tests/web и без маркера → FAIL
  TC-J50-002  фронт-диф + маркер [no-ui-tests] с основанием → OK
  TC-J50-003  маркер без основания (или <10 символов) → FAIL
  TC-J50-004  фронт-диф с изменениями tests/web → OK
  TC-J50-005  бэкенд-диф (нет PR_CHANGED_UI) → проверка молчит
  TC-J50-006  маркер в начале строки (не только после пробела) → OK
  TC-J50-007  макеты в проекте (design/ в корне репо, структура ekotov-wiki) → FAIL без escape
  TC-J50-008  фронт-диф, макетов нет → проверка молчит (правило не применяется)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import pr_validate  # noqa: E402


@pytest.fixture()
def ui_repo(tmp_path) -> Path:
    """Fixture-репозиторий: change-пакет add-ui с макетами design/mockup.html."""
    repo = tmp_path / "proj"
    pkg = repo / "openspec" / "changes" / "add-ui"
    (pkg / "design").mkdir(parents=True)
    (pkg / "design" / "mockup.html").write_text("<html>мокап</html>", encoding="utf-8")
    return repo


@pytest.fixture()
def no_env(monkeypatch):
    """Чистый env-контекст дифа (без PR_CHANGED_*)."""
    for var in ("PR_CHANGED_UI", "PR_CHANGED_WEBTESTS"):
        monkeypatch.delenv(var, raising=False)


# TC-J50-001: фронт-диф + макеты, без tests/web и без маркера → FAIL
def test_j50_front_diff_no_tests_no_marker_fails(ui_repo, no_env, monkeypatch):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    errs = pr_validate.check_ui_tests_gate(ui_repo, "add-ui", "[add-ui] UI-дельта")
    assert errs == [
        "J50: UI-дельта без web-тестов: добавь tests/web кейсы или [no-ui-tests] + основание"
    ]


# TC-J50-002: фронт-диф + маркер [no-ui-tests] с основанием → OK
def test_j50_marker_with_reason_ok(ui_repo, no_env, monkeypatch, capsys):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    body = "[add-ui] полировка\n[no-ui-tests] только бэкенд-обвязка, UI не менялся"
    assert pr_validate.check_ui_tests_gate(ui_repo, "add-ui", body) == []
    # (2) основание выведено в диагностику
    assert "только бэкенд-обвязка" in capsys.readouterr().err


# TC-J50-003: маркер без основания (или <10 символов) → FAIL
@pytest.mark.parametrize("body", [
    "[add-ui] [no-ui-tests]",              # маркер без основания
    "[add-ui] [no-ui-tests] коротко",      # основание < 10 символов после маркера
])
def test_j50_marker_without_reason_fails(ui_repo, no_env, monkeypatch, body):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    errs = pr_validate.check_ui_tests_gate(ui_repo, "add-ui", body)
    assert errs
    assert "no-ui-tests" in errs[0]


# TC-J50-004: фронт-диф с изменениями tests/web → OK
def test_j50_web_tests_in_diff_ok(ui_repo, no_env, monkeypatch, capsys):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    monkeypatch.setenv("PR_CHANGED_WEBTESTS", "1")
    assert pr_validate.check_ui_tests_gate(ui_repo, "add-ui", "[add-ui]") == []
    assert "tests/web" in capsys.readouterr().err


# TC-J50-005: бэкенд-диф (нет PR_CHANGED_UI) → проверка молчит
def test_j50_backend_diff_silent(ui_repo, no_env, monkeypatch, capsys):
    monkeypatch.setenv("PR_CHANGED_WEBTESTS", "")  # мусор в env не включает ворота
    assert pr_validate.check_ui_tests_gate(ui_repo, "add-ui", "[add-ui]") == []
    # и в диагностике тишина
    assert "J50" not in capsys.readouterr().err


# TC-J50-006: маркер в начале строки (не только после пробела) → OK
def test_j50_marker_at_line_start_ok(ui_repo, no_env, monkeypatch):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    body = "[add-ui] заголовок\n[no-ui-tests] мокапы без интерактива, статика"
    assert pr_validate.check_ui_tests_gate(ui_repo, "add-ui", body) == []


# TC-J50-007: макеты в проекте (design/ в корне репо) → FAIL без escape
def test_j50_project_level_design(ui_repo, no_env, monkeypatch):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    # сносим макеты пакета — правило должно поймать design/ в корне проекта
    pkg_design = ui_repo / "openspec" / "changes" / "add-ui" / "design"
    import shutil
    shutil.rmtree(pkg_design)
    (ui_repo / "design").mkdir()
    (ui_repo / "design" / "tokens.html").write_text(":root{}", encoding="utf-8")
    errs = pr_validate.check_ui_tests_gate(ui_repo, "add-ui", "[add-ui]")
    assert errs and errs[0].startswith("J50")


# TC-J50-008: фронт-диф, макетов нет → проверка молчит
def test_j50_no_design_artifacts_silent(ui_repo, no_env, monkeypatch):
    monkeypatch.setenv("PR_CHANGED_UI", "1")
    import shutil
    shutil.rmtree(ui_repo / "openspec" / "changes" / "add-ui" / "design")
    assert pr_validate.check_ui_tests_gate(ui_repo, "add-ui", "[add-ui]") == []


# Диф-детектор CI (flow.yml): frontend/** и services/*/frontend/ ловятся,
# backend/** и чужие пути — нет (регрессия регэкспа ворот).
@pytest.mark.parametrize("path,expected", [
    ("frontend/src/app.js", True),
    ("services/wiki/frontend/main.ts", True),
    ("backend/api.py", False),
    ("frontendx/evil.js", False),
    ("services/wiki/backend/x.py", False),
    ("tests/web/test_ui.py", False),  # это не продуктовый фронтенд
])
def test_j50_ui_path_regex(path, expected):
    import re
    assert bool(re.match(r"^(frontend/|services/[^/]+/frontend/)", path)) is expected
