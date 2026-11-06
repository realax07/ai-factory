# -*- coding: utf-8 -*-
"""J65.1: единый реестр ролей agents/roles.json.

До J65.1 зона роли жила в словаре role_zone_policy, таблица зон
agents/README.md — отдельным текстом с отпечатком на коммит, зоны паков —
в README паков; места расходились (строк architect/devops/design_validator
в таблице не было, зоны паков шире политики — J64.11). Теперь политика ворот
читается из реестра, таблицы генерируются из него (gen_role_docs.py),
версия политики — sha256 реестра, раннер без `zones:` берет зону роли
целиком.

Трассировка:
  TC-J65-ROL-001  реестр целостен: id уникальны, поля на месте, паки и промпты
                  существуют
  TC-J65-ROL-002  таблицы README сгенерированы и актуальны; ручная правка
                  строки таблицы обнаруживается
  TC-J65-ROL-003  ROLE_ZONE_POLICY и EMPTY_POLICY_ROLES — из реестра
  TC-J65-ROL-004  версия политики — sha256 содержимого реестра
  TC-J65-ROL-005  раннер: pi-стадия без zones берет зону роли из реестра
                  ('*' → change-id пакета); явные zones не трогаются
  TC-J65-ROL-006  реестра нет или он битый — модуль политики не загружается
  TC-J65-ROL-007  factory_init кладет реестр в проект (FLOW_CONTROL_FILES)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402
import gen_role_docs as gen  # noqa: E402
import package_runner as pr  # noqa: E402
import role_zone_policy as rzp  # noqa: E402

REGISTRY = json.loads((FACTORY / "agents" / "roles.json").read_text("utf-8"))
ROLES = REGISTRY["roles"]


def test_registry_integrity():
    """TC-J65-ROL-001"""
    ids = [r["id"] for r in ROLES]
    assert len(ids) == len(set(ids))
    for r in ROLES:
        for key in ("id", "title", "mode", "zone_text", "push", "zones"):
            assert key in r, (r["id"], key)
        if r.get("pack"):
            assert (gen.PACKS / r["pack"] / "settings.example.json").is_file(), r
        if r.get("prompt"):
            assert (FACTORY / r["prompt"]).is_file(), r
        if r.get("empty_policy"):
            assert r["zones"] == [], r


def test_generated_tables_up_to_date():
    """TC-J65-ROL-002"""
    assert gen.main(["--check"]) == 0
    readme = gen.TARGETS["zones"].read_text(encoding="utf-8")
    tampered = readme.replace("| Код-ревьюер | auto-edit |",
                              "| Код-ревьюер | yolo |", 1)
    assert tampered != readme
    assert gen.apply(tampered, "zones", gen.render_zones(ROLES)) == readme


def test_policy_from_registry():
    """TC-J65-ROL-003"""
    expected = {r["id"]: tuple(r["zones"]) for r in ROLES if r["zones"]}
    assert rzp.ROLE_ZONE_POLICY == expected
    assert set(rzp.EMPTY_POLICY_ROLES) == {
        r["id"] for r in ROLES if r.get("empty_policy")}
    assert rzp.allowed_zones_for("unknown-role") == ()


def test_policy_version_is_registry_digest(tmp_path):
    """TC-J65-ROL-004"""
    raw = (FACTORY / "agents" / "roles.json").read_bytes()
    assert rzp.policy_version().endswith(hashlib.sha256(raw).hexdigest())
    changed = dict(REGISTRY)
    changed["roles"] = ROLES[:-1]
    path = tmp_path / "roles.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    _, sha = rzp._load_registry(path)
    assert sha != hashlib.sha256(raw).hexdigest()


def _plan(body: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write("# PLAN-x\n\n```yaml\npipeline:\n  package: add-widget\n"
                "  flow: 1\n  stages:\n" + body + "```\n")
    return Path(f.name)


def test_runner_default_zones_from_registry():
    """TC-J65-ROL-005"""
    m = pr.parse_manifest(_plan("    - id: r\n      run: pi:code-reviewer\n"))
    assert m["stages"][0]["zones"] == ["code-reviews/add-widget/review-*.md"]
    m = pr.parse_manifest(_plan("    - id: d\n      run: pi:dev\n"))
    assert "openspec/changes/add-widget/tasks.md" in m["stages"][0]["zones"]
    m = pr.parse_manifest(_plan(
        "    - id: d\n      run: pi:dev\n      zones: [backend/**]\n"))
    assert m["stages"][0]["zones"] == ["backend/**"]


@pytest.mark.parametrize("content", ["", "{", '{"schema": "roles/0", "roles": []}'])
def test_missing_or_broken_registry_fails_closed(tmp_path, content):
    """TC-J65-ROL-006"""
    path = tmp_path / "roles.json"
    if content:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError):
        rzp._load_registry(path)


def test_factory_init_copies_registry():
    """TC-J65-ROL-007"""
    assert "agents/roles.json" in fi.FLOW_CONTROL_FILES
    assert "scripts/role_zone_policy.py" in fi.FLOW_CONTROL_FILES
