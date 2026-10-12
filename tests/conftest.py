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
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
