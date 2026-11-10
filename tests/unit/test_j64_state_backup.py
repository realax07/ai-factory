# -*- coding: utf-8 -*-
"""J64.6: бэкап и восстановление state движка (решение Заказчика 2026-11-10 —
«Бэкап + восстановление»).

Трассировка:
  TC-J64-SB-001  backup: архив state-<UTC>.tar.gz в AF_BACKUP_DIR; без
                 session-archive по умолчанию; ротация --keep; --dest внутри
                 state — отказ
  TC-J64-SB-002  restore: удаленный state восстанавливается из архива без
                 ручных правок JSON (приемка ТЗ); прежний state сохраняется
                 рядом, не удаляется
  TC-J64-SB-003  restore при активных сессиях — отказ без --force
  TC-J64-SB-004  restore отклоняет архив с путями вне state (.., абсолютные,
                 ссылки) — state не тронут
  TC-J64-SB-005  обертка крона и строка в таблице рекомендуемых кронов
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402
import state_backup as sb  # noqa: E402


@pytest.fixture
def paths(tmp_path, monkeypatch):
    state, dest = tmp_path / "state", tmp_path / "backups"
    monkeypatch.setenv("AF_STATE_DIR", str(state))
    monkeypatch.setenv("AF_BACKUP_DIR", str(dest))
    state.mkdir()
    (state / "flow_mode.json").write_text('{"mode": "enforcing"}', encoding="utf-8")
    (state / "active_sessions.json").write_text(
        json.dumps({"sessions": [{"delegation_id": "d1", "status": "closed"}]}),
        encoding="utf-8")
    (state / "flowctl_state.json").write_text('{"runs": {}}', encoding="utf-8")
    (state / "session-archive").mkdir()
    (state / "session-archive" / "big.jsonl").write_text("x" * 100, encoding="utf-8")
    return state, dest


def test_backup_and_rotation(paths, capsys):
    """TC-J64-SB-001."""
    state, dest = paths
    assert sb.main(["backup"]) == 0
    assert capsys.readouterr().out == ""            # крон: чисто = молчание
    arcs = sb.archives(dest)
    assert len(arcs) == 1
    with tarfile.open(arcs[0]) as tar:
        names = tar.getnames()
    assert "state/flow_mode.json" in names
    assert not any("session-archive/" in n for n in names)
    for _ in range(4):
        sb.backup(state, dest, keep=3)
    assert len(sb.archives(dest)) == 3
    with pytest.raises(RuntimeError, match="внутри state"):
        sb.backup(state, state / "bk")


def test_restore_after_state_loss(paths):
    """TC-J64-SB-002: приемка ТЗ — удалить state и восстановить."""
    state, dest = paths
    arc = sb.backup(state, dest)
    import shutil
    shutil.rmtree(state)
    assert sb.main(["restore", str(arc)]) == 0
    assert json.loads((state / "flow_mode.json").read_text(encoding="utf-8"))["mode"] == "enforcing"
    assert (state / "active_sessions.json").is_file()
    # повторное восстановление поверх существующего — прежний сохраняется
    (state / "marker").write_text("1", encoding="utf-8")
    prev = sb.restore(arc, state)
    assert prev is not None and (prev / "marker").is_file()
    assert not (state / "marker").exists()


def test_restore_refuses_active_sessions(paths, capsys):
    """TC-J64-SB-003."""
    state, dest = paths
    arc = sb.backup(state, dest)
    (state / "active_sessions.json").write_text(
        json.dumps({"sessions": [{"delegation_id": "live", "status": "running"}]}),
        encoding="utf-8")
    assert sb.main(["restore", str(arc)]) == 1
    assert "live" in capsys.readouterr().err
    assert sb.main(["restore", str(arc), "--force"]) == 0


@pytest.mark.parametrize("name,kind", [("../evil", "file"), ("/abs", "file"),
                                       ("state/link", "sym"), ("other/x", "file")])
def test_restore_rejects_unsafe_archive(paths, tmp_path, name, kind):
    """TC-J64-SB-004."""
    state, _ = paths
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        if kind == "sym":
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
        else:
            data = b"x"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(RuntimeError):
        sb.restore(bad, state, force=True)
    assert (state / "flow_mode.json").is_file()      # state не тронут
    assert not list(state.parent.glob("state.restore-*"))


def test_cron_wrapper_and_table(tmp_path, capsys):
    """TC-J64-SB-005."""
    assert "state_backup.py" in fi.WATCHDOG_SCRIPTS
    report = fi.install_crons(tmp_path / "scripts")
    assert "state_backup.py" in report["installed"]
    fi.print_recommended_crons()
    assert "state-backup" in capsys.readouterr().out
