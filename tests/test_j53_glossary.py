# -*- coding: utf-8 -*-
"""Тесты скелета глоссария проекта (J53): factory_init создает docs/glossary.md.

Решение Заказчика (backlog/J53-*.md): глоссарий — процесс, НЕ ворота.
Детерминированность не нужна: никаких flow_check-ERROR, машинных форматов
и валидации — фабрика кладет только скелет со свободным форматом записей.

Кейсы:
  (а) factory_init создает docs/glossary.md с 5 секциями и правилом ведения;
  (б) повторный запуск без --force НЕ перезаписывает (термины проекта);
  (в) --force пересоздает скелет;
  (г) e2e: полный прогон factory_init на пустом git-репо создает глоссарий.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init  # noqa: E402

SECTIONS = ["Сервисы", "Процессы", "Сущности данных",
            "Элементы фронта", "Статусы"]


def make_repo(tmp_path: Path) -> Path:
    # tmp_path/proj уже создан autouse-фикстурой conftest (J41, PLAN подложен
    # в корень — factory_init его не трогает).
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def test_a_init_creates_glossary_with_5_sections(tmp_path, capsys):
    """TC-J53-001: factory_init создает глоссарий с 5 секциями."""
    repo = make_repo(tmp_path)
    status = factory_init.install_glossary(repo)
    assert status == "created"
    g = repo / "docs" / "glossary.md"
    assert g.is_file()
    text = g.read_text("utf-8")
    assert text.startswith("# Глоссарий проекта")
    for s in SECTIONS:
        assert f"## {s}" in text
    # правило ведения — свободная форма, без машинных ворот
    assert "запиши одной строкой" in text
    assert "своими словами" in text
    assert "создан" in capsys.readouterr().out


def test_b_rerun_keeps_project_glossary(tmp_path):
    """TC-J53-002: повторный запуск без --force не перезаписывает."""
    repo = make_repo(tmp_path)
    factory_init.install_glossary(repo)
    g = repo / "docs" / "glossary.md"
    # проект успел накопить термины
    project_terms = g.read_text("utf-8") + "\nvideo — сервис конвертации видео\n"
    g.write_text(project_terms, "utf-8")

    assert factory_init.install_glossary(repo) == "kept"
    assert g.read_text("utf-8") == project_terms  # термины не тронуты


def test_c_force_recreates_skeleton(tmp_path):
    """TC-J53-003: --force пересоздает скелет."""
    repo = make_repo(tmp_path)
    factory_init.install_glossary(repo)
    g = repo / "docs" / "glossary.md"
    g.write_text("свои правки проекта\n", "utf-8")

    assert factory_init.install_glossary(repo, force=True) == "recreated"
    text = g.read_text("utf-8")
    assert "свои правки проекта" not in text
    assert text == factory_init.GLOSSARY_TEMPLATE


def test_d_e2e_factory_init_creates_glossary(tmp_path, monkeypatch):
    """TC-J53-004: полный factory_init создает глоссарий (идемпотентно)."""
    repo = make_repo(tmp_path)
    monkeypatch.setattr("sys.argv", [
        "factory_init.py", "--target", str(repo),
        "--name", "J53 Fixture", "--skip-plugin",
    ])
    factory_init.main()  # flow_check/openspec могут дать WARNING — не ворота J53
    g = repo / "docs" / "glossary.md"
    assert g.is_file()
    first = g.read_text("utf-8")

    # повторный полный прогон — глоссарий не тронут
    monkeypatch.setattr("sys.argv", [
        "factory_init.py", "--target", str(repo),
        "--name", "J53 Fixture", "--skip-plugin",
    ])
    factory_init.main()
    assert g.read_text("utf-8") == first
