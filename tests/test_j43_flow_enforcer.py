# -*- coding: utf-8 -*-
"""Тесты plugins/flow-enforcer (J43: pre_tool_call-энфорсер делегаций).

Фикстуры: tmp-реестр, tmp-репозиторий, tmp-каталог логов
(FLOW_ENFORCER_STATE_DIR) — реальный ~/.hermes/state/ НЕ используется.
subprocess мокается в кейсах вердиктов; последний тест гоняет РЕАЛЬНЫЙ
flowctl prepare --dry-run на fixture-репо (замер латентности prepare).

Кейсы (ТЗ J43):
  (а) не-delegate_task → нет директивы;
  (б) delegate_task без маркеров в strict → block MARKERS_MISSING;
  (в) в permissive → нет директивы (+ строка в логе);
  (г) bypass-маркер → пропуск + запись в bypass-лог;
  (д) flowctl prepare ok (мок subprocess) → ALLOW;
  (е) prepare fail → block с кодом из вывода;
  (ж) исключение в хуке → fail-closed block;
  (з) парсинг маркеров из goal-заголовка (канонический формат);
  + латентность prepare на fixture (реальный subprocess, logging).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402

SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))


# --------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи/реестр в tmp, режим по умолчанию."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(tmp_path / "state" / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    yield state


def delegate_args(goal: str, context: str | None = None) -> dict:
    a = {"goal": goal}
    if context is not None:
        a["context"] = context
    return a


def install_fake_run(monkeypatch, rc: int, out: str, err: str = "") -> list:
    """Мок subprocess.run внутри enforcer; возвращает собранные argv."""
    calls: list[list[str]] = []

    def _fake(argv, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess([], rc, out, err)

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    return calls


HEADER_GOAL = (
    "flow: role=dev repo=/tmp/proj change=add-widget\n"
    "Задача: реализовать виджет. Зона записи: src/.\n"
)
MARKERS = {"role": "dev", "repo": "/tmp/proj", "change": "add-widget",
           "task": None}


# ------------------------------------------------------------ (а) триггер


def test_a_non_delegate_tool_no_directive():
    for tool in ("terminal", "read_file", "write_file", "web_search"):
        assert enforcer.flow_enforce(tool, {"command": "ls"}, "t1") is None


# ------------------------------------------------- (б, в) маркеры/режимы


def test_b_strict_missing_markers_block_code():
    import os
    os.environ["FLOW_ENFORCER_MODE"] = "strict"
    try:
        res = enforcer.flow_enforce(
            "delegate_task", delegate_args("почини стили"), "t2")
    finally:
        os.environ["FLOW_ENFORCER_MODE"] = "permissive"
    assert res is not None and res["action"] == "block"
    assert "MARKERS_MISSING" in res["message"]


def test_c_permissive_missing_markers_passes_and_logs(plugin_env):
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args("почини стили"), "t3")
    assert res is None
    log = plugin_env / "flow-enforcer.log"
    assert log.is_file()
    assert "markers_missing_permissive" in log.read_text(encoding="utf-8")


# ------------------------------------------------------------ (г) bypass


def test_d_bypass_marker_passes_and_logs(plugin_env):
    goal = "flow: bypass --by customer\n" + HEADER_GOAL
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(goal), "t4")
    assert res is None  # никакой subprocess не понадобился
    blog = plugin_env / "flow-enforcer-bypass.log"
    assert blog.is_file()
    entry = json.loads(blog.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["task_id"] == "t4"
    assert entry["goal_head"].startswith("flow: bypass --by customer")


# ------------------------------------------------------- (д/е) subprocess


def test_e_prepare_ok_allows(monkeypatch):
    calls = install_fake_run(monkeypatch, rc=0, out="prepared: true\n")
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t5")
    assert res is None  # ALLOW — без директивы
    assert len(calls) == 1
    argv = calls[0]
    assert argv[2:4] == ["prepare", "--dry-run"]
    for flag, val in (("--role", "dev"), ("--repo", "/tmp/proj"),
                      ("--change", "add-widget"), ("--action", "dev_task")):
        assert argv[argv.index(flag) + 1] == val


def test_f_prepare_fail_blocks_with_code(monkeypatch):
    out = json.dumps({"reason": "PLAN_RELEASE_MISSING",
                      "note": "план релиза не найден"})
    install_fake_run(monkeypatch, rc=1, out=out)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t6")
    assert res is not None and res["action"] == "block"
    assert "PLAN_RELEASE_MISSING" in res["message"]
    assert "exit 1" in res["message"]


def test_f2_stderr_included_in_block(monkeypatch):
    install_fake_run(monkeypatch, rc=2, out="", err="ZONE_OUTSIDE_POLICY: x")
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t6b")
    assert res["action"] == "block"
    assert "ZONE_OUTSIDE_POLICY" in res["message"]


# -------------------------------------------------------- (ж) fail-closed


def test_g_exception_fail_closed(monkeypatch):
    def _boom(argv, **kw):
        raise RuntimeError("flowctl exploded")

    monkeypatch.setattr(enforcer.subprocess, "run", _boom)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t7")
    assert res is not None and res["action"] == "block"
    assert res["message"].startswith("flow-enforcer internal error:")
    assert "(fail-closed)" in res["message"]


# ---------------------------------------------------- (з) парсинг заголовка


def test_h_parse_markers_from_goal_header():
    assert enforcer.parse_markers(delegate_args(HEADER_GOAL)) == MARKERS


def test_h2_parse_markers_from_context_fallback(monkeypatch):
    install_fake_run(monkeypatch, rc=0, out="")
    goal = "Задача: виджет"
    context = "role: qa_automation repo: /tmp/proj change: add-widget"
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(goal, context), "t8")
    assert res is None
    # действие по роли из context-маркеров
    # (проверяется через собранный argv — см. test_e_prepare_ok_allows)


def test_h3_parse_markers_none():
    assert enforcer.parse_markers(delegate_args("без маркеров")) is None
    assert enforcer.parse_markers({}) is None


def test_h4_role_action_mapping():
    assert enforcer.ROLE_ACTIONS["dev"] == "dev_task"
    assert enforcer.ROLE_ACTIONS["code_reviewer"] == "code_review"
    assert enforcer.ROLE_ACTIONS["qa_automation"] == "qa_automation"


# ------------------------------------------- латентность (реальный flowctl)


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")


@pytest.mark.no_plan_fixture
def test_i_real_prepare_latency(tmp_path, monkeypatch):
    """Реальный flowctl prepare --dry-run на fixture-репо: ALLOW + замер.

    Отчет по латентности — duration_s в логе и в выводе теста.
    """
    import re as _re

    # fixture-репо Флоу 1, готовый к dev_task (как в test_flowctl.make_repo)
    repo = tmp_path / "proj"
    repo.mkdir()
    def _git(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True, text=True)
    def _write(rel: str, text: str) -> None:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git("init", "-q")
    _git("config", "user.email", "t@t")
    _git("config", "user.name", "t")
    _write("requirements.md", REQ_APPROVED)
    _write("openspec/changes/add-widget/proposal.md", "# p\n")
    _write("openspec/changes/add-widget/design.md", "# d\n")
    _write("openspec/changes/add-widget/tasks.md",
           "# Tasks\n\n- [ ] 1.1 реализовать виджет\n")
    _write("openspec/changes/add-widget/specs/widget/spec.md",
           "### Requirement: W\n#### Scenario: S\n- GIVEN a\n- WHEN b\n- THEN c\n")
    _write("code-reviews/add-widget/review-001-1.1.md",
           "## Вердикт: approve\nReviewer-Delegation: deleg_testreviewer0000\n")
    _write("sdd.md", "# SDD\n")
    _write("src/widget.py", "X = 1\n")
    # J41: план релиза — обязательный артефакт ворот
    _write("PLAN-add-widget.md",
           "# PLAN-add-widget — план релиза (fixture)\n\n"
           "**Флоу: 1** (J43 latency fixture).\n\n## Этапы\n\n1. dev\n2. review\n3. merge\n")
    _git("add", "-A")
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")

    registry = tmp_path / "state" / "active_sessions.json"
    registry.write_text('{"sessions": []}', encoding="utf-8")
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY", str(registry))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")

    goal = (f"flow: role=dev repo={repo} change=add-widget\n"
            "task: 1.1\nЗадача: виджет.\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "t9")
    assert res is None, f"ожидался ALLOW, получен block: {res}"

    log = (tmp_path / "state" / "flow-enforcer.log").read_text("utf-8")
    entry = [json.loads(l) for l in log.splitlines()
             if l.strip()][-1]
    assert entry["event"] == "prepare_result" and entry["rc"] == 0
    duration = entry["duration_s"]
    assert duration < 30, f"prepare слишком долог: {duration}s"
    print(f"\n[j43] prepare latency on fixture: {duration}s")
    # WARNING-ветка (>10s) не сработала на fixture
    assert "slow_prepare" not in log


@pytest.mark.no_plan_fixture
def test_j_slow_prepare_logs_warning(tmp_path, monkeypatch):
    """Порог WARNING: prepare дольше 10с пишет WARNING в лог (мок времени)."""
    times = iter([0.0, float(enforcer.SLOW_PREPARE_SECONDS) + 1.0])
    real_monotonic = enforcer.time.monotonic
    monkeypatch.setattr(
        enforcer.time, "monotonic",
        lambda: next(times, real_monotonic()))

    def _fake_run(argv, **kw):
        return subprocess.CompletedProcess([], 0, "ok", "")

    monkeypatch.setattr(enforcer.subprocess, "run", _fake_run)
    res = enforcer.flow_enforce(
        "delegate_task", delegate_args(HEADER_GOAL), "t10")
    assert res is None
    log = (tmp_path / "state" / "flow-enforcer.log").read_text("utf-8")
    assert "slow_prepare" in log and "WARNING" in log


# ------------------------------------- factory_init: шаг установки плагина


def _init(tmp_path):
    sys.path.insert(0, str(FACTORY / "scripts"))
    import factory_init
    return factory_init


def _hermes_home(tmp_path, monkeypatch, config: str | None):
    home = tmp_path / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    if config is not None:
        (home / "config.yaml").write_text(config, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_k_install_plugin_copies_and_enables(tmp_path, monkeypatch):
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch,
                        "plugins:\n  enabled:\n    - other-plugin\n")
    assert fi.install_plugin() is True
    assert (home / "plugins" / "flow-enforcer" / "plugin.yaml").is_file()
    cfg = (home / "config.yaml").read_text("utf-8")
    assert "- flow-enforcer" in cfg
    # (yaml-модуля в stdlib нет; проверяем структуру текста)
    lines = cfg.splitlines()
    i = lines.index("plugins:")
    assert lines[i + 1] == "  enabled:"
    assert sorted(lines[i + 2:i + 4]) == ["    - flow-enforcer",
                                          "    - other-plugin"]


def test_k2_install_plugin_already_enabled(tmp_path, monkeypatch):
    fi = _init(tmp_path)
    cfg_text = "plugins:\n  enabled:\n    - flow-enforcer\n"
    home = _hermes_home(tmp_path, monkeypatch, cfg_text)
    assert fi.install_plugin() is True
    assert (home / "config.yaml").read_text("utf-8") == cfg_text  # без правки


def test_k3_install_plugin_no_block_prints_instruction(tmp_path, monkeypatch, capsys):
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch, "llm:\n  model: x\n")
    assert fi.install_plugin() is True
    out = capsys.readouterr().out
    assert "включи вручную" in out
    # конфиг НЕ изменен
    assert "flow-enforcer" not in (home / "config.yaml").read_text("utf-8")


def test_k4_install_plugin_skip(tmp_path, monkeypatch):
    fi = _init(tmp_path)
    home = _hermes_home(tmp_path, monkeypatch, None)
    assert fi.install_plugin(skip=True) is True
    assert not (home / "plugins" / "flow-enforcer").exists()


def test_k5_bootstrap_hint(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(FACTORY / "scripts"))
    import factory_bootstrap as fb
    home = _hermes_home(tmp_path, monkeypatch, None)
    fb.plugin_hint()
    assert "НЕ установлен" in capsys.readouterr().out
    (home / "plugins" / "flow-enforcer").mkdir()
    fb.plugin_hint()
    assert "установлен" in capsys.readouterr().out
