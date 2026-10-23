# -*- coding: utf-8 -*-
"""АУД: инсталлятор и крон-политика 2026-10-23 (install_crons).

Инцидент сессии: кроны исполняют КОПИИ из ~/.hermes/scripts (датированы
4 октября), фикс репо не доезжал до боевого файла — вотчдог спамил чат
5-минутным «ok». install_crons ставит обертки-делегаты (exec к репо-копии),
детектирует устаревшие standalone-копии и печатает реестр рекомендуемых
кронов (политика тишины: чисто = молчание).

Трассировка (rule 6):
  TC-AUD-301  flow_preflight.py/flow_scope_check.py в списках установки; check_mirrors.py — factory-only
  TC-AUD-302  install_crons создает обертки-делегаты для всех крон-скриптов
  TC-AUD-303  повторный прогон идемпотентен: уже-делегаты не переписываются
  TC-AUD-304  standalone-копия с дрейфом mtime/размера → WARN-список и замена оберткой
  TC-AUD-305  упраздненные скрипты (digest, pm-instruction) не оборачиваются, но попадают в WARN
  TC-AUD-306  таблица рекомендуемых кронов: */5 origin, 0 * * * * local, delegate — после проверки, digest — НЕ создавать
  TC-AUD-307  чужая (не-делегирующая) standalone-копия без дрейфа — заменяется, факт фиксируется
  TC-AUD-308  отсутствие репо-копии → errors, остальные скрипты ставятся
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init as fi  # noqa: E402


@pytest.fixture
def hermes_scripts(tmp_path) -> Path:
    """Fixture tmp HERMES_HOME: каталог живых скриптов кронов."""
    d = tmp_path / "hermes_home" / "scripts"
    d.mkdir(parents=True)
    return d


# TC-AUD-301: flow_preflight и flow_scope_check в списках установки,
# check_mirrors — factory-only (в списки не входит)
def test_installer_lists_include_preflight_scope_check_exclude_mirrors():
    all_files = fi.COPY_FILES + fi.FLOW_CONTROL_FILES
    assert "scripts/flow_preflight.py" in all_files
    assert "scripts/flow_scope_check.py" in all_files
    assert "scripts/check_mirrors.py" not in all_files


# TC-AUD-302: install_crons создает обертки-делегаты для всех крон-скриптов
def test_install_crons_creates_delegate_wrappers(hermes_scripts):
    rep = fi.install_crons(hermes_scripts)
    assert rep["errors"] == []
    assert sorted(rep["installed"]) == sorted(fi.WATCHDOG_SCRIPTS)
    for name in fi.WATCHDOG_SCRIPTS:
        text = (hermes_scripts / name).read_text(encoding="utf-8")
        assert str(FACTORY / "scripts" / name) in text  # делегация к репо
        assert "factory-cron-wrapper" in text


# TC-AUD-303: повторный прогон идемпотентен — существующие делегаты не тронуты
def test_install_crons_idempotent_for_existing_wrappers(hermes_scripts):
    fi.install_crons(hermes_scripts)
    before = {n: (hermes_scripts / n).read_text(encoding="utf-8")
              for n in fi.WATCHDOG_SCRIPTS}
    rep = fi.install_crons(hermes_scripts)
    assert rep["installed"] == []
    assert rep["replaced"] == []
    assert sorted(rep["already"]) == sorted(fi.WATCHDOG_SCRIPTS)
    for n, text in before.items():
        assert (hermes_scripts / n).read_text(encoding="utf-8") == text


# TC-AUD-304: устаревшая standalone-копия (mtime+размер дрейфуют) →
# WARN-список + замена оберткой-делегатом
def test_install_crons_flags_stale_standalone_copy(hermes_scripts):
    src = FACTORY / "scripts" / "session_watchdog.py"
    dst = hermes_scripts / "session_watchdog.py"
    dst.write_text("# standalone копия от 4 октября\n" + src.read_text(encoding="utf-8"),
                   encoding="utf-8")
    old = src.stat().st_mtime - 19 * 86400  # копии датированы 4 октября
    os.utime(dst, (old, old))
    rep = fi.install_crons(hermes_scripts)
    assert any("session_watchdog.py" in w for w in rep["stale_warn"])
    assert "session_watchdog.py" in rep["replaced"]
    text = dst.read_text(encoding="utf-8")
    assert str(FACTORY / "scripts" / "session_watchdog.py") in text


# TC-AUD-305: упраздненные скрипты не оборачиваются; их копии — в WARN
def test_install_crons_warns_but_does_not_wrap_abolished(hermes_scripts):
    (hermes_scripts / "watchdog_daily_digest.py").write_text(
        "# digest\n", encoding="utf-8")
    rep = fi.install_crons(hermes_scripts)
    assert rep["abolished_warn"], "копия упраздненного digest должна попасть в WARN"
    assert not (hermes_scripts / "watchdog_daily_digest.py").read_text(
        encoding="utf-8").startswith("#!/usr/bin/env python3\n# factory-cron-wrapper")
    assert "watchdog_daily_digest.py" not in fi.WATCHDOG_SCRIPTS
    assert not (hermes_scripts / "pm_instruction_monitor.py").exists()


# TC-AUD-306: таблица рекомендуемых кронов синхронна с политикой 2026-10-23
def test_recommended_crons_table_matches_policy(capsys):
    fi.print_recommended_crons()
    out = capsys.readouterr().out
    assert "session-watchdog" in out and "*/5 * * * *" in out
    assert "stand-reaper-hourly" in out and "0 * * * *" in out
    assert "origin" in out and "local" in out
    assert "после проверки" in out.lower() or "ПОСЛЕ проверки" in out
    assert "НЕ СОЗДАВАТЬ" in out and "упразднен" in out
    # digest не в числе создаваемых джоб (только строка «НЕ СОЗДАВАТЬ»)
    digest_rows = [l for l in out.splitlines() if "digest" in l]
    assert digest_rows and all("НЕ СОЗДАВАТЬ" in l for l in digest_rows)


# TC-AUD-307: standalone-копия без дрейфа тоже заменяется оберткой
# (канонический источник — репо; факт замены фиксируется в report)
def test_install_crons_replaces_even_fresh_standalone(hermes_scripts):
    src = (FACTORY / "scripts" / "stand_reaper.py").read_text(encoding="utf-8")
    (hermes_scripts / "stand_reaper.py").write_text(src, encoding="utf-8")
    rep = fi.install_crons(hermes_scripts)
    assert "stand_reaper.py" in rep["replaced"]
    assert "stand_reaper.py" in rep["installed"]
    assert str(FACTORY / "scripts" / "stand_reaper.py") in (
        hermes_scripts / "stand_reaper.py").read_text(encoding="utf-8")


# TC-AUD-308: нет репо-копии скрипта → errors, остальные ставятся
def test_install_crons_missing_repo_source_is_error(hermes_scripts, monkeypatch):
    monkeypatch.setattr(fi, "WATCHDOG_SCRIPTS",
                        ["no_such_script.py", "session_watchdog.py"])
    rep = fi.install_crons(hermes_scripts)
    assert any("no_such_script.py" in e for e in rep["errors"])
    assert rep["installed"] == ["session_watchdog.py"]
