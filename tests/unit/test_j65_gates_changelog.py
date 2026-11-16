# -*- coding: utf-8 -*-
"""J65.6: CHANGELOG ворот (docs/CHANGELOG-gates.md) — базовый список кодов
отказа ядра на core-v1.0 (решение Заказчика 2026-11-16 «Базовый список +
тест»).

Трассировка:
  TC-J65-CHG-001  каждый код отказа и статус ворот в файлах ядра и в
                  скриптах, копируемых в проект, описан строкой таблицы
                  CHANGELOG (новый код без строки — красный тест); не-коды
                  (имена env, паттернов, служебные слова) — явным списком.
                  Не видит коды, собранные только в f-строке (BYPASS — внесен
                  вручную)
  TC-J65-CHG-002  набор файлов ядра покрывает все .py из FLOW_CONTROL_FILES
                  установщика (новый модуль ядра попадает в проверку)
  TC-J65-CHG-003  коды flow_transition.REASON_CODES — все в CHANGELOG
  TC-J65-CHG-004  коды таблицы §9 контракта flow_control_contract.md — все
                  в CHANGELOG
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FACTORY / "scripts"))

import factory_init  # noqa: E402
import flow_transition  # noqa: E402

CHANGELOG = FACTORY / "docs" / "CHANGELOG-gates.md"

CORE_FILES = (
    "scripts/flow_ids.py", "scripts/flow_state.py", "scripts/flow_transition.py",
    "scripts/session_check.py", "scripts/gate_runner.py", "scripts/flowctl.py",
    "scripts/gates_stats.py", "scripts/executor_watchdog.py",
    "scripts/executors/__init__.py", "scripts/executors/pi.py",
    "scripts/executors/hermes.py", "scripts/executors/stub.py",
    "scripts/flow_mode.py", "scripts/role_zone_policy.py",
    "scripts/flow_scope_check.py", "scripts/pr_validate.py",
    "scripts/flow_check.py", "scripts/pm_bounds_check.py",
    "scripts/delegate_gate.py", "scripts/delegate_watchdog.py",
    "scripts/package_runner.py", "plugins/flow-enforcer/enforcer.py",
)

# Скрипты, которые установщик копирует в проект (ворота PR, вотчдоги):
# их коды тоже видит пользователь ворот. factory_paths — модуль путей.
COPY_SCRIPTS = tuple(p for p in factory_init.COPY_FILES
                     if p.endswith(".py") and p != "scripts/factory_paths.py")
SCANNED = tuple(dict.fromkeys(CORE_FILES + COPY_SCRIPTS))

# Строки КАПСОМ в ядре, которые не коды отказа: имена env и констант,
# служебные слова.
NOT_CODES = {
    "CLOSED", "EXECUTOR", "HEAD", "RANGE", "TODO", "KILL", "PR_BODY",
    "AF_EXECUTOR_STUB_CMD", "AF_PROJECTS_ROOT", "BUG_ID_PATTERN",
    "CHANGE_ID_PATTERN", "SLUG_PATTERN", "SEVERITY_PREFIXES",
    "EKOTOV_WIKI_BASE_URL", "EKOTOV_WIKI_DB_PATH",
    "FLOW_ENFORCER_PRODUCT_REPOS", "FLOW_ENFORCER_PUSH", "FLOW_MODEL_ENFORCE",
    "FLOW_ENFORCER_STATE_DIR", "AF_STATE_DIR", "AI_FACTORY_HOME",
}

TOKEN_RE = re.compile(r"""["']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)["']""")
ENV_RE = re.compile(r"""(?:environ(?:\.get)?\(?\[?|getenv\(|_fp_env\(|setenv\(|env\[|delenv\(|pop\()\s*["']([A-Z][A-Z0-9_]+)["']""")
# Документирован — только строкой таблицы: «| `КОД` | смысл |».
DOC_CODE_RE = re.compile(r"^\| `([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)` \|", re.M)


def core_codes() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for rel in SCANNED:
        text = (FACTORY / rel).read_text(encoding="utf-8")
        env = set(ENV_RE.findall(text))
        for tok in TOKEN_RE.findall(text):
            if len(tok) >= 4 and tok not in env and tok not in NOT_CODES:
                found.setdefault(tok, set()).add(rel)
    return found


def documented() -> set[str]:
    return set(DOC_CODE_RE.findall(CHANGELOG.read_text(encoding="utf-8")))


def test_every_core_code_documented():
    """TC-J65-CHG-001."""
    codes = core_codes()
    assert len(codes) > 30, "сканер ничего не нашел — сломан"
    missing = {c: sorted(f) for c, f in codes.items() if c not in documented()}
    assert not missing, ("коды отказа без строки в docs/CHANGELOG-gates.md "
                         f"(или добавь в NOT_CODES, если это не код): {missing}")


def test_not_codes_are_still_present():
    """TC-J65-CHG-001: список не-кодов не копит мертвые записи."""
    texts = "".join((FACTORY / r).read_text(encoding="utf-8") for r in SCANNED)
    stale = sorted(n for n in NOT_CODES if f'"{n}"' not in texts and f"'{n}'" not in texts)
    assert not stale, f"NOT_CODES без вхождений в ядре: {stale}"


def test_core_files_cover_installer_core():
    """TC-J65-CHG-002."""
    installer = {p for p in factory_init.FLOW_CONTROL_FILES if p.endswith(".py")}
    assert installer <= set(CORE_FILES), sorted(installer - set(CORE_FILES))


def test_reason_codes_documented():
    """TC-J65-CHG-003."""
    assert set(flow_transition.REASON_CODES) <= documented()


def test_contract_codes_documented():
    """TC-J65-CHG-004."""
    text = (FACTORY / "contracts" / "flow_control_contract.md").read_text(encoding="utf-8")
    sec = text.split("## 9.", 1)[1].split("\n## ", 1)[0]
    codes = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", sec, re.M))
    assert len(codes) >= 10, codes
    assert codes <= documented(), sorted(codes - documented())
