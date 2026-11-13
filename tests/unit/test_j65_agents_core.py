# -*- coding: utf-8 -*-
"""J64.15 + J65.11: AGENTS.md — нормативное ядро для ПМ на Hermes (glm-5.3-flash).

Решения Заказчика 2026-11-13: карта «правило ↔ проверка» — отдельным файлом
(docs/rules-enforcement.md), операционные правила ПМ сжаты и оставлены,
камни стенда вынесены (docs/project-pitfalls.md), предел — 80 строк.

Трассировка:
  TC-J65-AGC-001  AGENTS.md ≤ 80 строк; разделы «Правила», «Оркестрация»,
                  «Эскалация»; правила пронумерованы подряд с 1
  TC-J65-AGC-002  номера docs/rules-enforcement.md = номера правил AGENTS.md
  TC-J65-AGC-003  ссылки «AGENTS.md п.N» в коде и доках ведут на
                  существующее правило
  TC-J65-AGC-004  прежний текст сохранен в archive/agents-md/ (история не
                  теряется)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
AGENTS = FACTORY / "AGENTS.md"
MAP = FACTORY / "docs" / "rules-enforcement.md"


def rule_numbers() -> list[int]:
    text = AGENTS.read_text(encoding="utf-8")
    body = text.split("## Правила", 1)[1].split("\n## ", 1)[0]
    return [int(m) for m in re.findall(r"^(\d+)\. ", body, re.M)]


def test_core_size_and_structure():
    """TC-J65-AGC-001."""
    text = AGENTS.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 80
    for head in ("## Правила", "## Оркестрация", "## Эскалация"):
        assert head in text
    nums = rule_numbers()
    assert nums == list(range(1, len(nums) + 1)) and len(nums) >= 12


def test_enforcement_map_matches_rules():
    """TC-J65-AGC-002."""
    table = re.findall(r"^\| (\d+) \|", MAP.read_text(encoding="utf-8"), re.M)
    assert [int(n) for n in table] == rule_numbers()


def test_rule_references_resolve():
    """TC-J65-AGC-003: ссылки в обоих порядках («AGENTS.md п.N», «правило N
    AGENTS.md»); смысл правил, на которые ссылается код: п.7 — история, п.10
    — параллель/зоны, п.11 — worktree, п.4 — push."""
    out = subprocess.run(["git", "-C", str(FACTORY), "grep", "-hoE",
                          r"AGENTS\.md (п\. ?|правило )[0-9]+|(п\. ?|правило )[0-9]+ AGENTS\.md",
                          "--", "scripts", "plugins", "docs", "agents", "contracts",
                          "templates", "skills"],
                         capture_output=True, text=True).stdout
    refs = {int(re.search(r"(\d+)", r.replace("AGENTS", "")).group(1))
            for r in out.splitlines()}
    assert refs and refs <= set(rule_numbers()), sorted(refs - set(rule_numbers()))
    body = AGENTS.read_text(encoding="utf-8").split("## Правила", 1)[1]
    rules = dict(re.findall(r"^(\d+)\. (.+)$", body, re.M))
    for num, word in (("4", "Push"), ("7", "История"), ("10", "active_sessions"),
                      ("11", "worktree"), ("17", "раннером"), ("21", "Внешний агент")):
        assert word in rules[num], (num, word)


def test_previous_text_archived():
    """TC-J65-AGC-004."""
    old = FACTORY / "archive" / "agents-md" / "AGENTS-2026-11-13.md"
    assert old.is_file() and "## Rules" in old.read_text(encoding="utf-8")
