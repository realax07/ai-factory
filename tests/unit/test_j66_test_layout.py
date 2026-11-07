# -*- coding: utf-8 -*-
"""J66: раскладка автотестов tests/unit · api · web · integration.

Спека qa-pipeline («Раскладка автотестов», «Проверка раскладки автотестов»,
«Трассировка», «Стек»); решения Заказчика 2026-11-07 — PLAN-test-zones.md.

Трассировка:
  TC-J66-001  режим раскладки: файла нет — warn; strict/warn читаются;
              битый JSON и неизвестный режим — проблема (FLOW-ERROR)
  TC-J66-002  тест в корне tests/: warn — FLOW-WARNING без отказа,
              strict — FLOW-ERROR (rc 1)
  TC-J66-003  стек уровня: requests/playwright в unit и integration,
              playwright в api — нарушение; playwright в web — норма
  TC-J66-004  трассировка: unit без TC-ID проходит, api без TC-ID — ошибка
  TC-J66-005  битый test-layout.json — FLOW-ERROR даже без тестов вне раскладки
  TC-J66-006  factory_init: strict для проекта без тестов вне раскладки,
              warn — при легаси-тестах; существующий файл не трогается;
              каталоги раскладки — паритет с flow_check
  TC-J66-007  зоны реестра: dev — tests/unit/** (без tests/**, e2e/**),
              qa_automation — api/web/integration, не unit
  TC-J66-008  test-layout.json — защищенный путь (pm_bounds_check,
              flow_transition)
  TC-J66-009  фабрика сама по раскладке: strict, тестов вне tests/unit/ нет
  TC-J66-010  сторож дерева J64.1 активен при `pytest tests/` (корневой
              conftest — sessionstart вызван; регресс review-001 #1)
  TC-J66-011  разбор импортов через ast: `import os, requests`, `as`,
              `from … import`, вложенные каталоги, importorskip/importlib;
              текст в строках — не импорт
  TC-J66-012  только unit-тесты без кейс-базы — не нарушение контракта 6
  TC-J66-013  зоны по поведению narrow_zones: dev ↛ tests/api, qa ↛ tests/unit
  TC-J66-014  коммит с test-layout.json без [pipeline] — нарушение J3
  TC-J66-015  Флоу 2–5: этап qa_automation (роль qa_automation) сразу после
              первого этапа флоу, его вход — вход первого этапа; enforcer —
              тот же порядок
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402
import flow_check as fc  # noqa: E402
import flow_transition as ft  # noqa: E402
import pm_bounds_check as pbc  # noqa: E402
import role_zone_policy as rzp  # noqa: E402


def make_repo(tmp_path: Path, files: dict[str, str], mode: str | None = None,
              raw_layout: str | None = None) -> Path:
    repo = tmp_path / "proj"
    # as-is база кейсов: автотесты без нее — ошибка контракта 6 (не J66).
    reg = repo / "test-model" / "regression" / "core"
    reg.mkdir(parents=True)
    (reg / "TC-CORE-001.md").write_text("# TC-CORE-001: x\n", encoding="utf-8")
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    layout = repo / fc.TEST_LAYOUT_REL
    if raw_layout is not None:
        layout.write_text(raw_layout, encoding="utf-8")
    elif mode is not None:
        layout.write_text(json.dumps({"schema": "test-layout/1", "mode": mode}),
                          encoding="utf-8")
    return repo


TC_TEST = '"""TC-CORE-001."""\n\n\ndef test_x():\n    assert True\n'
NO_TC_TEST = '"""Unit без кейса."""\n\n\ndef test_x():\n    assert True\n'


def run_check(repo: Path, capsys) -> tuple[int, str]:
    rc = fc.check(repo)
    return rc, capsys.readouterr().out


class TestLayoutMode:
    def test_absent_file_is_warn(self, tmp_path):
        """TC-J66-001: файла нет — warn без проблемы."""
        repo = make_repo(tmp_path, {})
        assert fc.layout_mode_of(repo) == ("warn", None)

    @pytest.mark.parametrize("mode", ["warn", "strict"])
    def test_valid_modes(self, tmp_path, mode):
        """TC-J66-001: явные режимы читаются как есть."""
        repo = make_repo(tmp_path, {}, mode=mode)
        assert fc.layout_mode_of(repo) == (mode, None)

    @pytest.mark.parametrize("raw", ["{not json", '{"mode": "off"}', "[]"])
    def test_broken_or_unknown_is_problem(self, tmp_path, raw):
        """TC-J66-001: битый файл/неизвестный режим — не молчаливый дефолт."""
        repo = make_repo(tmp_path, {}, raw_layout=raw)
        mode, problem = fc.layout_mode_of(repo)
        assert mode == "strict" and problem and fc.TEST_LAYOUT_REL in problem


class TestRootTest:
    def test_warn_mode_warns_without_failing(self, tmp_path, capsys):
        """TC-J66-002: warn — FLOW-WARNING, ворота зеленые."""
        repo = make_repo(tmp_path, {"tests/test_root.py": TC_TEST})
        rc, out = run_check(repo, capsys)
        assert rc == 0
        assert "FLOW-WARNING: tests/test_root.py: тест вне раскладки" in out

    def test_strict_mode_fails(self, tmp_path, capsys):
        """TC-J66-002: strict — FLOW-ERROR, rc 1."""
        repo = make_repo(tmp_path, {"tests/test_root.py": TC_TEST}, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 1
        assert "FLOW-ERROR: tests/test_root.py: тест вне раскладки" in out

    def test_unknown_top_dir_is_outside(self, tmp_path, capsys):
        """TC-J66-002: каталог вне списка (tests/e2e/) — тоже вне раскладки."""
        repo = make_repo(tmp_path, {"tests/e2e/test_s.py": TC_TEST}, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 1 and "tests/e2e/test_s.py: тест вне раскладки" in out

    def test_layout_dirs_pass_strict(self, tmp_path, capsys):
        """TC-J66-002: все каталоги раскладки, включая tests/web/e2e/, — норма."""
        files = {f"tests/{d}/test_{d}.py": TC_TEST for d in fc.TEST_LAYOUT_DIRS}
        files["tests/web/e2e/test_stand.py"] = TC_TEST
        repo = make_repo(tmp_path, files, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 0, out
        assert "J66" not in out


class TestStack:
    @pytest.mark.parametrize("level,line", [
        ("unit", "import requests"),
        ("unit", "from playwright.sync_api import Page"),
        ("integration", "import requests"),
        ("integration", "from playwright.sync_api import expect"),
        ("api", "from playwright.sync_api import Page"),
    ])
    def test_forbidden_import(self, tmp_path, capsys, level, line):
        """TC-J66-003: запрещенный импорт уровня — нарушение (strict → rc 1)."""
        mod = line.split()[1].split(".")[0]
        repo = make_repo(tmp_path, {f"tests/{level}/test_s.py": line + "\n" + TC_TEST},
                         mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 1
        assert f"импорт {mod} в tests/{level}/" in out

    @pytest.mark.parametrize("level,line", [
        ("web", "from playwright.sync_api import Page"),
        ("api", "import requests"),
        ("unit", "import requests_mock_helper"),   # имя-префикс — не requests
    ])
    def test_allowed_import(self, tmp_path, capsys, level, line):
        """TC-J66-003: стек своего уровня (и похожие имена) — норма."""
        repo = make_repo(tmp_path, {f"tests/{level}/test_s.py": line + "\n" + TC_TEST},
                         mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 0, out


class TestTraceability:
    def test_unit_without_tc_passes(self, tmp_path, capsys):
        """TC-J66-004: unit-тест dev без TC-ID — не дефект трассировки."""
        repo = make_repo(tmp_path, {"tests/unit/test_u.py": NO_TC_TEST}, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 0, out

    def test_api_without_tc_fails(self, tmp_path, capsys):
        """TC-J66-004: приемочный api-тест без TC-ID — дефект (rule 6)."""
        repo = make_repo(tmp_path, {"tests/api/test_a.py": NO_TC_TEST}, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 1
        assert "tests/api/test_a.py: тесты без TC-трассировки" in out


def test_broken_layout_file_fails(tmp_path, capsys):
    """TC-J66-005: битый файл режима — FLOW-ERROR при чистой раскладке."""
    repo = make_repo(tmp_path, {"tests/unit/test_u.py": NO_TC_TEST},
                     raw_layout="{broken")
    rc, out = run_check(repo, capsys)
    assert rc == 1
    assert f"FLOW-ERROR: {fc.TEST_LAYOUT_REL} не читается" in out


class TestFactoryInit:
    def test_single_implementation(self):
        """TC-J66-006: factory_init использует разбор flow_check (одна
        реализация раскладки и стека)."""
        assert fi.TEST_LAYOUT_REL == fc.TEST_LAYOUT_REL
        assert fi._fc is fc

    def test_stack_violation_keeps_warn(self, tmp_path):
        """TC-J66-006: тест на месте, но с запрещенным импортом — warn."""
        (tmp_path / "tests" / "unit").mkdir(parents=True)
        (tmp_path / "tests" / "unit" / "test_n.py").write_text(
            "import requests\n", encoding="utf-8")
        fi.install_test_layout(tmp_path)
        data = json.loads((tmp_path / fi.TEST_LAYOUT_REL).read_text(encoding="utf-8"))
        assert data["mode"] == "warn"

    def test_new_project_strict(self, tmp_path):
        """TC-J66-006: тестов вне раскладки нет — strict."""
        (tmp_path / "tests" / "unit").mkdir(parents=True)
        (tmp_path / "tests" / "unit" / "test_smoke.py").write_text("", encoding="utf-8")
        fi.install_test_layout(tmp_path)
        data = json.loads((tmp_path / fi.TEST_LAYOUT_REL).read_text(encoding="utf-8"))
        assert data["mode"] == "strict"

    def test_legacy_project_warn(self, tmp_path):
        """TC-J66-006: легаси-тесты в корне tests/ — warn."""
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_old.py").write_text("", encoding="utf-8")
        found = fi.misplaced_tests(tmp_path)
        assert len(found) == 1 and found[0].startswith("tests/test_old.py: тест вне раскладки")
        fi.install_test_layout(tmp_path)
        data = json.loads((tmp_path / fi.TEST_LAYOUT_REL).read_text(encoding="utf-8"))
        assert data["mode"] == "warn"

    def test_existing_file_untouched(self, tmp_path):
        """TC-J66-006: существующий файл не перезаписывается (и при --force)."""
        dst = tmp_path / fi.TEST_LAYOUT_REL
        dst.parent.mkdir(parents=True)
        dst.write_text('{"mode": "warn"}', encoding="utf-8")
        fi.install_test_layout(tmp_path)
        assert dst.read_text(encoding="utf-8") == '{"mode": "warn"}'


def test_role_zones():
    """TC-J66-007: dev — только tests/unit, qa_automation — приемочные уровни."""
    roles = {r["id"]: r for r in json.loads(
        (FACTORY / "agents" / "roles.json").read_text(encoding="utf-8"))["roles"]}
    dev = roles["dev"]["zones"]
    assert "tests/unit/**" in dev
    assert "tests/**" not in dev and "e2e/**" not in dev
    assert not any(z.startswith(("tests/api", "tests/web", "tests/integration"))
                   for z in dev)
    qa = roles["qa_automation"]["zones"]
    for z in ("tests/api/**", "tests/web/**", "tests/integration/**"):
        assert z in qa
    assert "tests/**" not in qa
    assert not any(z.startswith("tests/unit") for z in qa)


def test_layout_file_protected():
    """TC-J66-008: смягчение strict → warn — только через защищенный путь."""
    assert fc.TEST_LAYOUT_REL in pbc.PROTECTED_PATHS
    assert fc.TEST_LAYOUT_REL in ft.PROTECTED_PATHS


def test_factory_follows_layout():
    """TC-J66-009: фабрика — strict, все ее тесты в tests/unit/."""
    assert fc.layout_mode_of(FACTORY) == ("strict", None)
    files = list((FACTORY / "tests").rglob("test_*.py"))
    assert files and fc.layout_findings(FACTORY, files) == []


def test_tree_guard_active(request):
    """TC-J66-010: хук sessionstart корневого conftest отработал — сторож
    FACTORY-TREE-LEAK видит снимок дерева при любом запуске сьюта."""
    assert (FACTORY / "tests" / "conftest.py").is_file()
    assert not (FACTORY / "tests" / "unit" / "conftest.py").exists()
    assert hasattr(request.config, "_factory_tree_before")


class TestImportParsing:
    @pytest.mark.parametrize("src", [
        "import os, requests",
        "import requests as r",
        "from requests.adapters import HTTPAdapter",
        "def f():\n    import requests\n",
        "import pytest\nrequests = pytest.importorskip('requests')",
        "import importlib\nimportlib.import_module('requests.sessions')",
    ])
    def test_detected(self, tmp_path, capsys, src):
        """TC-J66-011: формы импорта requests в unit — нарушение."""
        repo = make_repo(tmp_path, {"tests/unit/deep/er/test_s.py": src + "\n" + TC_TEST},
                         mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 1 and "импорт requests в tests/unit/" in out

    def test_text_in_string_is_not_import(self, tmp_path, capsys):
        """TC-J66-011: строка «import requests» в docstring — не импорт."""
        src = '"""Пример:\nimport requests\n"""\n' + TC_TEST
        repo = make_repo(tmp_path, {"tests/unit/test_s.py": src}, mode="strict")
        rc, out = run_check(repo, capsys)
        assert rc == 0, out


def test_unit_only_needs_no_case_base(tmp_path, capsys):
    """TC-J66-012: проект только с unit-тестами и без кейс-базы — норма."""
    repo = tmp_path / "proj"
    (repo / "tests" / "unit").mkdir(parents=True)
    (repo / "tests" / "unit" / "test_u.py").write_text(NO_TC_TEST, encoding="utf-8")
    rc, out = run_check(repo, capsys)
    assert rc == 0, out
    (repo / "tests" / "api").mkdir()
    (repo / "tests" / "api" / "test_a.py").write_text(TC_TEST, encoding="utf-8")
    rc, out = run_check(repo, capsys)
    assert rc == 1 and "контракт 6" in out


def test_narrow_zones_behaviour():
    """TC-J66-013: зона роли по поведению политики, не по строкам реестра."""
    def ok(role, path):
        return rzp.narrow_zones(role, [path])["zones"] == [path]
    assert ok("dev", "tests/unit/test_x.py")
    assert ok("dev", "tests/unit/sub/conftest.py")
    for p in ("tests/api/test_x.py", "tests/web/e2e/test_s.py",
              "tests/integration/test_x.py", "tests/test_root.py",
              "e2e/test_stand.py"):
        assert not ok("dev", p), p
    for p in ("tests/api/test_x.py", "tests/web/e2e/test_s.py",
              "tests/integration/test_x.py", "tests/conftest.py",
              "tests/README.md"):
        assert ok("qa_automation", p), p
    for p in ("tests/unit/test_x.py", "tests/test_root.py"):
        assert not ok("qa_automation", p), p


def test_layout_change_needs_pipeline_marker(tmp_path):
    """TC-J66-014: правка test-layout.json без [pipeline] — нарушение J3."""
    repo = tmp_path / "r"
    repo.mkdir()
    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    f = repo / fc.TEST_LAYOUT_REL
    f.parent.mkdir(parents=True)
    f.write_text('{"mode": "warn"}', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "[chore] смягчить раскладку")
    assert pbc.check_commit(repo, "HEAD")
    f.write_text('{"mode": "strict"}', encoding="utf-8")
    git("commit", "-qam", "[pipeline] J66: раскладка strict")
    assert pbc.check_commit(repo, "HEAD") == []


@pytest.mark.parametrize("flow,first", [(2, "bug_fix"), (3, "emergency_stabilize"),
                                        (4, "chore_task"), (5, "express_task")])
def test_qa_automation_stage_in_maintenance_flows(flow, first):
    """TC-J66-015: регрессионный/адаптированный приемочный тест во Флоу 2–5 —
    легальный этап qa_automation (dev пишет только tests/unit)."""
    sys.path.insert(0, str(FACTORY / "plugins" / "flow-enforcer"))
    import enforcer  # noqa: E402
    stages = ft.STAGE_TABLE[flow]
    actions = [s.action for s in stages]
    assert actions[0] == first and actions[1] == "qa_automation"
    qa, head = stages[1], stages[0]
    assert qa.roles == ("qa_automation",)
    assert qa.check is head.check
    assert enforcer.SEQUENCE_PREREQS[flow]["qa_automation"] == frozenset({first})
