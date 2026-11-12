# -*- coding: utf-8 -*-
"""session_check.glob_matches: посегментная семантика `**` (кандидат J65.10).

Прежняя реализация сравнивала префикс перед `**` буквально: зона политики
`openspec/changes/<id>/specs/**` (`<id>` → `*`) не матчила
`openspec/changes/x/specs/a/spec.md` — СА не мог запросить конкретный
spec.md (ZONE_OUTSIDE_POLICY; ревью J65.10 review-002), `*/**` матчил ровно
два сегмента, а `a/**/*` — сам каталог `a`.

Трассировка:
  TC-J65-GLB-001  перебор: glob_matches совпадает с оракулом семантики зон
                  (`*` — один сегмент, `**` — любое число, включая ноль;
                  паттерн без glob — каталог со вложенными) на всех парах
                  паттерн × путь из алфавита
  TC-J65-GLB-002  живой сценарий: СА запрашивает конкретный spec.md внутри
                  specs/ — зона в политике; чужой пакет — нет
  TC-J65-GLB-003  прежние контракты ТЗ 04 сохранены: `src/*` не углубляется,
                  `src/**` включает сам префикс, литерал — зона-каталог,
                  пустой путь/паттерн — нет совпадения
"""
from __future__ import annotations

import fnmatch
import itertools
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import role_zone_policy as rzp  # noqa: E402
import session_check as sc  # noqa: E402


def oracle(pat: str, path: str) -> bool:
    ps, us = pat.split("/"), path.split("/")
    if not any(ch in pat for ch in "*?["):
        return path == pat or path.startswith(pat + "/")

    def m(i: int, j: int) -> bool:
        if i == len(ps):
            return j == len(us)
        if ps[i] == "**":
            return any(m(i + 1, k) for k in range(j, len(us) + 1))
        return j < len(us) and fnmatch.fnmatchcase(us[j], ps[i]) and m(i + 1, j + 1)
    return m(0, 0)


def test_glob_matches_equals_oracle():
    """TC-J65-GLB-001."""
    segs = ["a", "x1", "*", "x*", "?1", "[ab]", "**", "*.md"]
    psegs = ["a", "b", "x1", "y1", "r.md"]
    pats = ["/".join(p) for n in (1, 2, 3) for p in itertools.product(segs, repeat=n)]
    paths = ["/".join(p) for n in (1, 2, 3, 4) for p in itertools.product(psegs, repeat=n)]
    bad = [(p, x) for p in pats for x in paths if sc.glob_matches(p, x) != oracle(p, x)]
    assert bad == [], bad[:10]


def test_sa_concrete_spec_path_in_policy():
    """TC-J65-GLB-002."""
    ok = rzp.narrow_zones("sa", ["openspec/changes/x/specs/a/spec.md"])
    assert ok["violations"] == [] and ok["zones"] == ["openspec/changes/x/specs/a/spec.md"]
    assert sc.glob_matches("openspec/changes/*/specs/**", "openspec/changes/x/specs/a/b/spec.md")
    assert rzp.narrow_zones("sa", ["openspec/specs/a/spec.md"])["violations"]
    # резервация с паттерном пакета держит путь вложенной спеки (post-check)
    assert sc.zone_holds(["openspec/changes/x/specs/**"], "openspec/changes/x/specs/a/spec.md")


def test_tz04_contracts_kept():
    """TC-J65-GLB-003."""
    assert sc.glob_matches("src/*", "src/a.py") and not sc.glob_matches("src/*", "src/a/b.py")
    assert sc.glob_matches("src/**", "src") and sc.glob_matches("src/**", "src/a/b.py")
    assert not sc.glob_matches("src/**", "srcx/a.py")
    assert sc.glob_matches("src", "src/a/b.py") and not sc.glob_matches("src", "srcx")
    assert sc.glob_matches("a/**/b", "a/b") and sc.glob_matches("a/**/b", "a/x/y/b")
    assert sc.glob_matches("**", "any/path") and not sc.glob_matches("a/**/*", "a")
    assert not sc.glob_matches("", "a") and not sc.glob_matches("a/*", "")
