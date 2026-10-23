# -*- coding: utf-8 -*-
"""АУД-4: sha256-сверка копий скриптов проектов vs эталон фабрики (Н22,
scripts/check_mirrors.py).

Инцидент-класс: фикс в фабрике может тихо не доехать до копий в проектах
(осознано в J34, механизма не было).

Трассировка:
  TC-CM-001  все копии совпадают — match, exit 0
  TC-CM-002  копия протухла (контент разошелся) — mismatch, exit 1
  TC-CM-003  копии нет — missing, exit 1
  TC-CM-004  несколько --project: сводный статус = худший
  TC-CM-005  эталона нет (no_reference) — статус error-класса, exit 1
  TC-CM-006  --file: список файлов переопределяется
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_mirrors as cm  # noqa: E402


def make_factory(tmp_path: Path) -> Path:
    f = tmp_path / "factory"
    (f / "scripts").mkdir(parents=True)
    (f / "scripts" / "flow_check.py").write_text("FLOW = 1\n", encoding="utf-8")
    (f / "scripts" / "pr_validate.py").write_text("PV = 1\n", encoding="utf-8")
    (f / "scripts" / "impact_rules.json").write_text("{}\n", encoding="utf-8")
    return f


def make_project(root: Path, factory: Path, name: str,
                 overrides: dict[str, str] | None = None,
                 drop: tuple[str, ...] = ()) -> Path:
    p = root / name
    (p / "scripts").mkdir(parents=True)
    for fname in ("flow_check.py", "pr_validate.py", "impact_rules.json"):
        if fname in drop:
            continue
        content = (overrides or {}).get(
            fname, (factory / "scripts" / fname).read_text(encoding="utf-8"))
        (p / "scripts" / fname).write_text(content, encoding="utf-8")
    return p


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check_mirrors.py"), *args],
        capture_output=True, text=True)


def test_cm_all_match(tmp_path):
    factory = make_factory(tmp_path)
    proj = make_project(tmp_path, factory, "wiki")
    res = cm.check_project(proj, factory, list(cm.DEFAULT_FILES))
    assert res["status"] == "match"
    p = run_cli("--project", str(proj), "--factory", str(factory))
    assert p.returncode == 0
    assert json.loads(p.stdout)["status"] == "match"


def test_cm_stale_copy_mismatch(tmp_path):
    factory = make_factory(tmp_path)
    proj = make_project(tmp_path, factory, "wiki",
                        overrides={"pr_validate.py": "PV = 0  # протухла\n"})
    res = cm.check_project(proj, factory, list(cm.DEFAULT_FILES))
    assert res["status"] == "mismatch"
    entry = next(e for e in res["files"] if e["file"] == "pr_validate.py")
    assert entry["reference_sha256"] != entry["copy_sha256"]
    p = run_cli("--project", str(proj), "--factory", str(factory))
    assert p.returncode == 1


def test_cm_missing_copy(tmp_path):
    factory = make_factory(tmp_path)
    proj = make_project(tmp_path, factory, "wiki",
                        drop=("flow_check.py",))
    res = cm.check_project(proj, factory, list(cm.DEFAULT_FILES))
    assert res["status"] == "missing"
    assert next(e for e in res["files"]
                if e["file"] == "flow_check.py")["status"] == "missing"


def test_cm_multiple_projects_worst(tmp_path):
    factory = make_factory(tmp_path)
    ok = make_project(tmp_path, factory, "wiki")
    stale = make_project(tmp_path, factory, "shop",
                         overrides={"flow_check.py": "FLOW = 9\n"})
    p = run_cli("--project", str(ok), "--project", str(stale),
                "--factory", str(factory))
    assert p.returncode == 1
    data = json.loads(p.stdout)
    assert data["status"] == "mismatch"
    by_path = {r["project"]: r["status"] for r in data["projects"]}
    assert by_path[str(ok)] == "match" and by_path[str(stale)] == "mismatch"


def test_cm_no_reference(tmp_path):
    factory = make_factory(tmp_path)
    proj = tmp_path / "empty-proj"
    proj.mkdir()
    res = cm.check_project(proj, factory, ["nope.json"])
    assert res["status"] == "no_reference"
    p = run_cli("--project", str(proj), "--factory", str(factory),
                "--file", "nope.json")
    assert p.returncode == 1


def test_cm_file_override(tmp_path):
    factory = make_factory(tmp_path)
    proj = make_project(tmp_path, factory, "wiki",
                        overrides={"impact_rules.json": "{\"rules\": []}\n"})
    # протух impact_rules.json, но сверяем только flow_check.py — match
    p = run_cli("--project", str(proj), "--factory", str(factory),
                "--file", "flow_check.py")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert [e["file"] for e in data["projects"][0]["files"]] == ["flow_check.py"]


def test_cm_default_factory_is_repo(tmp_path):
    """Без --factory эталон = репо скрипта (scripts/.. текущей фабрики)."""
    p = run_cli("--project", str(FACTORY), "--file", "impact_rules.json")
    assert p.returncode == 0
    data = json.loads(p.stdout)
    assert data["factory"] == str(FACTORY)
    assert data["projects"][0]["files"][0]["status"] == "match"
