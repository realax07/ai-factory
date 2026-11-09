# -*- coding: utf-8 -*-
"""J64.11 (остаток): зона записи в промптах роль-паков ⊆ политики реестра.

Промпты паков (`role-agents.md`, строка `zone (write): …` и раздел «Зоны»)
писались руками и разошлись с agents/roles.json: code-reviewer писал ревью в
test-model/reviews/ (политика — code-reviews/<id>/), architect — в docs/**,
devops — в docs/ops/**; агент, следуя промпту, получал OUT_OF_ZONE на своем
же артефакте. Проверка — на семантике zone-guard: префикс каждой зоны
промпта (normalize_zone раннера) лежит внутри префикса какой-либо зоны
политики. Промпт может быть уже политики, но не шире.

Трассировка:
  TC-J65-PRZ-001  у каждого пака с политикой зон есть строка `zone (write):`,
                  и каждая ее зона внутри политики роли
  TC-J65-PRZ-002  ключевые артефакты ролей лежат в зоне политики: review
                  code-reviewer — code-reviews/<id>/, impact-карта sa —
                  openspec/changes/<id>/impact.md (J58)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import package_runner as pr  # noqa: E402
import role_zone_policy as rzp  # noqa: E402

PACKS = FACTORY / "skills" / "pm-factory" / "pi" / "role-packs"
ROLES = [r for r in json.loads((FACTORY / "agents" / "roles.json")
                               .read_text(encoding="utf-8"))["roles"]
         if r.get("pack") and r.get("zones")]
CID = "c123-demo"
_TOKEN = re.compile(r"(?<![\w(])([\w.\-]+(?:/[\w.\-<>*{},]+)+/?\**|[\w\-]+\.(?:md|ini|py))")


def _expand(token: str) -> list[str]:
    """`dir/{a,b}.md` → [dir/a.md, dir/b.md]; плейсхолдер → id."""
    token = token.replace("<change-id>", CID).replace("<id>", CID)
    m = re.search(r"\{([^}]*)\}", token)
    if not m:
        return [token]
    return [token[:m.start()] + part + token[m.end():] for part in m.group(1).split(",")]


def _inside(prefix: str, policy: list[str]) -> bool:
    return any(prefix == p or prefix.startswith(p + "/") for p in policy)


def prompt_zones(pack: str) -> list[str]:
    text = (PACKS / pack / "role-agents.md").read_text(encoding="utf-8")
    m = re.search(r"^zone \(write\):\s*(.+)$", text, re.M)
    assert m, f"{pack}: нет строки `zone (write):`"
    line = re.sub(r"\([^)]*\)", "", m.group(1))
    return [z for t in _TOKEN.findall(line) for z in _expand(t)]


def test_prompt_zones_inside_policy():
    """TC-J65-PRZ-001."""
    checked = 0
    for role in ROLES:
        policy = [pr.normalize_zone(z.replace(rzp.CHANGE_ID, CID))
                  for z in role["zones"]]
        zones = prompt_zones(role["pack"])
        assert zones, role["pack"]
        for z in zones:
            assert _inside(pr.normalize_zone(z), policy), (
                f"{role['pack']}: зона промпта {z} шире политики {role['zones']}")
        checked += 1
    assert checked >= 12


def test_key_artifacts_in_policy():
    """TC-J65-PRZ-002."""
    def ok(role, path):
        return rzp.narrow_zones(role, [path])["violations"] == []
    assert ok("code_reviewer", f"code-reviews/{CID}/review-1.1-001.md")
    assert not ok("code_reviewer", f"test-model/reviews/{CID}/review-001.md")
    assert ok("sa", f"openspec/changes/{CID}/impact.md")
    assert ok("architect", f"test-model/reviews/{CID}/review-001-architecture.md")
    assert not ok("architect", "docs/notes.md")
    assert ok("devops", ".github/workflows/flow.yml")
