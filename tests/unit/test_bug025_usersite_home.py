# -*- coding: utf-8 -*-
"""BUG-025: user-site теряется у subprocess-интерпретатора при подмене HOME.

J64.2 подменяет HOME на временный каталог (pytest_configure + isolated_home).
Python вычисляет user-site из HOME, поэтому дочерний `python -m pytest`
(regress-тьеры j51/j52/j54) на машине с pip --user зависимостями (VPS:
~/.local/lib/python3.14/site-packages) падал «No module named pluggy» —
18 фейлов. В CI и на чистой машине user-site не задействован, дефект не
виден.

Фикс (tests/conftest.py): до подмены HOME реальный user base фиксируется в
PYTHONUSERBASE; HOME и HERMES_HOME по-прежнему временные.

Трассировка:
  TC-BUG-025-001  subprocess видит тот же user-site, что и процесс сьюта
  TC-BUG-025-002  изоляция сохранена: HOME subprocess — временный, не реальный
  TC-BUG-025-003  subprocess `python -m pytest --version` запускается (rc 0)
  TC-BUG-025-004  pytest_unconfigure восстанавливает PYTHONUSERBASE
                  (не заданный до сьюта — снимается, заданный — прежний;
                  пустая строка трактуется как «не задано»)
"""
from __future__ import annotations

import importlib.util
import os
import site
import subprocess
import sys
import types
from pathlib import Path

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"  # J66: корневой conftest


def _py(code: str) -> str:
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=os.environ.copy())
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_subprocess_sees_same_user_site():
    """TC-BUG-025-001: user-site дочернего интерпретатора = user-site сьюта
    (вычислен при старте с реальным HOME)."""
    child = _py("import site; print(site.getusersitepackages())")
    assert child == site.getusersitepackages()


def test_home_isolation_kept(request):
    """TC-BUG-025-002: фикс не возвращает реальный HOME в subprocess."""
    real_home = request.config._factory_home[1]
    child_home = _py("from pathlib import Path; print(Path.home())")
    assert child_home == os.environ["HOME"]
    assert child_home != real_home


def test_subprocess_pytest_starts():
    """TC-BUG-025-003: прямой симптом — `python -m pytest` в subprocess
    импортирует свои зависимости. Информативен только там, где pytest стоит
    в user-site (VPS); в CI и venv зеленый и без фикса — дефект там ловит
    TC-BUG-025-001."""
    proc = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                          capture_output=True, text=True, env=os.environ.copy())
    assert proc.returncode == 0, proc.stderr


def _load_conftest():
    spec = importlib.util.spec_from_file_location("_bug025_conftest", CONFTEST)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unconfigure_restores_userbase(monkeypatch, tmp_path):
    """TC-BUG-025-004: после сьюта PYTHONUSERBASE — как до него."""
    mod = _load_conftest()
    monkeypatch.setenv("HOME", str(tmp_path / "real"))

    def cycle(expected_during):
        cfg = types.SimpleNamespace()
        mod.pytest_configure(cfg)
        try:
            assert os.environ["PYTHONUSERBASE"] == expected_during
        finally:  # unconfigure удаляет временный HOME даже при падении assert
            mod.pytest_unconfigure(cfg)

    monkeypatch.delenv("PYTHONUSERBASE", raising=False)
    cycle(site.getuserbase())
    assert "PYTHONUSERBASE" not in os.environ
    assert os.environ["HOME"] == str(tmp_path / "real")

    monkeypatch.setenv("PYTHONUSERBASE", "")  # пустое = не задано
    cycle(site.getuserbase())
    assert os.environ["PYTHONUSERBASE"] == ""

    monkeypatch.setenv("PYTHONUSERBASE", str(tmp_path / "ub"))
    cycle(str(tmp_path / "ub"))
    assert os.environ["PYTHONUSERBASE"] == str(tmp_path / "ub")
