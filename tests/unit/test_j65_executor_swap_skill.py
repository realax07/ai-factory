# -*- coding: utf-8 -*-
"""Скилл executor-swap и гайд внешнего оркестратора (решение Заказчика
2026-11-15, закрытие J65.10 «реальные исполнители»).

Скилл — единственная инструкция, как подменить модель, исполнителя стадии
или оркестратора. Тест держит его в синхроне с кодом: новый модуль
`scripts/executors/` без строки в скилле, битая ссылка на файл или скилл,
до которого ПМ не дотянется, ссылка на несуществующий связанный скилл —
красный тест.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
SKILL = FACTORY / "skills" / "pm-factory" / "executor-swap" / "SKILL.md"
GUIDE = FACTORY / "docs" / "guides" / "external-orchestrator.md"

sys.path.insert(0, str(FACTORY / "scripts"))
import executors  # noqa: E402


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md без frontmatter"
    head = text.split("\n---\n", 1)[0]
    out = {}
    for line in head.splitlines()[1:]:
        key, sep, val = line.partition(":")
        if sep and not line.startswith(" "):
            out[key.strip()] = val.strip()
    return out


def test_skill_frontmatter():
    meta = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert meta.get("name") == "executor-swap"
    # description — триггер загрузки: и «что», и «когда»
    assert "Загружать" in meta.get("description", "")


def test_skill_reachable_from_pm_and_registry():
    """Скилл попадает в репо, только если на него ссылается роль
    (skills/README.md, «Правила ведения»)."""
    pm = (FACTORY / "agents" / "pm_agent.md").read_text(encoding="utf-8")
    assert "`executor-swap`" in pm
    reg = (FACTORY / "skills" / "README.md").read_text(encoding="utf-8")
    assert "(pm-factory/executor-swap/)" in reg


def test_every_executor_documented():
    text = SKILL.read_text(encoding="utf-8")
    names = executors.names()
    assert names, "реестр исполнителей пуст"
    for name in names:
        assert f"| `{name}` |" in text, (
            f"исполнитель {name} не описан в таблице скилла executor-swap")


def test_referenced_paths_exist():
    paths = set()
    for doc in (SKILL, GUIDE):
        for m in re.findall(r"`((?:scripts|skills|docs|agents|plugins|tests)/[^`\s]+)`",
                            doc.read_text(encoding="utf-8")):
            paths.add(m.rstrip("/"))
    assert paths
    missing = sorted(p for p in paths
                     if "<" not in p and not (FACTORY / p).exists())
    assert not missing, f"битые пути: {missing}"


def test_related_skills_exist():
    """related_skills во frontmatter ведут на скиллы этой библиотеки."""
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"related_skills:\s*\[([^\]]*)\]", text)
    assert m, "нет related_skills"
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    assert names
    have = {p.parent.name for p in (FACTORY / "skills").rglob("SKILL.md")}
    missing = [n for n in names if n not in have]
    assert not missing, f"нет скиллов: {missing}"


def test_skill_and_guide_link_each_other():
    assert "docs/guides/external-orchestrator.md" in SKILL.read_text(encoding="utf-8")
    assert "skills/pm-factory/executor-swap/SKILL.md" in GUIDE.read_text(encoding="utf-8")
