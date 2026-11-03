# -*- coding: utf-8 -*-
"""J64.5: единый модуль путей машины (scripts/factory_paths.py).

Кейсы: дефолты от HOME; каждая переменная окружения переопределяет свой
путь; state_dir по умолчанию внутри HERMES_HOME, AF_STATE_DIR отвязывает;
паритет энфорсера (плагин ставится копией и модуль не импортирует);
в scripts/ и plugins/ не осталось прошитых путей машины; манифест раннера
задает срезаемый env стенда (gate_env_strip).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))
sys.path.insert(0, str(FACTORY / "plugins" / "flow-enforcer"))

import factory_paths as fp  # noqa: E402
import enforcer  # noqa: E402

ENV = ("HERMES_HOME", "AF_STATE_DIR", "AI_FACTORY_HOME", "AF_PROJECTS_ROOT",
       "PI_AGENT_DIR", "FLOW_ENFORCER_STATE_DIR")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_defaults_follow_home(clean_env):
    """TC-FP-001: дефолты путей вычисляются от HOME (как до J64.5)."""
    home = clean_env
    assert fp.hermes_home() == home / ".hermes"
    assert fp.state_dir() == home / ".hermes" / "state"
    assert fp.registry_path() == home / ".hermes" / "state" / "active_sessions.json"
    assert fp.flowctl_state_path() == home / ".hermes" / "state" / "flowctl_state.json"
    assert fp.factory_home() == home / "ai-factory"
    assert fp.projects_root() == home
    assert fp.pi_agent_dir() == home / ".pi" / "agent"


def test_each_env_overrides_its_path(clean_env, monkeypatch, tmp_path):
    """TC-FP-002: каждая переменная окружения переопределяет свой путь."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    # память движка от HERMES_HOME НЕ зависит (ревью J64.5: иначе процесс с
    # другим HERMES_HOME терял flow_mode и раздваивал реестр)
    assert fp.state_dir() == clean_env / ".hermes" / "state"
    assert fp.hermes_home() == tmp_path / "h"
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "s"))
    assert fp.state_dir() == tmp_path / "s"
    monkeypatch.setenv("AI_FACTORY_HOME", str(tmp_path / "f"))
    monkeypatch.setenv("AF_PROJECTS_ROOT", str(tmp_path / "p"))
    monkeypatch.setenv("PI_AGENT_DIR", str(tmp_path / "pi"))
    assert fp.factory_home() == tmp_path / "f"
    assert fp.projects_root() == tmp_path / "p"
    assert fp.pi_agent_dir() == tmp_path / "pi"
    monkeypatch.setenv("AF_STATE_DIR", "  ")                # пустое = дефолт
    assert fp.state_dir() == clean_env / ".hermes" / "state"


@pytest.mark.parametrize("env", [
    {},
    {"HERMES_HOME": "h"},
    {"HERMES_HOME": "h", "AF_STATE_DIR": "s"},
    {"AI_FACTORY_HOME": "f", "AF_PROJECTS_ROOT": "p"},
])
def test_enforcer_paths_parity(clean_env, monkeypatch, tmp_path, env):
    """TC-FP-003: Энфорсер повторяет env и дефолты factory_paths (своя копия функций)."""
    for name, value in env.items():
        monkeypatch.setenv(name, str(tmp_path / value))
    assert enforcer.state_dir() == fp.state_dir()
    assert enforcer.factory_home() == fp.factory_home()
    assert enforcer.projects_root() == fp.projects_root()


def test_no_hardcoded_machine_paths():
    """TC-FP-004: В коде ворот нет прошитых путей машины — только factory_paths и
    зеркало в энфорсере (J64.5, критерий приемки)."""
    pattern = re.compile(r'Path\.home\(\)|expanduser\("~|/home/[a-z]+/')
    allowed = {"scripts/factory_paths.py"}
    offenders = []
    for path in sorted([*FACTORY.glob("scripts/*.py"),
                        *FACTORY.glob("plugins/**/*.py")]):
        rel = path.relative_to(FACTORY).as_posix()
        if rel in allowed:
            continue
        for no, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if not pattern.search(code):
                continue
            if rel.endswith("enforcer.py") and "_env_path(" in code:
                continue  # зеркало factory_paths (паритет — тест выше)
            offenders.append(f"{rel}:{no}: {line.strip()}")
    assert offenders == []


def test_cli_describe(clean_env):
    """TC-FP-005: CLI печатает текущие пути."""
    out = subprocess.run([sys.executable, str(FACTORY / "scripts/factory_paths.py")],
                         capture_output=True, text=True, check=True).stdout
    assert "registry" in out and str(clean_env) in out


def test_runner_gate_env_strip_from_manifest(tmp_path):
    """TC-FP-006: J64.5: срезаемый env стенда — из манифеста; без ключа — дефолт пилота;
    [] — не срезать; не список — ManifestError."""
    import package_runner as pr
    base = ("# P\n\n```yaml\npipeline:\n  package: p\n  flow: 5\n{extra}"
            "  stages:\n    - id: a\n      run: gate:true\n```\n")

    def manifest(extra: str):
        plan = tmp_path / "PLAN-p.md"
        plan.write_text(base.format(extra=extra), encoding="utf-8")
        return pr.parse_manifest(plan)

    assert manifest("")["gate_env_strip"] is None
    assert manifest("  gate_env_strip: [APP_URL, APP_DB]\n")[
        "gate_env_strip"] == ["APP_URL", "APP_DB"]
    assert manifest("  gate_env_strip: []\n")["gate_env_strip"] == []
    with pytest.raises(pr.ManifestError):
        manifest("  gate_env_strip: APP_URL\n")


def test_runner_gate_command_env_stripped_per_manifest(tmp_path, monkeypatch):
    """TC-FP-007: Сквозная проверка: gate-команда не видит переменную из
    pipeline.gate_env_strip, видит прочие."""
    import package_runner as pr
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True)
    (repo / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "i"], check=True)
    plan = repo / "PLAN-p.md"
    plan.write_text(
        "# P\n\n```yaml\npipeline:\n  package: p\n  flow: 5\n"
        "  gate_env_strip: [APP_URL]\n  stages:\n"
        "    - id: a\n      run: gate:test -z \"$APP_URL\" && test -n \"$KEEP\"\n"
        "```\n", encoding="utf-8")
    monkeypatch.setenv("APP_URL", "http://stand")
    monkeypatch.setenv("KEEP", "1")
    monkeypatch.setattr(pr, "ensure_worktree", lambda r, s, b: repo)
    assert pr.cmd_run(plan, dry_run=False) == 0


@pytest.mark.parametrize("script", ["flow_check.py", "pr_validate.py"])
def test_autonomous_copy_without_factory_paths(tmp_path, clean_env, script):
    """TC-FP-008 (ревью J64.5, major): копия flow_check/pr_validate в проекте
    без factory_paths.py работает (запасной дефолт), а не падает на импорте."""
    import shutil
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    shutil.copy2(FACTORY / "scripts" / script, proj / "scripts" / script)
    if script == "pr_validate.py":   # pr_validate импортирует session_check
        shutil.copy2(FACTORY / "scripts" / "session_check.py",
                     proj / "scripts" / "session_check.py")
        shutil.copy2(FACTORY / "scripts" / "flow_mode.py",
                     proj / "scripts" / "flow_mode.py")
    proc = subprocess.run([sys.executable, f"scripts/{script}", "--help"],
                          cwd=proj, capture_output=True, text=True)
    assert "ModuleNotFoundError" not in proc.stderr, proc.stderr
    assert "factory_paths" not in proc.stderr, proc.stderr


def test_fallback_matches_factory_paths(clean_env, monkeypatch, tmp_path):
    """TC-FP-009: запасные пути автономных копий = factory_paths (те же env
    и дефолты)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fc_copy", FACTORY / "scripts" / "flow_check.py")
    src = (FACTORY / "scripts" / "flow_check.py").read_text("utf-8")
    assert "except ImportError" in src and "AF_STATE_DIR" in src
    for env in ({}, {"AI_FACTORY_HOME": "f", "AF_STATE_DIR": "s",
                     "HERMES_HOME": "h"}):
        for name, value in env.items():
            monkeypatch.setenv(name, str(tmp_path / value))
        ns = {}
        block = src[src.index("    from types import SimpleNamespace"):
                    src.index("    )\n", src.index("fp = _NS(")) + 6]
        exec("import os\nfrom pathlib import Path\n"
             + "\n".join(l[4:] for l in block.splitlines()), ns)
        alt = ns["fp"]
        assert alt.factory_home() == fp.factory_home()
        assert alt.hermes_home() == fp.hermes_home()
        assert alt.state_dir() == fp.state_dir()
        assert alt.flowctl_state_path() == fp.flowctl_state_path()
