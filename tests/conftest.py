# -*- coding: utf-8 -*-
"""Общие pytest-фикстуры фабрики.

plan_release_fixture (J41, задача A): autouse-фикстура подкладывает план
релиза в fixture-репозитории тестов. Урок P15 (инцидент add-wiki) и решение
Заказчика 2026-10-11: план релиза — обязательный артефакт ворот, ворота
(check_create_change / check_dev_task) теперь DENY без
PLAN-<change>.md (или openspec/changes/<id>/PLAN.md) с объявленным воркфлоу.

Существующие сьюты (test_flow_transition, test_workflow_bypasses, test_flowctl,
…) строят fixture-репозитории через локальные make_repo() и ожидают ALLOW на
«собранном» репо. Чтобы J41-ворота не ломали 140 вызовов make_repo (и чтобы
не переписывать зону чужих сьют), фикстура вписывает PLAN-add-widget.md в
tmp_path ДО коммита репо. Файл печатает маркер в stderr — в журнале прогона
видно, где фикс-план подложен (прозрачность приемки). Тесты, которые проверяют
само J41-правило (test_j41_plan_release.py), отключают фикстуру
(@pytest.mark.no_plan_fixture) и создают планы вручную.

isolated_home (J64.2): autouse — HOME и HERMES_HOME каждого теста во
временном каталоге. Прогон сьюта на машине фабрики не пишет в боевой
~/.hermes (state, логи энфорсера, ~/.hermes/scripts), на чистой машине не
создает его. Проверено прогоном с HOME=<пустой каталог>: каталог остается
пустым.

User-site при подмене HOME (BUG-025): Python вычисляет user-site из HOME,
поэтому дочерний интерпретатор (subprocess `python -m pytest` в regress-
тьерах) с фейковым HOME терял ~/.local/lib/... — на VPS там pytest/pluggy
(pip --user), 18 фейлов j51/j52/j54. До подмены HOME реальный user base
фиксируется в PYTHONUSERBASE: импорты дочерних процессов живут, state
по-прежнему изолирован (HOME и HERMES_HOME — временные).

Сторож дерева (J64.1): сьют не оставляет файлов в репозитории фабрики —
`git status --porcelain` после прогона сравнивается с исходным; новые пути
→ сьют красный с перечнем (прецедент: каталог `prepared: true/` с
симлинками на /home/openclaw/... попал в main, коммит 6d4d365).
"""
from __future__ import annotations

import os
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Эталонный прогон J65.10: tests/fixtures/ — данные проектов (там свои
# test_*.py фиктивного проекта), не тесты фабрики.
collect_ignore_glob = ["fixtures/*"]

PLAN_FIXTURE_NAME = "PLAN-add-widget.md"
# Шапка — как у backlog/J41-*.md (жирный Флоу-декларант обязателен).
PLAN_FIXTURE_TEXT = (
    "# PLAN-add-widget — план релиза change-пакета (fixture)\n"
    "\n"
    "**Флоу: 1** (J41 fixture: план релиза обязателен до старта работ;\n"
    "пишет ПМ, СА лишь детализирует в tasks.md).\n"
    "\n"
    "## Этапы\n\n1. dev\n2. review\n3. merge\n"
)

# Примечание J43.1: план Флоу 2 (test-model/bugs/PLAN.md) и Флоу 4
# (PLAN-chore.md) фикстура НЕ кладет — их расположение делает непустым
# факт test-model.present/bugs (flow_state) и ломает чужие допущения.
# Флоу-специфичные планы пишут сами сьюты-помощники (TestFlow2/TestFlow4
# в test_flow_transition.py) и тесты правил (test_j41_plan_release.py,
# test_j431_flow_aware.py — оба с no_plan_fixture).


@pytest.fixture(autouse=True)
def plan_release_fixture(request, tmp_path):
    """Подкладывает PLAN-add-widget.md в КОРЕНЬ fixture-репозитория
    tmp_path/proj (J41; урок P15).

    Фикстура выполняется ДО тела теста (до make_repo), поэтому каталог
    создается здесь. Часть сьютов (test_flow_state, test_review003_fixes)
    строит свои mini-repo в ПОДКАТАЛОГАХ tmp_path ("a", "b", …) и в корне —
    "proj" через repo.mkdir() без exist_ok: mkdir(exist_ok=True) здесь
    совместим с обоими вариантами (git init и запись PLAN в уже
    существующий каталог легальны). Ворота ищут план относительно
    scope.repo (свои для каждого флоу пути — flow_transition.
    plan_release_paths). Отключение: pytest.mark.no_plan_fixture — для
    тестов самих J41/J43.1-правил.
    """
    if request.node.get_closest_marker("no_plan_fixture"):
        yield
        return
    repo_root = tmp_path / "proj"
    repo_root.mkdir(parents=True, exist_ok=True)
    plan_path = repo_root / PLAN_FIXTURE_NAME
    plan_path.write_text(PLAN_FIXTURE_TEXT, encoding="utf-8")
    print(f"[j41-fixture] PLAN подложен: {plan_path}", file=sys.stderr)
    yield


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    """HOME/HERMES_HOME теста — временный каталог (J64.2)."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(home / ".hermes"))
    yield home


FACTORY_ROOT = Path(__file__).resolve().parent.parent


def _tree_status() -> set[str] | None:
    proc = subprocess.run(
        ["git", "-C", str(FACTORY_ROOT), "status", "--porcelain", "-uall"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return None  # не git-дерево (архив исходников) — сторож молчит
    return {line for line in proc.stdout.splitlines() if line.strip()}


def pytest_configure(config):
    """HOME/HERMES_HOME сессии — временный каталог ДО импорта тестовых
    модулей (J64.2): константы уровня импорта (Path.home() / ".hermes" в
    delegate_watchdog, flow_mode, session_archive …) тоже не указывают на
    боевой ~/.hermes. isolated_home дополнительно разводит тесты между собой.

    PYTHONUSERBASE (BUG-025) — реальный user base, вычисленный ДО подмены
    HOME: subprocess-интерпретаторы видят те же user-site пакеты."""
    home = Path(tempfile.mkdtemp(prefix="af-test-home-"))
    config._factory_home = (home, os.environ.get("HOME"),
                            os.environ.get("HERMES_HOME"),
                            os.environ.get("PYTHONUSERBASE"))
    if not os.environ.get("PYTHONUSERBASE"):  # "" Python считает «не задано»
        os.environ["PYTHONUSERBASE"] = site.getuserbase()
    os.environ["HOME"] = str(home)
    os.environ["HERMES_HOME"] = str(home / ".hermes")


def pytest_unconfigure(config):
    saved = getattr(config, "_factory_home", None)
    if saved is None:
        return
    home, old_home, old_hermes, old_userbase = saved
    for key, old in (("HOME", old_home), ("HERMES_HOME", old_hermes),
                     ("PYTHONUSERBASE", old_userbase)):
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
    shutil.rmtree(home, ignore_errors=True)


def pytest_sessionstart(session):
    session.config._factory_tree_before = _tree_status()


def pytest_sessionfinish(session, exitstatus):
    """Сторож дерева (J64.1): новые пути в репозитории после сьюта — FAIL."""
    before = getattr(session.config, "_factory_tree_before", None)
    after = _tree_status()
    if before is None or after is None:
        return
    leaked = sorted(after - before)
    if leaked:
        print("\nFACTORY-TREE-LEAK: сьют оставил изменения в репозитории "
              "фабрики (тест пишет вне tmp_path):\n  "
              + "\n  ".join(leaked), file=sys.stderr)
        if session.exitstatus == pytest.ExitCode.OK:
            # прочие коды (прерывание, ошибка использования …) не затираем
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
