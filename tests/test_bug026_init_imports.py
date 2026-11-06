# -*- coding: utf-8 -*-
"""BUG-026: factory_init не копировал flow_ids.py, который импортирует движок.

J65.3 (PR #223) вынес грамматику scope в scripts/flow_ids.py и перевел на
него flow_state, flow_transition и flowctl. factory_init копирует эти
скрипты в проект (FLOW_CONTROL_FILES), а flow_ids в списки копирования не
попал: проект после `factory_init --force` получал ModuleNotFoundError в
копиях движка. Класс дефекта — «копируемый скрипт импортирует фабричный
модуль, которого нет в списке копирования» (прецедент того же класса —
factory_paths, J64.5).

Трассировка:
  TC-BUG-026-001  каждый фабричный модуль, импортируемый копируемым скриптом
                  (включая try/except-импорты), сам входит в списки копирования
  TC-BUG-026-002  все копируемые .py (набор файлов factory_init) импортируются
                  в каталоге без остальной фабрики
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402

COPIED = [p for p in fi.COPY_FILES + fi.FLOW_CONTROL_FILES if p.endswith(".py")]


def _factory_imports(rel: str) -> set[str]:
    tree = ast.parse((FACTORY / rel).read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    local = {p.stem for p in (FACTORY / "scripts").glob("*.py")}
    return mods & local


def test_copied_scripts_bring_their_imports():
    """TC-BUG-026-001"""
    copied = {Path(p).stem for p in COPIED}
    missing = {rel: sorted(_factory_imports(rel) - copied) for rel in COPIED}
    missing = {k: v for k, v in missing.items() if v}
    assert not missing, missing


def test_engine_copies_import_standalone(tmp_path):
    """TC-BUG-026-002"""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for rel in COPIED:
        shutil.copy2(FACTORY / rel, scripts / Path(rel).name)
    for mod in sorted(Path(rel).stem for rel in COPIED):
        proc = subprocess.run(
            [sys.executable, "-I", "-c",
             f"import sys; sys.path.insert(0, {str(scripts)!r}); import {mod}"],
            capture_output=True, text=True, cwd=tmp_path)
        assert proc.returncode == 0, f"{mod}: {proc.stderr[-400:]}"
