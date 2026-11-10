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
  TC-J65-PZ-003  пак без политики (auditor) не генерируется; debug — с зоной
                 docs/project-pitfalls.md (J64.11, 2026-11-10) [test-adapted];
                 плейсхолдер генератора = role_zone_policy.CHANGE_ID
  TC-J65-PZ-004  пример в двойных кавычках не трогается; пак с политикой без
                 маркеров — ошибка с именем файла (rc 2)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import gen_role_docs as gen  # noqa: E402
import package_runner as pr  # noqa: E402
import role_zone_policy as rzp  # noqa: E402

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
        # то, что раннер прокидывает стадии без zones: policy_zones → normalize
        runner = []
        for z in pr.policy_zones(role["pack"], rzp.CHANGE_ID):
            n = pr.normalize_zone(z)
            if n not in runner:
                runner.append(n)
        assert pref.split(":") == runner, path


def test_pack_examples_use_policy_prefix():
    """TC-J65-PZ-002."""
    with_example = set()
    for path, role in gen.pack_targets(ROLES):
        _, prefix = gen.pack_zone_forms(role)
        want = prefix.replace("<id>", gen.EXAMPLE_ID)
        for value in re.findall(r"PI_ZONE_WRITE='([^']*)'",
                                path.read_text(encoding="utf-8")):
            assert value == want, path
            with_example.add(role["pack"])
    # у каждого пака с политикой есть пример запуска, кроме regress-runner
    # (у него шаблон в двойных кавычках — генератор его не трогает)
    expected = {r["pack"] for _, r in gen.pack_targets(ROLES)} - {"regress-runner"}
    assert with_example == expected


def test_packs_without_policy_untouched():
    """TC-J65-PZ-003."""
    packs = {r["pack"] for _, r in gen.pack_targets(ROLES)}
    assert "auditor" not in packs and "debug" in packs
    for pack in ("auditor",):
        text = (gen.PACKS / pack / "README.md").read_text(encoding="utf-8")
        assert "roles:pack-zone" not in text
    assert gen.CHANGE_ID_PLACEHOLDER == rzp.CHANGE_ID


def test_double_quotes_and_missing_markers(tmp_path, monkeypatch, capsys):
    """TC-J65-PZ-004."""
    role = next(r for _, r in gen.pack_targets(ROLES) if r["pack"] == "dev")
    text = 'PI_ZONE_WRITE="зона1:зона2" pi ...\n'
    assert gen.apply_pack_example(text, role) == text
    packs = tmp_path / "packs"
    (packs / "dev").mkdir(parents=True)
    (packs / "dev" / "README.md").write_text("# dev\n", encoding="utf-8")
    monkeypatch.setattr(gen, "PACKS", packs)
    monkeypatch.setattr(gen, "FACTORY", tmp_path)
    monkeypatch.setattr(gen, "TARGETS", {})
    monkeypatch.setattr(gen, "_roles", lambda: [role])
    assert gen.main(["--check"]) == 2
    assert "packs/dev/README.md" in capsys.readouterr().err
