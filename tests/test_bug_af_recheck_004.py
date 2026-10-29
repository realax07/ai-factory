# -*- coding: utf-8 -*-
"""BUG-AF-RECHECK-004: coverage_matrix не читал канонический OpenSpec
«#### Scenario:» и выдавал ложный успех при 0 распознанных сценариев.

Фикс: SCEN_RE распознает (Сценарий|Scenario); 0 распознанных при поданном
входе (и отсутствующий вход) — «СПЕКА НЕ РАСПОЗНАНА (0 сценариев)» + exit 3
(и в strict, и без); uncovered при --strict → exit 2; кейс-ссылка по ИМЕНИ
сценария — не сирота (отсутствие FR/SC не делает корректную ссылку сиротой).
Проверка на реальном пакете add-deterministic-flow: 29 сценариев.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPT = (FACTORY / "skills" / "test-case-design" / "scripts"
          / "coverage_matrix.py")

RU_SPEC = "### Requirement: Логин\n### Сценарий: Успешный вход\n- GIVEN a\n"
EN_SPEC = "### Requirement: Login\n#### Scenario: Successful login\n- GIVEN a\n"


def run_matrix(specs: Path | str, cases: Path | str,
               strict: bool = False) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(SCRIPT), str(specs),
            "--cases", str(cases)]
    if strict:
        argv.append("--strict")
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def make_tree(tmp_path: Path, spec_text: str, case_text: str | None,
              spec_name: str = "spec.md") -> tuple[Path, Path]:
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / spec_name).write_text(spec_text, encoding="utf-8")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(exist_ok=True)
    if case_text is not None:
        (cases_dir / "TC-DEMO-001.md").write_text(case_text,
                                                  encoding="utf-8")
    return spec_dir, cases_dir


COVERED_CASE = ("# TC-DEMO-001\n\nRequirement: FR-1\n\n"
                "Сценарий: Успешный вход — пользователь входит.\n")


# --------------------------------------------------------- распознавание


def test_ru_scenarios_still_recognized(tmp_path):
    """TC-AF-RECHECK-004-01: русский формат «### Сценарий:» сохранен;
    покрытый сценарий → exit 0."""
    spec_dir, cases = make_tree(tmp_path, RU_SPEC, COVERED_CASE)
    p = run_matrix(spec_dir, cases)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Сценариев в спеках: 1" in p.stdout
    assert "Все сценарии покрыты кейсами." in p.stdout


def test_canonical_openspec_scenario_recognized(tmp_path):
    """TC-AF-RECHECK-004-02: канонический «#### Scenario:» (EN) распознается
    (раньше — 0 сценариев и ложное «все покрыты»)."""
    spec_dir, cases = make_tree(tmp_path, EN_SPEC,
                                "# TC-DEMO-001\n\nScenario: Successful "
                                "login — ok.\n")
    p = run_matrix(spec_dir, cases)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Сценариев в спеках: 1" in p.stdout


def test_real_package_deterministic_flow_29_scenarios():
    """TC-AF-RECHECK-004-03: реальный пакет add-deterministic-flow —
    распознано 29 сценариев (канонические «#### Scenario:»)."""
    # 2026-10-29: change архивирован (repo-cleanup) — пакет в archive/
    pkg = FACTORY / "openspec" / "changes" / "archive" / "2026-10-29-add-deterministic-flow"
    cases = FACTORY / "test-model" / "new"
    p = run_matrix(pkg, cases)
    assert p.returncode in (0, 1, 2), p.stdout + p.stderr
    assert "Сценариев в спеках: 29" in p.stdout, p.stdout


# ------------------------------------------------------------- диагностика


def test_zero_scenarios_exit_3_strict_and_plain(tmp_path):
    """TC-AF-RECHECK-004-04: вход-файл есть, сценариев 0 → «СПЕКА НЕ
    РАСПОЗНАНА (0 сценариев)» + exit 3 (и в strict, и без) — не «все
    покрыты»."""
    spec_dir, cases = make_tree(tmp_path, "# Просто проза без сценариев\n",
                                None)
    for strict in (False, True):
        p = run_matrix(spec_dir, cases, strict=strict)
        assert p.returncode == 3, p.stdout + p.stderr
        assert "СПЕКА НЕ РАСПОЗНАНА (0 сценариев)" in p.stdout
        assert "Все сценарии покрыты" not in p.stdout


def test_missing_input_exit_3(tmp_path):
    """TC-AF-RECHECK-004-05: отсутствующий вход → exit 3 с диагностикой."""
    p = run_matrix(tmp_path / "no-such-dir", tmp_path / "no-cases")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "СПЕКА НЕ РАСПОЗНАНА (0 сценариев)" in p.stdout


# ------------------------------------------------------- exit-коды strict


def test_uncovered_strict_exit_2(tmp_path):
    """TC-AF-RECHECK-004-06: непокрытый сценарий → exit 2 в strict
    (непустой отчет), exit 1 без strict."""
    spec_dir, cases = make_tree(tmp_path, RU_SPEC, None)
    p = run_matrix(spec_dir, cases, strict=True)
    assert p.returncode == 2 and "БЕЗ КЕЙСОВ (1)" in p.stdout
    p2 = run_matrix(spec_dir, cases, strict=False)
    assert p2.returncode == 1


# ------------------------------------------------------------------ сироты


def test_named_scenario_reference_not_orphan(tmp_path):
    """TC-AF-RECHECK-004-07: кейс ссылается на сценарий по ИМЕНИ (без
    SC/FR/NFR-идентификатора) — НЕ сирота (корректная ссылка не осирочена
    отсутствием идентификатора)."""
    spec_dir, cases = make_tree(
        tmp_path, RU_SPEC,
        "# TC-DEMO-001\n\nСценарий: Успешный вход — покрытие по имени.\n")
    p = run_matrix(spec_dir, cases)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "КЕЙСЫ-СИРОТЫ" not in p.stdout
