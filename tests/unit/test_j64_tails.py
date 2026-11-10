# -*- coding: utf-8 -*-
"""Хвосты J64: J64.9 (ruleset_check), J64.11 (зона debug), J64.17 (CI по SHA).

Трассировка:
  TC-J64-T-001  ruleset_check: боевой ruleset — OK (exit 0); выключенный,
                с bypass, без PR-правила или без обязательной проверки —
                расхождение (exit 1); нечитаемый файл — exit 2
  TC-J64-T-002  debug пишет только docs/project-pitfalls.md (решение
                Заказчика 2026-11-10, «Зона только pitfalls»)
  TC-J64-T-003  flow.yml: actions — по 40-символьному SHA, pytest — с версией
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import role_zone_policy as rzp  # noqa: E402
import ruleset_check as rc  # noqa: E402

GOOD = {
    "enforcement": "active", "bypass_actors": [], "target": "branch",
    "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
    "rules": [
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {}},
        {"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "test-flow-control"},
                                       {"context": "flow"}]}},
    ],
}


def _run(tmp_path, data, capsys):
    f = tmp_path / "rs.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    rc_ = rc.main(["--from-json", str(f)])
    return rc_, capsys.readouterr().out


def test_ruleset_ok(tmp_path, capsys):
    """TC-J64-T-001."""
    code, out = _run(tmp_path, GOOD, capsys)
    assert code == 0 and "OK" in out


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.update(enforcement="disabled"), "enforcement"),
    (lambda d: d.update(bypass_actors=[{"actor_id": 1}]), "bypass_actors"),
    (lambda d: d["rules"].pop(1), "pull_request"),
    (lambda d: d["rules"].pop(0), "non_fast_forward"),
    (lambda d: d["conditions"]["ref_name"].update(include=["refs/heads/dev"]), "не нацелен на main"),
    (lambda d: d["rules"][2]["parameters"]["required_status_checks"].pop(), "flow"),
])
def test_ruleset_problems(tmp_path, capsys, mutate, needle):
    """TC-J64-T-001."""
    data = copy.deepcopy(GOOD)
    mutate(data)
    code, out = _run(tmp_path, data, capsys)
    assert code == 1 and "РАСХОЖДЕНИЕ" in out and needle in out


def test_ruleset_unreadable(tmp_path):
    """TC-J64-T-001."""
    assert rc.main(["--from-json", str(tmp_path / "missing.json")]) == 2


def test_ruleset_without_bypass_field_unknown(tmp_path, capsys):
    """TC-J64-T-001: нет bypass_actors (токен без права) — UNKNOWN, не OK."""
    data = copy.deepcopy(GOOD)
    del data["bypass_actors"]
    code, _ = _run(tmp_path, data, capsys)
    assert code == 2


def test_ruleset_not_found(monkeypatch, capsys):
    """TC-J64-T-001: ruleset main не найден — exit 2."""
    monkeypatch.setattr(rc, "_gh", lambda args: "[]" if args[:2] == ["api", "repos/o/r/rulesets"] else "o/r")
    assert rc.main(["--repo", "o/r"]) == 2
    assert "не найден" in capsys.readouterr().err


def test_debug_zone_only_pitfalls():
    """TC-J64-T-002."""
    ok = lambda p: rzp.narrow_zones("debug", [p])["violations"] == []  # noqa: E731
    assert ok("docs/project-pitfalls.md")
    for p in ("docs/other.md", "src/app.py", "tests/unit/test_x.py",
              "test-model/regress/c1/log.md"):
        assert not ok(p), p


def test_ci_pinned():
    """TC-J64-T-003."""
    text = (FACTORY / ".github" / "workflows" / "flow.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses
    assert re.search(r"pip install[^\n]*\bpytest==\d+\.\d+\.\d+", text)
