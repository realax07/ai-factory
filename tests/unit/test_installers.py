# -*- coding: utf-8 -*-
"""Установщики фабрики: factory_bootstrap.py (машина) и factory_init.py (проект).

Ревизия 2026-11-07 (PLAN-installers.md): bootstrap ставил системный crontab
(*/2 session_watchdog, */5 delegate_watchdog) вопреки политике кронов
2026-10-23, писал flow_mode.json в HERMES_HOME/state мимо AF_STATE_DIR и
FLOW_MODE_FILE, не проверял OpenSpec и Pi; factory_init создавал
упраздненный test-model/checklists (J23) и ставил плагин и кроны Hermes на
машине без Hermes.

Трассировка:
  TC-INST-001  режим ворот bootstrap — тот же файл, что читает flow_mode.py
               (FLOW_MODE_FILE / AF_STATE_DIR); новый — shadow; существующий
               без флага не меняется; флаг — перезаписывает
  TC-INST-002  bootstrap не пишет системный crontab; записи прежнего
               bootstrap — WARN; без Hermes обертки кронов не ставятся
  TC-INST-003  zone-guard: нет — копируется; совпадает — не трогается;
               отличается — не перезаписывается (WARN)
  TC-INST-004  check_env: отсутствие openspec — MISSING (False), отсутствие
               pi — только WARN
  TC-INST-005  factory_init: без test-model/checklists; без Hermes —
               плагин и кроны пропущены, init OK; шаблон impact — в templates/
  TC-INST-006  flow_check: легаси _template/impact.md — WARN и пропуск;
               любой другой openspec/changes/_* проверяется как пакет
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))


_ENV_KEYS = ("HERMES_HOME", "AF_STATE_DIR", "PI_AGENT_DIR", "FLOW_MODE_FILE")


@pytest.fixture
def bootstrap_env(tmp_path):
    """Свежий импорт bootstrap с путями машины во временном каталоге.

    reload переписывает константы модулей (flow_mode._STATE_DIR и т.п.),
    поэтому после теста env восстанавливается и модули перезагружаются
    заново — состояние не протекает в другие тесты сьюта.
    """
    import os
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}

    def make(hermes: bool = True):
        home = tmp_path / "hermes"
        if hermes:
            home.mkdir(exist_ok=True)
        os.environ["HERMES_HOME"] = str(home)
        os.environ["AF_STATE_DIR"] = str(tmp_path / "state")
        os.environ["PI_AGENT_DIR"] = str(tmp_path / "pi")
        os.environ.pop("FLOW_MODE_FILE", None)
        return _reload_all()

    yield make
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reload_all()


def _reload_all():
    import factory_paths
    import flow_mode
    importlib.reload(factory_paths)
    importlib.reload(flow_mode)
    import factory_bootstrap
    return importlib.reload(factory_bootstrap)


class TestFlowMode:
    def test_new_file_shadow_in_state_dir(self, bootstrap_env, monkeypatch, tmp_path):
        """TC-INST-001: файл режима — в AF_STATE_DIR, тот же, что у flow_mode."""
        fb = bootstrap_env()
        assert fb.state_dirs() == "shadow"
        f = tmp_path / "state" / "flow_mode.json"
        assert fb.fm.mode_file() == f
        assert json.loads(f.read_text(encoding="utf-8"))["mode"] == "shadow"
        assert not (tmp_path / "hermes" / "state").exists()

    def test_flow_mode_file_env_respected(self, bootstrap_env, monkeypatch, tmp_path):
        """TC-INST-001: FLOW_MODE_FILE — приоритет, как у flow_mode.py."""
        fb = bootstrap_env()
        custom = tmp_path / "custom" / "mode.json"
        monkeypatch.setenv("FLOW_MODE_FILE", str(custom))
        fb.state_dirs()
        assert custom.is_file()

    def test_existing_mode_kept_without_flag(self, bootstrap_env, monkeypatch, tmp_path, capsys):
        """TC-INST-001: боевой режим не сбрасывается повторным bootstrap."""
        fb = bootstrap_env()
        fb.fm.set_mode("enforcing", by="customer")
        assert fb.state_dirs() == "enforcing"
        assert fb.fm.get_mode() == "enforcing"
        assert fb.state_dirs("shadow") == "shadow"   # явный флаг
        assert fb.fm.get_mode() == "shadow"
        assert "понижает боевой" in capsys.readouterr().out


class TestCrons:
    def test_no_system_crontab_write(self, bootstrap_env, monkeypatch, tmp_path, capsys):
        """TC-INST-002: crontab только читается; legacy-запись — WARN."""
        fb = bootstrap_env()
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw.get("input")))
            if cmd[:2] == ["crontab", "-l"]:
                return subprocess.CompletedProcess(
                    cmd, 0, "*/2 * * * * python3 /x/session_watchdog.py\n# delegate_watchdog.py\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(fb.subprocess, "run", fake_run)
        assert fb.setup_crons() is True
        out = capsys.readouterr().out
        assert "запись прежнего bootstrap" in out and "session_watchdog.py" in out
        assert out.count("запись прежнего bootstrap") == 1   # комментарий не считается
        assert all(cmd[:2] != ["crontab", "-"] for cmd, _ in calls)
        wrappers = tmp_path / "hermes" / "scripts"
        assert (wrappers / "session_watchdog.py").is_file()

    def test_no_hermes_no_wrappers(self, bootstrap_env, monkeypatch, tmp_path, capsys):
        """TC-INST-002: оркестратор не Hermes — обертки не ставятся."""
        fb = bootstrap_env(hermes=False)
        monkeypatch.setattr(fb, "legacy_crontab_entries", lambda: [])
        assert fb.setup_crons() is True
        assert "Hermes не найден" in capsys.readouterr().out
        assert not (tmp_path / "hermes").exists()


class TestZoneGuard:
    def test_install_same_differs(self, bootstrap_env, monkeypatch, tmp_path, capsys):
        """TC-INST-003."""
        fb = bootstrap_env()
        dst = tmp_path / "pi" / "extensions" / "zone-guard.ts"
        assert fb.install_zone_guard() is True
        assert dst.read_bytes() == fb.ZONE_GUARD_SRC.read_bytes()
        assert fb.install_zone_guard() is True
        assert "актуален" in capsys.readouterr().out
        dst.write_text("// local", encoding="utf-8")
        assert fb.install_zone_guard() is True
        out = capsys.readouterr().out
        assert "отличается от репо" in out
        assert dst.read_text(encoding="utf-8") == "// local"
        assert "models.json" in out


def test_check_env_openspec_required_pi_optional(bootstrap_env, monkeypatch, tmp_path, capsys):
    """TC-INST-004."""
    fb = bootstrap_env()
    missing = {"openspec"}

    def fake(cmd):
        if cmd[0] in missing:
            return 127, ""
        return 0, f"{cmd[0]} 1.14.0"

    monkeypatch.setattr(fb, "_run", fake)
    assert fb.check_env() is False
    assert "openspec: MISSING" in capsys.readouterr().out
    missing = {"pi"}
    assert fb.check_env() is True
    assert "pi: WARN" in capsys.readouterr().out


def test_factory_init_without_hermes(tmp_path):
    """TC-INST-005: init без Hermes — плагин и кроны пропущены, OK; без
    упраздненного test-model/checklists."""
    target = tmp_path / "init-target"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    env = {k: v for k, v in __import__("os").environ.items()}
    env["HERMES_HOME"] = str(tmp_path / "no-hermes")
    env["AF_STATE_DIR"] = str(tmp_path / "state")
    r = subprocess.run([sys.executable, str(FACTORY / "scripts" / "factory_init.py"),
                        "--target", str(target), "--name", "T"],
                       capture_output=True, text=True, env=env)
    assert "плагин flow-enforcer: пропуск — Hermes не найден" in r.stdout
    assert "кроны: пропуск — Hermes не найден" in r.stdout
    assert not (tmp_path / "no-hermes").exists()
    assert not (target / "test-model" / "checklists").exists()
    assert "post-init flow_check" in r.stdout and "(exit 0)" in r.stdout
    # rc 0, либо 1 только из-за отсутствия openspec CLI на машине сьюта
    assert r.returncode == 0 or (r.returncode == 1 and "openspec CLI: НЕ найден" in r.stdout), r.stdout
    assert (target / "templates" / "impact.template.md").is_file()
    assert not (target / "openspec" / "changes" / "_template").exists()


def _repo_with_change_dir(tmp_path, name, files):
    repo = tmp_path / "chk"
    for rel, text in files.items():
        p = repo / "openspec" / "changes" / name / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return repo


def test_flow_check_legacy_template_only(tmp_path, capsys):
    """TC-INST-006."""
    import flow_check as fc
    repo = _repo_with_change_dir(tmp_path, "_template", {"impact.md": "# Impact\n"})
    assert fc.check(repo) == 0
    assert "легаси-шаблон impact-карты" in capsys.readouterr().out
    # _template с дельтой спеки — уже не шаблон: контракты 1/2 действуют
    (repo / "openspec" / "changes" / "_template" / "specs" / "x").mkdir(parents=True)
    (repo / "openspec" / "changes" / "_template" / "specs" / "x" / "spec.md").write_text(
        "## ADDED Requirements\n", encoding="utf-8")
    assert fc.check(repo) > 0
    capsys.readouterr()
    other = _repo_with_change_dir(tmp_path / "o", "_x", {"proposal.md": "# p\n"})
    assert fc.check(other) > 0
    assert "openspec/changes/_x" in capsys.readouterr().out
