# -*- coding: utf-8 -*-
"""Тесты MODEL_ENFORCE (J60): маркер исполнителя на боевых этапах 5.3-ролей.

Регруп J59 (решение Заказчика 2026-10-31): боевые волны SA/архитектор/DEV/BA
— через Pi роль-паки (glm-5.3), не через general-делегацию. Правило —
AGENTS.md §Оркестрация 2.1; энфорсер — model_enforce_gate в
plugins/flow-enforcer/enforcer.py (перехват delegate_task ДО разбора
flow-маркеров).

Матрица (ТЗ J60):
  (а) pi-маркер ([pi:<роль5.3>]) на боевом этапе → pass (нет директивы,
      запись model_enforce_pass в лог);
  (б) [hermes:<роль5.3>] на боевом этапе → DENY MODEL_ENFORCE с подсказкой
      pi роль-пака;
  (в) боевой этап без маркера → WARN в лог, делегация НЕ блокирована
      (миграционный период);
  (г) не-5.3 вызов (devops/qa/docs-ключевые слова) → pass без маркера,
      лог чист;
  (д) FLOW_MODEL_ENFORCE=off → ВСЕ кейсы pass (деградация);
  (е) Флоу 2/4/5 (guard flow=2|4|5) → pass без маркера (свобода выбора);
  (ж) регистр маркера не важен; эвристика этапа по каждому ключевому слову.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_DIR = FACTORY / "plugins" / "flow-enforcer"
sys.path.insert(0, str(PLUGIN_DIR))

import enforcer  # noqa: E402


@pytest.fixture(autouse=True)
def plugin_env(tmp_path, monkeypatch):
    """Изолированная среда: логи в tmp, флаг J60 в дефолте ON."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FLOW_ENFORCER_STATE_DIR", str(state))
    monkeypatch.setenv("FLOW_ENFORCER_REGISTRY",
                       str(state / "active_sessions.json"))
    monkeypatch.setenv("FLOW_ENFORCER_MODE", "permissive")
    monkeypatch.setenv("AI_FACTORY_HOME", str(FACTORY))
    # J60: дефолт ON — флаг не должен прилетать из окружения разработчика.
    monkeypatch.delenv("FLOW_MODEL_ENFORCE", raising=False)
    return state


def log_text(plugin_env) -> str:
    log = plugin_env / "flow-enforcer.log"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


def delegate(goal: str):
    return enforcer.flow_enforce("delegate_task", {"goal": goal}, "j60")


# Боевые этапы: эвристика ключевых слов роли + маркер исполнителя.
SA_PI = ("Этап create_change пакета add-widget. Исполнитель [pi:sa] "
         "(роль-пак sa, glm-5.3).")
DEV_PI = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
          "paths=src/widget.py\n"
          "Задача dev: реализовать виджет. Исполнитель [pi:dev].")
ARCH_HERMES = ("arch-review пакета add-widget. Исполнитель [hermes:architect].")
BA_HERMES = ("Разбор requirements пакета add-widget. Исполнитель [hermes:ba].")
SA_NO_MARKER = ("Этап create_change пакета add-widget. СА готовит спеку "
                "и impact-карту.")


# --------------------------------------------------- (а) pi-маркер → pass

def test_a_pi_marker_passes(plugin_env):
    """TC-J60-001: [pi:sa] на боевом этапе → ALLOW, запись в лог."""
    assert delegate(SA_PI) is None
    assert "model_enforce_pass" in log_text(plugin_env)


def test_a2_pi_dev_marker_via_flow_enforce(plugin_env, monkeypatch):
    """TC-J60-002: [pi:dev] на dev_task → ALLOW (end-to-end через хук,
    с моком prepare — дальше J60-ворот делегация легальна)."""
    calls = []

    def _fake(argv, **kw):
        calls.append(list(argv))
        import subprocess
        return subprocess.CompletedProcess([], 0, "prepared: true\n", "")

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    assert delegate(DEV_PI) is None
    log = log_text(plugin_env)
    assert "model_enforce_pass" in log
    assert '"pi_roles": ["dev"]' in log


def test_a3_marker_case_insensitive(plugin_env):
    """TC-J60-003: регистр маркера не важен ([PI:SA])."""
    assert enforcer.model_enforce_gate(
        "Этап create_change. Исполнитель [PI:SA].") is None


# ------------------------------------------- (б) hermes на 5.3-роли → DENY

@pytest.mark.parametrize("goal,role", [
    (ARCH_HERMES, "architect"),
    (BA_HERMES, "ba"),
    ("Задача dev по модулю платежей. Исполнитель [hermes:dev].", "dev"),
    ("СА готовит спеку пакета. Исполнитель [hermes:sa].", "sa"),
])
def test_b_hermes_on_53_role_denied(plugin_env, goal, role):
    """TC-J60-004: [hermes:<роль5.3>] → block MODEL_ENFORCE с подсказкой."""
    res = delegate(goal)
    assert res is not None and res["action"] == "block"
    msg = res["message"]
    assert "MODEL_ENFORCE" in msg
    assert f"role-packs/{role}" in msg
    assert "журнале PLAN.md" in msg
    assert "model_enforce_denied" in log_text(plugin_env)


def test_b2_hermes_block_not_shadowed_by_markers(plugin_env):
    """TC-J60-005: DENY стоит ДО разбора flow-маркеров — hermes-делегация
    с каноническим заголовком тоже блокируется."""
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget\n"
            "Задача dev. Исполнитель [hermes:dev].\n")
    res = delegate(goal)
    assert res is not None and res["action"] == "block"
    assert "MODEL_ENFORCE" in res["message"]


# ------------------------------------------ (в) без маркера → WARN, не блок

def test_c_no_marker_warns_but_passes(plugin_env):
    """TC-J60-006: боевой этап без маркера → WARN в лог, делегация идет."""
    assert delegate(SA_NO_MARKER) is None
    log = log_text(plugin_env)
    assert "model_enforce_warn" in log
    assert '"stages": ["sa"]' in log


@pytest.mark.parametrize("goal,stage", [
    ("Ревью архитектора пакета (arch-review) — жду заключение.", "architect"),
    ("Задача dev: собрать виджет по спеке.", "dev"),
    ("Сверка requirements и кейсов пакета.", "ba"),
])
def test_c2_every_stage_keyword_warns(plugin_env, goal, stage):
    """TC-J60-007: каждое ключевое слово этапа распознается (WARN-ветка)."""
    assert delegate(goal) is None
    assert f'"stages": ["{stage}"]' in log_text(plugin_env)


# ------------------------------------------------ (г) не-5.3 вызов → pass

@pytest.mark.parametrize("goal", [
    "devops: перезапустить стенд и собрать docker-логи.",
    "qa_cases: написать кейсы на виджет по чеклисту.",
    "docs_task: обновить README модуля платежей.",
    "chore_task: обновить lock-файл зависимостей.",  # Ф4-ключевые слова вне 5.3
])
def test_d_non_combat_call_passes(plugin_env, goal):
    """TC-J60-008: devops/qa/docs-вызовы без 5.3-ключевых слов — pass без
    маркера, лог без model_enforce-записей."""
    assert delegate(goal) is None
    assert "model_enforce" not in log_text(plugin_env)


def test_d2_flow245_guard_preserves_freedom(plugin_env):
    """TC-J60-010: маркер flow=2/4/5 гасит правило — bug_fix/chore/express
    задача dev без маркера исполнителя проходит (свобода выбора, ТЗ J60)."""
    for n in (2, 4, 5):
        goal = (f"flow: flow={n} role=dev repo=/tmp/proj scope=w-{n}\n"
                f"Задача dev по fix-{n}.\n")
        assert enforcer.model_enforce_gate(goal) is None
    assert "model_enforce" not in log_text(plugin_env)


# ------------------------------------------------------- (д) флаг off

def test_e_flag_off_disables_everything(plugin_env, monkeypatch):
    """TC-J60-010: FLOW_MODEL_ENFORCE=off → все кейсы pass (деградация).
    J60-ворота молчат; легальная делегация (DEV_PI) доходит до prepare —
    его мокаем (ворота prepare — не предмет этого теста)."""
    import subprocess

    def _fake(argv, **kw):
        return subprocess.CompletedProcess([], 0, "prepared: true\n", "")

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    monkeypatch.setenv("FLOW_MODEL_ENFORCE", "off")
    for goal in (SA_PI, ARCH_HERMES, SA_NO_MARKER, DEV_PI):
        assert delegate(goal) is None
    assert "model_enforce" not in log_text(plugin_env)


def test_e2_flag_values(plugin_env, monkeypatch):
    """TC-J60-011: 0/false/no выключают; пусто/прочее — ON (дефолт ON)."""
    for off in ("0", "false", "no", "off"):
        monkeypatch.setenv("FLOW_MODEL_ENFORCE", off)
        assert enforcer.model_enforce_enabled() is False
    for on in ("1", "on", "", "yes"):
        monkeypatch.setenv("FLOW_MODEL_ENFORCE", on)
        assert enforcer.model_enforce_enabled() is True
    monkeypatch.delenv("FLOW_MODEL_ENFORCE")
    assert enforcer.model_enforce_enabled() is True  # дефолт ON (Заказчик)


# ------------------------------------------------- (е/ж) юнит-детали

def test_f_stage_heuristics_unit():
    """TC-J60-012: эвристика — таблица ключевое слово → роль."""
    assert enforcer.stage_roles("СА и create_change") == ["sa"]
    assert enforcer.stage_roles("arch-review архитектора") == ["architect"]
    assert enforcer.stage_roles("dev_task по пакету") == ["dev"]
    assert enforcer.stage_roles("BA сводит requirements") == ["ba"]
    # «СА»/«BA» — только верхним регистром целым словом; смешанные/строчные
    # вхождения и латиница внутри слов не дают ложного боевого этапа.
    assert enforcer.stage_roles("сайт саНастройка, байка BAджик") == []
    assert enforcer.stage_roles("обычный docs-вызов без ключевых слов") == []


def test_g_executor_marker_unit():
    """TC-J60-013: парсер маркеров исполнителя."""
    assert enforcer.executor_markers("[pi:sa] и [HERMES:Dev]") == [
        ("pi", "sa"), ("hermes", "dev")]
    assert enforcer.executor_markers("без маркеров") == []
    # Не-5.3 роли маркером не признаются (code_reviewer и др. — вне регрупа).
    assert enforcer.executor_markers("[pi:code_reviewer]") == []


def test_h_warn_not_shadowing_later_gates(plugin_env):
    """TC-J60-014: WARN-делегация доходит до остальных ворот — после
    model_enforce_gate хук продолжает разбор flow-маркеров (bypass/MARKERS
    логика не сдвинута)."""
    # Боевой этап без маркера, strict без заголовка → прежний MARKERS_MISSING.
    import os
    os.environ["FLOW_ENFORCER_MODE"] = "strict"
    try:
        res = delegate(SA_NO_MARKER)
    finally:
        os.environ["FLOW_ENFORCER_MODE"] = "permissive"
    assert res is not None and "MARKERS_MISSING" in res["message"]
    assert "model_enforce_warn" in log_text(plugin_env)
