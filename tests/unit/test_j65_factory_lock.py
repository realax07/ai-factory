# -*- coding: utf-8 -*-
"""J65.7: ворота CI проекта — по закрепленной версии фабрики (factory.lock).

Решение Заказчика 2026-11-10: «Lock по SHA сейчас» (теги core-vX.Y — после
J65.6; копии скриптов в проектах снимаются после перевода всех трех
проектов, вместе с J66).

Трассировка:
  TC-J65-LCK-001  factory.lock: запись/чтение; битый (нет sha, не 40 hex, нет
                  repo, строка без '=') — LockError
  TC-J65-LCK-002  update без --sha: HEAD фабрики не в origin/main — отказ;
                  битый lock update перезаписывает
  TC-J65-LCK-003  шаг «Factory lock» из flow.yml (bash как есть): lock есть —
                  sha/repo в GITHUB_OUTPUT, FACTORY_SCRIPTS=.factory/scripts;
                  нет — FACTORY_SCRIPTS=scripts; битый — exit 1
  TC-J65-LCK-004  flow.yml: checkout фабрики по lock в .factory, flow_check и
                  pr_validate — через $FACTORY_SCRIPTS
  TC-J65-LCK-005  factory_init: lock пишется только опубликованным HEAD,
                  существующий без --force не трогается
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402
import factory_lock as fl  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
FLOW_YML = (FACTORY / ".github" / "workflows" / "flow.yml").read_text(encoding="utf-8")


def test_roundtrip_and_errors(tmp_path):
    """TC-J65-LCK-001."""
    assert fl.read_lock(tmp_path) is None
    fl.write_lock(tmp_path, SHA)
    assert fl.read_lock(tmp_path) == {"repo": fl.DEFAULT_REPO, "sha": SHA}
    for body in ("repo=a/b\n", f"repo=a/b\nsha={SHA[:-1]}\n", f"sha={SHA}\n",
                 f"repo=a/b\nsha={SHA}\noops\n", f"repo=a/b\nrepo=c/d\nsha={SHA}\n",
                 f"repo = a/b\nsha={SHA}\n", f"  repo=a/b\nsha={SHA}\n",
                 f"repo=evil;rm\nsha={SHA}\n", f"repo=a/b\r\nsha={SHA}\r\n"):
        (tmp_path / fl.LOCK_NAME).write_text(body, encoding="utf-8")
        with pytest.raises(fl.LockError):
            fl.read_lock(tmp_path)


def test_update_refuses_unpublished(tmp_path, monkeypatch, capsys):
    """TC-J65-LCK-002: HEAD не влит в origin/main (несуществующий SHA) — отказ;
    битый lock update перезаписывает."""
    monkeypatch.setattr(fl, "_git", lambda *a: SHA)
    assert fl.main(["update", "--target", str(tmp_path)]) == 1
    assert "не влит в origin/main" in capsys.readouterr().err
    assert not (tmp_path / fl.LOCK_NAME).exists()
    assert fl.main(["update", "--target", str(tmp_path), "--sha", SHA]) == 0
    assert fl.read_lock(tmp_path)["sha"] == SHA
    (tmp_path / fl.LOCK_NAME).write_text("garbage\n", encoding="utf-8")
    assert fl.main(["update", "--target", str(tmp_path), "--sha", SHA]) == 0
    assert fl.read_lock(tmp_path)["sha"] == SHA


def _lock_step_script() -> str:
    m = re.search(r"- name: Factory lock \(J65\.7\)\n\s+id: lock\n\s+run: \|\n(.*?)\n\n",
                  FLOW_YML, re.S)
    assert m, "шаг Factory lock не найден"
    return "\n".join(line[10:] for line in m.group(1).splitlines())


@pytest.mark.parametrize("lock,rc,out_sha,scripts", [
    (f"# c\nrepo=realax07/ai-factory\nsha={SHA}\n", 0, SHA, ".factory/scripts"),
    (None, 0, None, "scripts"),
    ("repo=realax07/ai-factory\nsha=deadbeef\n", 1, None, None),
    (f"repo=evil;rm\nsha={SHA}\n", 1, None, None),
    (f"repo=a/b\nrepo=c/d\nsha={SHA}\n", 1, None, None),
    (f"repo = a/b\nsha={SHA}\n", 1, None, None),
    (f"  repo=a/b\nsha={SHA}\n", 1, None, None),
])
def test_lock_step_shell(tmp_path, lock, rc, out_sha, scripts):
    """TC-J65-LCK-003: шаг CI исполняется bash'ем как в Actions."""
    if lock is not None:
        (tmp_path / fl.LOCK_NAME).write_text(lock, encoding="utf-8")
    out, env = tmp_path / "out", tmp_path / "env"
    r = subprocess.run(["bash", "-e", "-c", _lock_step_script()], cwd=tmp_path,
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(out),
                            "GITHUB_ENV": str(env), "GITHUB_WORKSPACE": str(tmp_path)})
    assert r.returncode == rc, r.stdout + r.stderr
    if rc:
        return
    envtext = env.read_text()
    assert f"FACTORY_SCRIPTS={scripts}" in envtext
    assert (f"AI_FACTORY_HOME={tmp_path}/.factory" in envtext) is bool(out_sha)
    if out_sha:
        assert f"sha={out_sha}" in out.read_text()
        assert "repo=realax07/ai-factory" in out.read_text()
        # чтение python и shell согласованы
        assert fl.read_lock(tmp_path)["sha"] == out_sha


def test_flow_yml_uses_lock():
    """TC-J65-LCK-004."""
    assert re.search(r"repository: \$\{\{ steps\.lock\.outputs\.repo \}\}", FLOW_YML)
    assert re.search(r"ref: \$\{\{ steps\.lock\.outputs\.sha \}\}", FLOW_YML)
    assert "path: .factory" in FLOW_YML
    assert "if: steps.lock.outputs.sha != ''" in FLOW_YML
    assert "persist-credentials: false" in FLOW_YML
    assert 'python3 "$FACTORY_SCRIPTS/flow_check.py" .' in FLOW_YML
    assert 'python3 "$FACTORY_SCRIPTS/pr_validate.py" .' in FLOW_YML
    assert "python3 scripts/flow_check.py" not in FLOW_YML
    assert "python3 scripts/pr_validate.py" not in FLOW_YML


def test_factory_init_lock(tmp_path, monkeypatch, capsys):
    """TC-J65-LCK-005."""
    monkeypatch.setattr(fl, "published_head", lambda: SHA)
    assert fi.install_factory_lock(tmp_path) is True
    assert fl.read_lock(tmp_path)["sha"] == SHA
    other = "f" * 40
    monkeypatch.setattr(fl, "published_head", lambda: other)
    assert fi.install_factory_lock(tmp_path) is True          # без --force — не тронут
    assert fl.read_lock(tmp_path)["sha"] == SHA
    assert fi.install_factory_lock(tmp_path, force=True) is True
    assert fl.read_lock(tmp_path)["sha"] == other

    def unpublished():
        raise fl.LockError("не опубликован")
    monkeypatch.setattr(fl, "published_head", unpublished)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert fi.install_factory_lock(fresh) is False
    assert not (fresh / fl.LOCK_NAME).exists()
