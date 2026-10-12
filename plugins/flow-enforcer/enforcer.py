# -*- coding: utf-8 -*-
"""flow-enforcer — ядро pre_tool_call-энфорсера делегаций (J43).

Перехватывает только tool_name == 'delegate_task'. Из args.goal/args.context
парсит маркеры конвейера:

  1. Заголовок (канонический формат, см. templates/task_delegation.md):
         flow: role=<роль> repo=<путь> change=<id>
  2. Одиночные маркеры: 'role: X', 'repo: P', 'change: C' в тех же строках.

Без маркеров решение по режиму FLOW_ENFORCER_MODE:
  - 'strict'     → block MARKERS_MISSING;
  - 'permissive' (дефолт) → пропуск + запись в лог (аудит-след).

Bypass: дословная строка 'flow: bypass --by customer' в goal — явное
распоряжение Заказчика: пропуск + запись в incident-файл.

Валидация: subprocess flowctl prepare --dry-run (--dry-run, чтобы энфорсер
НЕ создавал reservation/zone-резерв: это сделает штатный prepare ПМ перед
запуском; энфорсер только проверяет решение ворот — ALLOW/DENY). Код 0 →
пропуск; ненулевой → block с выводом (там machine-коды: PLAN_RELEASE_MISSING,
ZONE_*, REQUIREMENTS_NOT_APPROVED, ...).

Fail-closed: любое исключение в хуке → block
'flow-enforcer internal error: ... (fail-closed)'. Плюс платформенный
fail-closed на таймаут (hooks.md §pre_tool_call).

Env:
  FLOW_ENFORCER_MODE       strict | permissive (дефолт permissive)
  FLOW_ENFORCER_STATE_DIR  каталог логов (дефолт ~/.hermes/state)
  AI_FACTORY_HOME          путь к фабрике (дефолт ~/ai-factory)
  FLOW_ENFORCER_REGISTRY   путь к active_sessions.json (проброс --registry)
  FLOW_ENFORCER_FLOW       номер флоу (дефолт 1)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TRIGGER_TOOL = "delegate_task"
BYPASS_MARKER = "flow: bypass --by customer"
HEADER_RE = re.compile(
    r"flow:\s*role=(?P<role>\S+)\s+repo=(?P<repo>\S+)\s+change=(?P<change>\S+)")
SINGLE_RE = {
    "role": re.compile(r"\brole:\s*([^\s,;]+)"),
    "repo": re.compile(r"\brepo:\s*([^\s,;]+)"),
    "change": re.compile(r"\bchange:\s*([^\s,;]+)"),
    "task": re.compile(r"\btask:\s*([^\s,;]+)"),  # опциональный (dev_task)
}

# Действие по роли: этапы STAGE_TABLE Флоу 1 (flow_transition.py).
ROLE_ACTIONS = {
    "dev": "dev_task",
    "sa": "create_change",
    "code_reviewer": "code_review",
    "qa_automation": "qa_automation",
    "qa_checklist": "qa_checklist",
    "qa_author": "qa_cases",
    "qa_case_author": "qa_cases",
    "qa_case_reviewer": "qa_review",
    "qa_impact_analyst": "qa_impact_analysis",
    "design_validator": "design_validation",
    "ui_designer": "design_task",
}
DEFAULT_ACTION = "dev_task"

SLOW_PREPARE_SECONDS = 10.0


def state_dir() -> Path:
    return Path(os.environ.get(
        "FLOW_ENFORCER_STATE_DIR", str(Path.home() / ".hermes" / "state")))


def factory_home() -> Path:
    return Path(os.environ.get(
        "AI_FACTORY_HOME", str(Path.home() / "ai-factory"))).expanduser()


def mode() -> str:
    return os.environ.get("FLOW_ENFORCER_MODE", "permissive").strip().lower()


def _marker_texts(args: dict) -> list[str]:
    """Строки, в которых ищутся маркеры: goal + context (args delegate_task)."""
    texts = []
    for key in ("goal", "context"):
        v = (args or {}).get(key)
        if isinstance(v, str) and v.strip():
            texts.append(v)
        elif isinstance(v, dict):
            texts.extend(str(x) for x in v.values() if isinstance(x, str))
    return texts


def parse_markers(args: dict) -> dict | None:
    """Достает role/repo/change: сначала канонический заголовок, затем
    одиночные маркеры 'role:/repo:/change:'; task: — опциональный маркер
    (dev_task уровня задачи). None — если обязательных маркеров нет."""
    texts = _marker_texts(args)
    role = repo = change = task = None
    for text in texts:
        m = HEADER_RE.search(text)
        if m:
            role, repo, change = m.group("role"), m.group("repo"), m.group("change")
            break
    found = {"role": role, "repo": repo, "change": change, "task": task}
    for text in texts:
        for key, rx in SINGLE_RE.items():
            if not found.get(key):
                m = rx.search(text)
                if m:
                    found[key] = m.group(1).strip("<>")
        if all(found.values()):
            break
    role, repo, change = found["role"], found["repo"], found["change"]
    if role and repo and change:
        return {"role": role, "repo": repo, "change": change,
                "task": found["task"]}
    return None


def has_bypass(goal: str) -> bool:
    return BYPASS_MARKER in (goal or "")


def _append_log(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": datetime.now(timezone.utc).isoformat(
            timespec="seconds"), **payload}
        with path.open("a", encoding="utf-8") as f:
            f.write(__import__("json").dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass  # лог — best-effort; на отказ лога вердикт не меняется


def log_event(payload: dict) -> None:
    _append_log(state_dir() / "flow-enforcer.log", payload)


def log_bypass(task_id: str, goal: str) -> None:
    _append_log(state_dir() / "flow-enforcer-bypass.log", {
        "task_id": task_id, "goal_head": (goal or "")[:200],
        "kind": "bypass --by customer",
    })


def prepare_command(markers: dict) -> list[str]:
    """argv проверки: flowctl prepare --dry-run (без side effects)."""
    role = markers["role"]
    repo = markers["repo"]
    action = ROLE_ACTIONS.get(role, DEFAULT_ACTION)
    flow = os.environ.get("FLOW_ENFORCER_FLOW", "1")
    project = os.environ.get("FLOW_ENFORCER_PROJECT") or Path(repo).name
    argv = [
        sys.executable, str(factory_home() / "scripts" / "flowctl.py"),
        "prepare", "--dry-run",
        "--role", role, "--repo", repo, "--change", markers["change"],
        "--action", action,
        "--project", project, "--flow", flow,
        "--owner-pm", "flow-enforcer",
    ]
    if markers.get("task"):
        argv += ["--task", markers["task"]]
    registry = os.environ.get("FLOW_ENFORCER_REGISTRY")
    if registry:
        argv += ["--registry", registry]
    return argv


def run_prepare(markers: dict) -> tuple[int, str, float]:
    """Прогон flowctl prepare --dry-run: (returncode, вывод, длительность)."""
    argv = prepare_command(markers)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc = 124
        out = f"flowctl prepare timeout: {exc}"
    duration = time.monotonic() - t0
    if duration > SLOW_PREPARE_SECONDS:
        log_event({"event": "slow_prepare", "level": "WARNING",
                   "duration_s": round(duration, 2), "argv": argv[2:]})
    return rc, out, duration


def flow_enforce(tool_name: str, args: dict, task_id: str = "",
                 **kwargs):  # noqa: ANN201 — None или directive-dict
    """pre_tool_call-хук: валидирует delegate_task против ворот конвейера."""
    try:
        if tool_name != TRIGGER_TOOL:
            return None  # не делегация — без директивы

        args = args or {}
        goal = args.get("goal") if isinstance(args.get("goal"), str) else ""
        log_event({"event": "delegate_task_seen", "task_id": task_id})

        if has_bypass(goal):
            log_bypass(task_id, goal)
            log_event({"event": "bypass", "task_id": task_id})
            return None

        markers = parse_markers(args)
        if markers is None:
            if mode() == "strict":
                return {"action": "block", "message": (
                    "FLOW-ENFORCER [MARKERS_MISSING]: делегация без маркеров "
                    "конвейера. Добавь в goal заголовок "
                    "'flow: role=<роль> repo=<путь> change=<id>' (см. "
                    "templates/task_delegation.md) или пройди flowctl prepare. "
                    "Bypass — только 'flow: bypass --by customer'.")}
            log_event({"event": "markers_missing_permissive",
                       "task_id": task_id})
            return None

        rc, out, duration = run_prepare(markers)
        log_event({"event": "prepare_result", "task_id": task_id,
                   "rc": rc, "duration_s": round(duration, 2),
                   "role": markers["role"], "repo": markers["repo"],
                   "change": markers["change"]})
        if rc == 0:
            return None  # ALLOW — без директивы
        return {"action": "block", "message": (
            f"FLOW-ENFORCER: flowctl prepare отклонил делегацию "
            f"(exit {rc}, role={markers['role']}, repo={markers['repo']}, "
            f"change={markers['change']}). Вывод ворот:\n"
            f"{out.strip()[-2000:]}")}
    except Exception as e:  # noqa: BLE001 — сознательный fail-closed (J43)
        return {"action": "block", "message": (
            f"flow-enforcer internal error: {e} (fail-closed)")}


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", flow_enforce)
