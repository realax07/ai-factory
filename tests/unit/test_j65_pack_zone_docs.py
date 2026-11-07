# -*- coding: utf-8 -*-
"""J65.1/J64.11: блок «Зона записи» в README каждого роль-пака — из реестра.

До 2026-11-07 примеры зон в README паков писались руками и расходились с
политикой ворот (code-reviewer — test-model/reviews вместо code-reviews/,
devops — docs/ops вместо ops/ и .github/workflows, architect — лишний docs/).
gen_role_docs.py теперь рендерит блок между маркерами roles:pack-zone и
пример `PI_ZONE_WRITE='…'` из agents/roles.json.

Трассировка:
  TC-J65-PZ-001  у каждого пака с политикой есть сгенерированный блок, и он
                 совпадает с политикой (glob) и normalize_zone (префикс)
  TC-J65-PZ-002  пример PI_ZONE_WRITE в README пака — префикс-форма
                 политики с <id> → C123
  TC-J65-PZ-003  паки без политики (debug, auditor) не генерируются
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import gen_role_docs as gen  # noqa: E402
import package_runner as pr  # noqa: E402

ROLES = gen._roles()


def test_pack_zone_blocks_match_policy():
    """TC-J65-PZ-001."""
    targets = gen.pack_targets(ROLES)
    assert {r["pack"] for _, r in targets} >= {"dev", "code-reviewer", "qa-automation"}
    for path, role in targets:
        text = path.read_text(encoding="utf-8")
        start = text.index("<!-- roles:pack-zone:start -->")
        end = text.index("<!-- roles:pack-zone:end -->")
        block = text[start:end]
        glob = re.search(r"манифест \(glob-форма\):\s*(\S+)", block).group(1)
        pref = re.search(r"env PI_ZONE_WRITE \(префикс\):\s*(\S+)", block).group(1)
        assert glob.split(":") == list(role["zones"]), path
        assert set(pref.split(":")) == {pr.normalize_zone(z) for z in role["zones"]}, path


def test_pack_examples_use_policy_prefix():
    """TC-J65-PZ-002."""
    for path, role in gen.pack_targets(ROLES):
        _, prefix = gen.pack_zone_forms(role)
        want = prefix.replace("<id>", gen.EXAMPLE_ID)
        for value in re.findall(r"PI_ZONE_WRITE='([^']*)'",
                                path.read_text(encoding="utf-8")):
            assert value == want, path


def test_packs_without_policy_untouched():
    """TC-J65-PZ-003."""
    packs = {r["pack"] for _, r in gen.pack_targets(ROLES)}
    assert "debug" not in packs and "auditor" not in packs
    for pack in ("debug", "auditor"):
        text = (gen.PACKS / pack / "README.md").read_text(encoding="utf-8")
        assert "roles:pack-zone" not in text
