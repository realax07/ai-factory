#!/usr/bin/env python3
"""flow_transition.py — проверка действий по снимку FlowSnapshot (поставка 03).

Чистая функция check_action(snapshot, action) -> Decision и CLI check/next.
Правила Флоу 1–5 — таблица этапов (design D3): этап = требуемые факты + роль
+ gates; check_action сверяет факты snapshot с этапом действия. Отсутствующий
критерий правила = UNKNOWN (честно), а не DENY (ложный запрет); UNKNOWN никогда
не разрешает исполнение. DENY перечисляет ВСЕ блокирующие причины.

Provenance-переходы (accept_review/merge): до поставки 05 идентичность
diff/SHA/даты не проверяема — явный UNKNOWN с STALE_EVIDENCE (compatibility
mode, ТЗ 03 п.8, design D4, спека Requirement «Provenance review»).

Shadow mode (срез 1): решение вычисляется честно, но ничего не блокирует,
не запускает агентов и не пишет ни в репозиторий, ни в реестр (спека
deterministic-flow, Requirement «Режим shadow»; контракт §14).

Парсеры flow_check (closed_dev_tasks, approved_review_tasks, parse_verdict)
переиспользуются импортом, не дублируются (ТЗ 03; design D1).

Usage:
    python3 scripts/flow_transition.py check --repo PATH --project ID --flow N \
        --change ID --action ACTION --role ROLE [--task ID] [--approval-ref S]
        [--json] [--registry PATH]
    python3 scripts/flow_transition.py next --repo PATH --project ID --flow N \
        --change ID [--json] [--registry PATH]

Exit codes: 0 — ALLOW; 1 — DENY; 2 — UNKNOWN или ошибка входа.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import flow_check
import flow_state

DECISION_SCHEMA = "flow-decision/1"

ALLOW = "ALLOW"
DENY = "DENY"
UNKNOWN = "UNKNOWN"

# Стабильные коды причин (контракт §9; FR-4).
MISSING_INPUT = "MISSING_INPUT"
INVALID_GATE = "INVALID_GATE"
HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
WRONG_ROLE = "WRONG_ROLE"
ZONE_CONFLICT = "ZONE_CONFLICT"
STALE_EVIDENCE = "STALE_EVIDENCE"
AMBIGUOUS_STATE = "AMBIGUOUS_STATE"
STALE_SNAPSHOT = "STALE_SNAPSHOT"
EXTERNAL_ENFORCEMENT_UNKNOWN = "EXTERNAL_ENFORCEMENT_UNKNOWN"
REASON_CODES = (
    MISSING_INPUT, INVALID_GATE, HUMAN_APPROVAL_REQUIRED, WRONG_ROLE,
    ZONE_CONFLICT, STALE_EVIDENCE, AMBIGUOUS_STATE, STALE_SNAPSHOT,
    EXTERNAL_ENFORCEMENT_UNKNOWN,
)

# Защищенные пути конвейера (Флоу 4, J3 pm_bounds_check).
PROTECTED_PATHS = ("openspec/", "contracts/", "AGENTS.md", "agents/README.md")

# Формат зависимостей в строке задачи tasks.md: «(после 1.1, 1.2)» / «depends: 1.1».
DEPS_RE = re.compile(
    r"(?:после|depends:|зависимости:)\s*"
    r"(\d+(?:\.\d+)*(?:\s*,\s*\d+(?:\.\d+)*)*)",
    re.IGNORECASE,
)
TASK_LINE_RE = re.compile(r"^[-*]\s*\[( |x)\]\s*(\d+(?:\.\d+)*)\s*(.*)$", re.M)
PARALLEL_MARKER = "[P]"


# ---------------------------------------------------------------- модели


@dataclass
class Finding:
    code: str
    detail: str
    unknown: bool = False  # True → критерий не проверяем (UNKNOWN), False → DENY


@dataclass
class ActionRequest:
    """Запрос действия (контракт §6; срез 1 — дополнительные опциональные поля)."""

    actor_role: str
    requested_action: str
    task_id: str | None = None
    approval_ref: object = None       # str (ссылка/цитата) | dict customer_decision v1
    expected_snapshot_digest: str | None = None
    # параллель/зависимости ([P], AGENTS.md п.10):
    task_parallel: bool | None = None
    # подтверждение маркера [P] в tasks.md (R5): CLI ставит после разбора
    # tasks.md; API-вызывающий — после собственной проверки маркера.
    parallel_confirmed: bool | None = None
    task_dependencies: tuple = ()
    dependency_evidence: dict | None = None  # {dep: {task_closed, review_approved}}
    # Флоу 2: фиксирует ввод нового поведения/API (эскалация):
    spec_delta: bool | None = None
    # Флоу 3: ссылка на инцидент/причину:
    incident_ref: str | None = None
    # Флоу 4: затрагиваемые пути и [pipeline]-маркер:
    paths: tuple = ()
    pipeline_marker: bool | None = None
    rules_change: bool | None = None
    # Флоу 5: подтверждение условий экспресс-режима (BACKLOG/README):
    small_change: bool | None = None

    def to_dict(self) -> dict:
        return {
            "actor_role": self.actor_role,
            "requested_action": self.requested_action,
            "task_id": self.task_id,
            "approval_ref": self.approval_ref
            if isinstance(self.approval_ref, (str, type(None))) else "<decision>",
            "task_parallel": self.task_parallel,
            "parallel_confirmed": self.parallel_confirmed,
            "task_dependencies": list(self.task_dependencies),
            "dependency_evidence": {
                str(k): dict(v) if isinstance(v, dict) else v
                for k, v in (self.dependency_evidence or {}).items()
            } or None,
            "expected_snapshot_digest": self.expected_snapshot_digest,
            "spec_delta": self.spec_delta,
            "incident_ref": self.incident_ref,
            "paths": list(self.paths),
            "pipeline_marker": self.pipeline_marker,
            "rules_change": self.rules_change,
            "small_change": self.small_change,
        }


@dataclass
class Decision:
    allowed: bool
    status: str                        # ALLOW | DENY | UNKNOWN
    action: str
    scope: dict
    actor_role: str
    snapshot_digest: str
    requirements_checked: list = field(default_factory=list)
    blocking_reasons: list = field(default_factory=list)
    details: list = field(default_factory=list)
    required_gates: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    next_candidates: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": DECISION_SCHEMA,
            "allowed": self.allowed,
            "status": self.status,
            "action": self.action,
            "scope": self.scope,
            "actor_role": self.actor_role,
            "snapshot_digest": self.snapshot_digest,
            "requirements_checked": self.requirements_checked,
            "blocking_reasons": self.blocking_reasons,
            "details": self.details,
            "required_gates": self.required_gates,
            "evidence_refs": self.evidence_refs,
            "next_candidates": self.next_candidates,
        }


# ------------------------------------------------------------ доступ к фактам


def _fact(snapshot: dict, key: str, ctx: dict) -> dict | None:
    """Первый факт с ключом; источник фиксируется как evidence."""
    ctx["checked"].add(key)
    for f in snapshot.get("facts", []):
        if f.get("key") == key:
            src = f.get("source")
            if src:
                ctx["evidence"].add(str(src))
            return f
    return None


def _fact_ready(snapshot: dict, key: str, ctx: dict) -> tuple[object, str, list]:
    """(value, status, findings). missing → MISSING_INPUT; unknown/invalid → UNKNOWN."""
    f = _fact(snapshot, key, ctx)
    if f is None or f.get("status") == "missing":
        return None, "missing", [
            Finding(MISSING_INPUT, f"факт «{key}»: отсутствует в снимке — "
                    f"артефакт не найден (источник: inspect, поставка 02)")]
    status = f.get("status", "unknown")
    if status in ("unknown", "invalid"):
        return f.get("value"), status, [
            Finding(MISSING_INPUT, f"факт «{key}»: источник нечитаем/непригоден "
                    f"(status={status}) — проверка невозможна, UNKNOWN честнее "
                    f"предположения (контракт §2, §9)", True)]
    return f.get("value"), status, []


def _require_task(snapshot: dict, action: ActionRequest, ctx: dict,
                  *, closed_denied: bool = True) -> list:
    """Задача tasks.md: существует и открыта (для действий по конкретной задаче)."""
    if not action.task_id:
        return [Finding(MISSING_INPUT,
                        "не указан task_id — действие уровня задачи требует задачу "
                        "tasks.md (scope, контракт §3)")]
    key = f"task.{action.task_id}.status"
    value, status, out = _fact_ready(snapshot, key, ctx)
    if status != "ready":
        out.extend([
            Finding(MISSING_INPUT, f"задача {action.task_id}: факт отсутствует в "
                    f"снимке — пересобери inspect с --task {action.task_id} "
                    f"(openspec/changes/<id>/tasks.md)")])
        return out
    if value == "not_found":
        out.append(Finding(MISSING_INPUT,
                           f"задача {action.task_id} не найдена в "
                           f"openspec/changes/<id>/tasks.md (контракт §3)"))
    elif value == "closed" and closed_denied:
        out.append(Finding(INVALID_GATE,
                           f"задача {action.task_id} уже закрыта — повторный "
                           f"проход этапа не разрешен (AGENTS.md, история не "
                           f"переписывается)"))
    return out


# ------------------------------------------------------- общие проверки этапов


def _requirements_approved(snapshot: dict, ctx: dict) -> list:
    value, status, out = _fact_ready(snapshot, "requirements.status", ctx)
    if status != "ready":
        return out
    if value != "approved":
        out.append(Finding(
            INVALID_GATE,
            f"requirements.md не УТВЕРЖДЕН (status={value}) — этап "
            f"approve_requirements пропущен (ТЗ 03 п.2; evidence: requirements.md)"))
    return out


def _arch_review_done(snapshot: dict, ctx: dict) -> list:
    """Этап architecture review: change-пакет + sdd.md + дельты (контракт 2)."""
    out: list = []
    pkg_value, pkg_status, out0 = _fact_ready(snapshot, "change.package", ctx)
    out.extend(out0)
    if pkg_status == "ready":
        if not isinstance(pkg_value, dict) or not pkg_value.get("present"):
            out.append(Finding(INVALID_GATE,
                               "change-пакет openspec/changes/<id>/ не создан — "
                               "этап create_change пропущен (контракт 2)"))
        else:
            missing_files = pkg_value.get("missing_files") or []
            if missing_files:
                out.append(Finding(
                    MISSING_INPUT,
                    f"change-пакет неполон: {', '.join(missing_files)} — "
                    f"architecture review невозможен (контракт 2; "
                    f"evidence: openspec/changes/<id>/)", True))
    else:
        out.append(Finding(
            INVALID_GATE,
            "change-пакет openspec/changes/<id>/ отсутствует — этап create_change "
            "пропущен (контракт 2; ТЗ 03 п.2)"))
    deltas, d_status, out1 = _fact_ready(snapshot, "change.spec_deltas", ctx)
    out.extend(out1)
    if d_status == "ready" and not deltas:
        out.append(Finding(INVALID_GATE,
                           "нет дельт specs/*/spec.md в change-пакете (контракт 2)"))
    sdd_value, sdd_status, out2 = _fact_ready(snapshot, "sdd.present", ctx)
    out.extend(out2)
    if sdd_status == "ready" and sdd_value is not True:
        out.append(Finding(INVALID_GATE,
                           "sdd.md отсутствует — активный change требует SDD "
                           "(контракт 2; evidence: sdd.md)"))
    if out0 or out2 or (d_status != "ready"):
        out.append(Finding(
            INVALID_GATE,
            "пропущен этап architecture review: нет complete-набора "
            "(change-пакет + sdd.md + дельты) (ТЗ 03 п.2; evidence: "
            "openspec/changes/<id>/, sdd.md)"))
    return out


def _approvals_for_task(snapshot: dict, action: ActionRequest, ctx: dict) -> list:
    """Есть ли approve-вердикт ревью для задачи (J10)."""
    value, status, out = _fact_ready(snapshot, "reviews.approved", ctx)
    if status != "ready":
        out.extend([
            Finding(MISSING_INPUT,
                    f"каталог code-reviews/{snapshot.get('scope', {}).get('change', '')}/ "
                    f"пуст или нечитаем — нет approve-вердикта (J10)")])
        return out
    approved = value.get("approved") if isinstance(value, dict) else None
    covered = False
    if approved and action.task_id:
        for name in approved:
            nums = re.findall(r"\d+(?:\.\d+)*", str(name))
            if action.task_id in nums:
                covered = True
                break
    if not covered:
        out.append(Finding(
            INVALID_GATE,
            f"нет approve-вердикта review для задачи {action.task_id} "
            f"(J10; evidence: code-reviews/<change-id>/review-*.md, "
            f"approved={approved})"))
    return out


def _deps_findings(action: ActionRequest, ctx: dict) -> list:
    """Зависимости задачи (AGENTS.md п.10; ТЗ 03 п.1).

    Статусы зависимостей — evidence от flow_check (closed_dev_tasks +
    approved_review_tasks: чекбокс [x] + approve-вердикт, J10). Без evidence —
    UNKNOWN (критерий не собран), не молчаливое разрешение.
    """
    deps = action.task_dependencies or ()
    if not deps:
        return []
    ctx["checked"].add("task.dependencies")
    out: list = []
    if action.dependency_evidence is None:
        return [Finding(
            MISSING_INPUT,
            f"зависимости {', '.join(deps)} не проверяемы по снимку: нет evidence "
            f"(closed_dev_tasks + approved_review_tasks) — UNKNOWN (ТЗ 03 п.1; "
            f"AGENTS.md п.10)", True)]
    for d in deps:
        ev = (action.dependency_evidence or {}).get(d)
        if ev is None:
            out.append(Finding(
                MISSING_INPUT,
                f"зависимость {d}: нет evidence о состоянии (ТЗ 03 п.1)", True))
            continue
        if not ev.get("task_closed"):
            out.append(Finding(
                INVALID_GATE,
                f"зависимая задача {d} ждёт merge предшественницы (AGENTS.md п.10: "
                f"задачи с зависимостями — строго последовательно; "
                f"evidence: openspec/changes/<id>/tasks.md)"))
        elif not ev.get("review_approved"):
            out.append(Finding(
                INVALID_GATE,
                f"зависимость {d} закрыта без code-review approve (J10; "
                f"evidence: code-reviews/<change-id>/review-*.md)"))
    return out


def _approval_finding(action: ActionRequest, scope: dict, stage_name: str) -> Finding | None:
    """Этапные ворота Заказчика (ТЗ 03 п.7; контракт §10; design D5).

    Срез 1: строковый approval_ref (ссылка на фиксацию в PLAN/BACKLOG/чат-логе)
    принимается как есть; строгая верификация формата — follow-up. Словарь
    проверяется по customer_decision v1: grants и привязка к scope/фазе.

    Упрощение среза 1 (review-001 R7): «фаза» привязывается к номеру флоу
    (bindings: phase == scope.flow). Фазы ВНУТРИ процесса одного флоу (например
    фаза А/Б релиза одного change) не различаются — расширение scope_ref
    (фаза ≠ flow) — follow-up; зафиксировано в design D5.
    """
    ref = action.approval_ref
    if not ref:
        return Finding(
            HUMAN_APPROVAL_REQUIRED,
            f"действие «{stage_name}» требует зафиксированного решения Заказчика "
            f"(дословная фиксация; «ПМ считает согласованным» решением не является; "
            f"формат: contracts/flow_control_contract.md §10; AGENTS.md «Этапные "
            f"ворота Заказчика»)")
    if isinstance(ref, str):
        return None
    if isinstance(ref, dict):
        if not ref.get("decision_id") or not isinstance(ref.get("grants"), list):
            return Finding(
                MISSING_INPUT,
                "approval_ref: словарь не соответствует customer_decision v1 — "
                "нет decision_id/grants (контракт §10)")
        if action.requested_action not in ref["grants"]:
            return Finding(
                HUMAN_APPROVAL_REQUIRED,
                f"решение {ref['decision_id']} не покрывает действие "
                f"«{action.requested_action}» (grants: "
                f"{', '.join(map(str, ref['grants']))}; контракт §10)")
        bindings = (
            ("project", scope.get("project")),
            ("change_id", scope.get("change")),
            ("phase", scope.get("flow")),
        )
        for key, expected in bindings:
            declared = ref.get(key)
            if declared is not None and str(declared) != str(expected):
                return Finding(
                    HUMAN_APPROVAL_REQUIRED,
                    f"решение {ref['decision_id']} относится к другой фазе/scope "
                    f"({key}={declared}, действие требует {expected}) — разрешение "
                    f"не переносится после закрытия фазы (ТЗ 03 п.7; спека "
                    f"«Этапные ворота Заказчика»)")
        return None
    return Finding(MISSING_INPUT,
                   "approval_ref: неподдерживаемый тип (ожидается str | dict)")


# ------------------------------------------------------------ проверки этапов
# Каждая функция: (snapshot, action, ctx, flow) -> list[Finding].


def check_approve_requirements(snapshot, action, ctx, flow):
    out: list = []
    value, status, out0 = _fact_ready(snapshot, "requirements.status", ctx)
    out.extend(out0)
    if status == "ready" and value not in ("draft", "approved"):
        out.append(Finding(AMBIGUOUS_STATE,
                           f"requirements.status={value!r}: неожиданное значение "
                           f"(ожидается draft|approved) — источник: requirements.md",
                           True))
    return out


def check_create_change(snapshot, action, ctx, flow):
    return list(_requirements_approved(snapshot, ctx))


def check_needs_arch(snapshot, action, ctx, flow):
    out = list(_requirements_approved(snapshot, ctx))
    out.extend(_arch_review_done(snapshot, ctx))
    return out


def check_dev_task(snapshot, action, ctx, flow):
    # Транзитивный порядок Флоу 1 (ТЗ 03 п.2 дословно): «утверждённые требования
    # → change/SDD → architecture review → dev task». dev_task проверяет ВСЕХ
    # предшественников, а не только ближайшего этапа — иначе цепочка рвется
    # (review-001 R4: dev_task при draft requirements молчаливо ALLOW).
    out = list(_requirements_approved(snapshot, ctx))
    out.extend(_arch_review_done(snapshot, ctx))
    out.extend(_require_task(snapshot, action, ctx))
    out.extend(_deps_findings(action, ctx))
    if action.task_parallel:
        ctx["checked"].add("zones.admit_session")
        # Зоны проверяет admit_session (поставка 04): здесь — обязательная пометка
        # в required_gates, не блокировка (контракт §7 «Параллель и зоны»).
        ctx.setdefault("extra_gates", []).append(
            "admit_session: непересекающиеся зоны записи (поставка 04; AGENTS.md п.10–11)")
        # ТЗ 03 п.1: параллельная задача допускается только при [P] в tasks.md
        # (review-001 R5). Снимок среза 1 не несет факт маркера — подтверждение
        # должно прийти извне (CLI-парсер tasks.md: parallel_confirmed); флаг
        # «на веру» не принимается — без подтверждения UNKNOWN (D3), не ALLOW.
        if action.parallel_confirmed is not True:
            ctx["checked"].add("task.parallel_marker")
            out.append(Finding(
                MISSING_INPUT,
                "task_parallel=True без подтвержденного маркера [P] в tasks.md — "
                "параллельная задача допускается только при [P] (ТЗ 03 п.1); факт "
                "маркера отсутствует в снимке (координация с поставкой 02) → "
                "UNKNOWN честнее доверия флагу (контракт §2, §9; design D3)",
                True))
    return out


def check_code_review(snapshot, action, ctx, flow):
    if flow == 1:
        return list(_require_task(snapshot, action, ctx))
    # chore/bug PR: ревью по диффу, задача tasks.md не обязательна.
    ctx["checked"].add("diff (внешний, PR)")
    return []


def _hotfix_debt_findings(snapshot, action, ctx, flow) -> list:
    """Хотфикс-долг Флоу 3 (review-001 R6; ТЗ 03 п.4; контракт §7 Флоу 3).

    Пока PR-цикл хотфикса не закрыт, ВСЕ последующие действия этого scope
    получают STALE_EVIDENCE-пометку незакрытого долга. Факт `hotfix.pr_pending`
    в срезе 1 не строится (координация с поставкой 02), поэтому на срезе 1 —
    честный fallback: пометка долга на каждый post-emergency шаг accept_review/
    merge_task Флоу 3 (по D3 — пометка/UNKNOWN, не молчаливое ALLOW).
    """
    if flow != 3:
        return []
    ctx["checked"].add("hotfix.pr_pending")
    ctx.setdefault("extra_gates", []).append(
        "незакрытый долг хотфикса: PR-цикл (review + pr_validate) после "
        "emergency_stabilize обязателен до завершения (контракт §7 Флоу 3; "
        "ТЗ 03 п.4)")
    return [Finding(
        STALE_EVIDENCE,
        "незакрытый долг хотфикса: PR-цикл после emergency_stabilize не "
        "подтвержден закрытым (факт hotfix.pr_pending отсутствует в снимке "
        "среза 1, координация с поставкой 02) — хотфикс не «завершен» merge "
        "без последующего PR (ТЗ 03 п.4; контракт §7 Флоу 3)",
        True)]


def check_accept_review(snapshot, action, ctx, flow):
    """Provenance-переход: compatibility mode → UNKNOWN (ТЗ 03 п.8; D4)."""
    out = _hotfix_debt_findings(snapshot, action, ctx, flow) if flow == 3 else []
    if action.task_id:
        out.extend(_approvals_for_task(snapshot, action, ctx))
    out.append(Finding(
        STALE_EVIDENCE,
        "provenance (task/change/SHA/diff, независимость автора) не проверяема "
        "до поставки 05 — accept_review в compatibility mode дает UNKNOWN "
        "(ТЗ 03 п.8; спека «Provenance review»; design D4)", True))
    return out


def check_merge_task(snapshot, action, ctx, flow):
    out: list = []
    if action.actor_role == "pm":
        out.append(Finding(WRONG_ROLE,
                           "ПМ не делает merge в продуктовых репозиториях (J9; "
                           "pm_bounds_check --product-commits; merge — через "
                           "dev-lead)"))
    out.extend(_approvals_for_task(snapshot, action, ctx))
    out.extend(_hotfix_debt_findings(snapshot, action, ctx, flow))
    out.append(Finding(
        STALE_EVIDENCE,
        "approve-вердикт не привязан к SHA/diff/дате ≤ коммита — provenance "
        "не проверяема до поставки 05, compatibility UNKNOWN (ТЗ 03 п.8; J10)",
        True))
    out.append(Finding(
        EXTERNAL_ENFORCEMENT_UNKNOWN,
        "branch protection на main не подтверждена локальным прогоном — пометка "
        "не повышает статус разрешения (FR-7; контракт §12)", True))
    return out


def _test_model_sub(snapshot, ctx, sub, deny_detail):
    value, status, out = _fact_ready(snapshot, "test_model.present", ctx)
    if status == "ready":
        if not isinstance(value, dict) or not value.get(sub):
            out.append(Finding(INVALID_GATE, deny_detail))
    return out


def check_qa_checklist(snapshot, action, ctx, flow):
    out: list = []
    deltas, d_status, out0 = _fact_ready(snapshot, "change.spec_deltas", ctx)
    out.extend(out0)
    specs_value, specs_status, out1 = _fact_ready(snapshot, "specs.present", ctx)
    out.extend(out1)
    has_source = (
        (d_status == "ready" and deltas)
        or (specs_status == "ready" and isinstance(specs_value, dict)
            and specs_value.get("count", 0) > 0)
    )
    if not has_source and not (out0 or out1):
        out.append(Finding(INVALID_GATE,
                           "чеклист требует спеку/дельты — источника нет "
                           "(контракт 3/4; evidence: openspec/specs/, "
                           "openspec/changes/<id>/specs/)"))
    return out


def check_qa_cases(snapshot, action, ctx, flow):
    return list(_test_model_sub(
        snapshot, ctx, "checklists",
        "кейсы требуют чеклист — test-model/checklists/ пуст (контракт 4)"))


def check_qa_review(snapshot, action, ctx, flow):
    return list(_test_model_sub(
        snapshot, ctx, "new",
        "нет кейсов в test-model/new/ — ревьюить нечего (контракт 4/5)"))


def check_qa_automation(snapshot, action, ctx, flow):
    return list(_test_model_sub(
        snapshot, ctx, "approved",
        "автотесты требуют approved-кейсы — test-model/approved/ пуст "
        "(контракт 5/6)"))


def check_archive_change(snapshot, action, ctx, flow):
    out: list = []
    value, status, out0 = _fact_ready(snapshot, "change.tasks", ctx)
    out.extend(out0)
    if status == "ready":
        open_n = value.get("open") if isinstance(value, dict) else None
        if open_n is None:
            out.append(Finding(AMBIGUOUS_STATE,
                               f"change.tasks={value!r}: неожиданный формат",
                               True))
        elif open_n > 0:
            out.append(Finding(
                INVALID_GATE,
                f"не все задачи закрыты (open={open_n}) — архивация требует [x] "
                f"по всем задачам (контракт 7; evidence: "
                f"openspec/changes/<id>/tasks.md)"))
    out.extend(_test_model_sub(
        snapshot, ctx, "approved",
        "QA-контур не завершен: нет approved-кейсов — QA не сводится к одной "
        "булевой переменной (ТЗ 03 п.2; контракты 3–6)"))
    if not action.approval_ref:
        out.append(Finding(
            MISSING_INPUT,
            "явное разрешение ПМ на архивацию не передано в action.approval_ref "
            "(контракт 7) — проверка невозможна, UNKNOWN", True))
    return out


def check_release(snapshot, action, ctx, flow):
    out: list = []
    value, status, out0 = _fact_ready(snapshot, "change.tasks", ctx)
    out.extend(out0)
    if status == "ready" and isinstance(value, dict) and value.get("open", 1) > 0:
        out.append(Finding(
            INVALID_GATE,
            f"архивация не завершена (open={value.get('open')}) — релиз требует "
            f"закрытого change (ТЗ 03 п.2: release gate после archive)"))
    # Транзитивность Флоу 1 (review-001 R4): release различает «все чекбоксы [x]»
    # и завершенный archive_change (дельты слиты, openspec validate). Факт
    # архивации (change.archived) в срезе 1 не строится — без него UNKNOWN,
    # не молчаливое ALLOW (D3: отсутствие критерия = UNKNOWN).
    ctx["checked"].add("change.archived")
    out.append(Finding(
        MISSING_INPUT,
        "факт завершенного archive_change (дельты слиты в openspec/specs/, "
        "openspec validate --strict пройден) отсутствует в снимке среза 1 — "
        "закрытые чекбоксы tasks.md не равны архивации; проверка невозможна → "
        "UNKNOWN (ТЗ 03 п.2; design D3; координация с поставкой 02)",
        True))
    out.append(Finding(
        EXTERNAL_ENFORCEMENT_UNKNOWN,
        "деплой-полномочия вне локальной проверки — branch protection/окружение "
        "не подтверждены (FR-7; контракт §12)", True))
    return out


def check_bug_fix(snapshot, action, ctx, flow):
    out: list = []
    value, status, out0 = _fact_ready(snapshot, "test_model.present", ctx)
    out.extend(out0)
    if status == "ready" and isinstance(value, dict) and not value.get("bugs"):
        out.append(Finding(
            MISSING_INPUT,
            f"баг-репорт test-model/bugs/{snapshot.get('scope', {}).get('change', '')}.md "
            f"отсутствует — Флоу 2 требует BUG-NNN репорт (ТЗ 03 п.3)"))
    specs_value, specs_status, out1 = _fact_ready(snapshot, "specs.present", ctx)
    out.extend(out1)
    if specs_status != "ready" or (
        isinstance(specs_value, dict) and specs_value.get("count", 0) == 0
    ):
        out.append(Finding(
            MISSING_INPUT,
            "существующая спека, описывающая ожидаемое поведение, обязательна "
            "(ТЗ 03 п.3; evidence: openspec/specs/)"))
    if action.spec_delta:
        out.append(Finding(
            INVALID_GATE,
            "Флоу 2 запрещен: фикс вводит новое ожидаемое поведение/API (дельта "
            "спеки) — эскалация на Флоу 1 / решение Заказчика (ТЗ 03 п.3; "
            "контракт §7 Флоу 2)"))
        ctx.setdefault("override_next", []).extend([
            {"action": "create_change", "task": None, "actor_role": "sa"},
            {"action": "escalate_to_customer", "task": None, "actor_role": "pm"},
        ])
    return out


def check_emergency_stabilize(snapshot, action, ctx, flow):
    out: list = []
    if not action.incident_ref:
        out.append(Finding(
            MISSING_INPUT,
            "причина инцидента не зафиксирована (action.incident_ref) — "
            "emergency-действие обязано фиксировать причину (ТЗ 03 п.4)", True))
    ctx.setdefault("extra_gates", []).append(
        "обязательный последующий PR-цикл: review + pr_validate (контракт §7 "
        "Флоу 3; хотфикс без PR не считается завершенным)")
    return out


def check_deploy_rollback(snapshot, action, ctx, flow):
    """Полномочия проверяет _approval_finding (stage.approval=True)."""
    return [Finding(
        EXTERNAL_ENFORCEMENT_UNKNOWN,
        "деплой/откат: внешние полномочия и состояние среды не подтверждаемы "
        "локально — пометка не повышает статус разрешения (FR-7; контракт §12)",
        True)]


def check_chore_task(snapshot, action, ctx, flow):
    out: list = []
    ctx["checked"].add("protected paths (J3)")
    protected = [
        p for p in action.paths
        if any(p == pe or p.startswith(pe) for pe in PROTECTED_PATHS)
    ]
    if protected and action.pipeline_marker is not True:
        out.append(Finding(
            INVALID_GATE,
            f"изменение защищенных путей ({', '.join(protected)}) требует "
            f"[pipeline]-маркер в subject (J3; pm_bounds_check; ТЗ 03 п.5)"))
    if action.rules_change:
        out.append(Finding(
            HUMAN_APPROVAL_REQUIRED,
            "изменение правил фабрики — отдельный change-пакет по решению "
            "Заказчика: обслуживание не меняет openspec/ (ТЗ 03 п.5; контракт §7 "
            "Флоу 4; pr_validate check_chore)"))
        ctx.setdefault("override_next", []).extend([
            {"action": "create_change", "task": None, "actor_role": "sa"},
        ])
    return out


def check_express_task(snapshot, action, ctx, flow):
    out: list = []
    if action.small_change is not True:
        out.append(Finding(
            MISSING_INPUT,
            "условия экспресс-режима (BACKLOG/README: мелкое изменение, "
            "ограниченный объем) не подтверждены в action.small_change — "
            "UNKNOWN (ТЗ 03 п.6)", True))
    return out


def check_express_close(snapshot, action, ctx, flow):
    """Ретроспективные артефакты обязательны до закрытия (ТЗ 03 п.6; R1.3)."""
    out: list = []
    value, status, out0 = _fact_ready(snapshot, "requirements.status", ctx)
    out.extend(out0)
    if status == "ready" and value != "approved":
        out.append(Finding(
            MISSING_INPUT,
            "ретроспективные requirements обязательны до закрытия цикла (ТЗ 03 "
            "п.6; урок R1.3; evidence: requirements.md)"))
    specs_value, specs_status, out1 = _fact_ready(snapshot, "specs.present", ctx)
    out.extend(out1)
    if specs_status == "ready" and (
        not isinstance(specs_value, dict) or specs_value.get("count", 0) == 0
    ):
        out.append(Finding(
            MISSING_INPUT,
            "ретроспективная spec delta обязательна до закрытия (ТЗ 03 п.6)"))
    tm_value, tm_status, out2 = _fact_ready(snapshot, "test_model.present", ctx)
    out.extend(out2)
    if tm_status == "ready" and isinstance(tm_value, dict) and not tm_value.get("new"):
        out.append(Finding(
            MISSING_INPUT,
            "ретроспективные кейсы обязательны до закрытия (ТЗ 03 п.6)"))
    return out


# --------------------------------------------------------------- таблица этапов
# D3: этап = действие + роли + gates + обязательное решение Заказчика + проверка.


@dataclass(frozen=True)
class Stage:
    action: str
    roles: tuple
    approval: bool
    gates: tuple
    check: Callable


STAGE_TABLE: dict[int, tuple[Stage, ...]] = {
    1: (
        Stage("approve_requirements", ("customer", "pm"), True,
              ("flow_check C1/E3",), check_approve_requirements),
        Stage("create_change", ("sa",), True,
              ("openspec validate --strict",), check_create_change),
        Stage("architecture_review", ("pm",), False,
              ("flow_check (контракт 2)",), check_needs_arch),
        Stage("dev_task", ("dev",), False,
              ("flow_check", "pm_bounds_check (J9/J10)"), check_dev_task),
        Stage("code_review", ("code_reviewer",), False,
              ("review-файл с вердиктом (agents/code_reviewer_agent.md)",),
              check_code_review),
        Stage("accept_review", ("code_reviewer",), False,
              ("provenance-блок (поставка 05)",), check_accept_review),
        Stage("merge_task", ("dev_lead", "integrator"), False,
              ("pm_bounds_check --require-review", "pr_validate",
               "branch protection (внеш.)"), check_merge_task),
        Stage("qa_checklist", ("qa_checklist",), False,
              ("flow_check (контракт 3)",), check_qa_checklist),
        Stage("qa_cases", ("qa_author",), False,
              ("flow_check (контракт 4)",), check_qa_cases),
        Stage("qa_review", ("qa_case_reviewer",), False,
              ("flow_check (контракт 5)",), check_qa_review),
        Stage("qa_automation", ("qa_automation",), False,
              ("flow_check (контракт 6)",), check_qa_automation),
        Stage("archive_change", ("integrator", "dev_lead"), False,
              ("flow_check (контракт 7)", "openspec validate"), check_archive_change),
        Stage("release", ("pm",), True, (), check_release),
    ),
    2: (
        Stage("bug_fix", ("dev",), False,
              ("pr_validate [BUG-NNN]",), check_bug_fix),
        Stage("accept_review", ("code_reviewer",), False,
              ("provenance-блок (поставка 05)",), check_accept_review),
        Stage("merge_task", ("dev_lead", "integrator"), False,
              ("pm_bounds_check --require-review", "pr_validate",
               "branch protection (внеш.)"), check_merge_task),
    ),
    3: (
        Stage("emergency_stabilize", ("dev", "devops"), False,
              ("pr_validate (последующий PR-цикл)",), check_emergency_stabilize),
        Stage("accept_review", ("code_reviewer",), False,
              ("provenance-блок (поставка 05)",), check_accept_review),
        Stage("merge_task", ("dev_lead", "integrator"), False,
              ("pm_bounds_check --require-review", "pr_validate",
               "branch protection (внеш.)"), check_merge_task),
        Stage("deploy_rollback", ("devops", "pm"), True,
              ("внешние полномочия (ТЗ 03 п.4)",), check_deploy_rollback),
    ),
    4: (
        Stage("chore_task", ("dev",), False,
              ("pr_validate check_chore", "pm_bounds_check (J3)"), check_chore_task),
        Stage("code_review", ("code_reviewer",), False,
              ("review-файл с вердиктом (agents/code_reviewer_agent.md)",),
              check_code_review),
        Stage("accept_review", ("code_reviewer",), False,
              ("provenance-блок (поставка 05)",), check_accept_review),
        Stage("merge_task", ("dev_lead", "integrator"), False,
              ("pm_bounds_check --require-review", "pr_validate",
               "branch protection (внеш.)"), check_merge_task),
    ),
    5: (
        Stage("express_task", ("dev",), False,
              ("pr_validate [change-id]",), check_express_task),
        Stage("express_close", ("pm",), False,
              ("flow_check", "openspec validate"), check_express_close),
    ),
}


# --------------------------------------------------------------- check_action


def _decide(snapshot, action, findings, ctx, stage, include_next) -> Decision:
    scope = dict(snapshot.get("scope", {})) if isinstance(snapshot, dict) else {}
    status = DENY if any(not f.unknown for f in findings) else (
        UNKNOWN if findings else ALLOW)
    blocking: list = []
    for f in findings:
        if f.code not in blocking:
            blocking.append(f.code)
    gates = list(stage.gates) if stage else []
    gates.extend(ctx.get("extra_gates") or [])
    next_candidates = list(ctx.get("override_next") or [])
    if include_next and stage is not None:
        flow = scope.get("flow") or 0
        for s in STAGE_TABLE.get(flow, ()):
            probe = ActionRequest(
                actor_role=s.roles[0],
                requested_action=s.action,
                task_id=action.task_id,
                approval_ref=action.approval_ref,
                task_parallel=action.task_parallel,
                task_dependencies=action.task_dependencies,
                dependency_evidence=action.dependency_evidence,
                spec_delta=action.spec_delta,
                incident_ref=action.incident_ref,
                paths=action.paths,
                pipeline_marker=action.pipeline_marker,
                rules_change=action.rules_change,
                small_change=action.small_change,
            )
            probe_decision = check_action(snapshot, probe, include_next=False)
            if probe_decision.status == ALLOW:
                cand = {"action": s.action, "task": probe.task_id,
                        "actor_role": s.roles[0]}
                if cand not in next_candidates:
                    next_candidates.append(cand)
    return Decision(
        allowed=(status == ALLOW),
        status=status,
        action=action.requested_action,
        scope=scope,
        actor_role=action.actor_role,
        snapshot_digest=str(snapshot.get("snapshot_digest", "")) if isinstance(snapshot, dict) else "",
        requirements_checked=sorted(ctx["checked"]),
        blocking_reasons=blocking,
        details=[f"{f.code}: {f.detail}" for f in findings],
        required_gates=gates,
        evidence_refs=sorted(ctx["evidence"]),
        next_candidates=next_candidates,
    )


def check_action(snapshot: dict, action: ActionRequest,
                 include_next: bool = False) -> Decision:
    """Чистая проверка действия по снимку (контракт §4, §6; FR-3).

    Читает только snapshot + action; ничего не пишет, не запускает агентов.
    UNKNOWN никогда не разрешает исполнение; DENY перечисляет все причины.
    """
    ctx: dict = {"checked": set(), "evidence": set()}
    findings: list = []
    stage = None

    if not isinstance(snapshot, dict) or not str(
        snapshot.get("schema_version", "")
    ).startswith("flow-snapshot"):
        findings.append(Finding(
            AMBIGUOUS_STATE,
            "снимок не распознан (schema_version не flow-snapshot/*) — пересобери "
            "inspect (поставка 02)", True))
        return _decide(snapshot, action, findings, ctx, None, include_next)

    scope = snapshot.get("scope", {})
    if action.expected_snapshot_digest and (
        action.expected_snapshot_digest != snapshot.get("snapshot_digest")
    ):
        findings.append(Finding(
            STALE_SNAPSHOT,
            f"ожидаемый digest {action.expected_snapshot_digest[:12]}… ≠ "
            f"фактическому {str(snapshot.get('snapshot_digest'))[:12]}… — снимок "
            f"устарел, вызови inspect заново (контракт §6)"))

    flow = scope.get("flow")
    if flow not in STAGE_TABLE:
        findings.append(Finding(
            AMBIGUOUS_STATE,
            f"неизвестный flow {flow!r} (ожидается 1–5) — неоднозначный scope "
            f"блокирует действие (контракт §3)", True))
        return _decide(snapshot, action, findings, ctx, None, include_next)

    for p in snapshot.get("problems", []):
        if p.get("code") == "FLOW_ID_INVALID":
            findings.append(Finding(
                AMBIGUOUS_STATE,
                f"scope не соответствует выбранному флоу: {p.get('detail')} "
                f"(ТЗ 02 п.6)", True))

    if not action.requested_action or not action.actor_role:
        findings.append(Finding(
            MISSING_INPUT,
            "actor_role и requested_action обязательны (контракт §6)"))
        return _decide(snapshot, action, findings, ctx, None, include_next)

    stages = {s.action: s for s in STAGE_TABLE[flow]}
    stage = stages.get(action.requested_action)
    if stage is None:
        findings.append(Finding(
            MISSING_INPUT,
            f"действие «{action.requested_action}» не входит в граф Флоу {flow} "
            f"(доступно: {', '.join(sorted(stages))}; контракт §7)", True))
        return _decide(snapshot, action, findings, ctx, None, include_next)

    ctx["checked"].add(f"role:{action.actor_role}")
    if action.actor_role not in stage.roles:
        findings.append(Finding(
            WRONG_ROLE,
            f"действие «{action.requested_action}» зарезервировано ролью "
            f"{'/'.join(sorted(stage.roles))}, фактическая «{action.actor_role}» "
            f"(agents/README.md; контракт §7)"))
    if stage.approval:
        af = _approval_finding(action, scope, action.requested_action)
        if af is not None:
            findings.append(af)
    findings.extend(stage.check(snapshot, action, ctx, flow))
    return _decide(snapshot, action, findings, ctx, stage, include_next)


# ------------------------------------------------------------------- CLI


def _decision_human(d: Decision) -> str:
    scope = d.scope
    lines = [
        f"flow_transition: {d.status} action={d.action} role={d.actor_role} "
        f"flow={scope.get('flow')} change={scope.get('change')}"
        + (f" task={scope.get('task')}" if scope.get("task") else "")
    ]
    if d.details:
        lines.append("причины/замечания:")
        lines.extend(f"  {x}" for x in d.details)
    else:
        lines.append("причины: нет")
    lines.append(f"gates: {', '.join(d.required_gates) if d.required_gates else '—'}")
    if d.evidence_refs:
        lines.append(f"evidence: {', '.join(d.evidence_refs)}")
    if d.next_candidates:
        lines.append("next_candidates:")
        for c in d.next_candidates:
            task = f" task={c['task']}" if c.get("task") else ""
            lines.append(f"  {c['action']} ({c['actor_role']}){task}")
    lines.append(f"snapshot_digest: {d.snapshot_digest}")
    return "\n".join(lines)


def _task_lines(tasks_text: str) -> dict[str, dict]:
    """task_id → {closed, parallel, deps, title} из текста tasks.md."""
    out: dict[str, dict] = {}
    for m in TASK_LINE_RE.finditer(tasks_text):
        tid = m.group(2)
        body = m.group(3)
        deps_m = DEPS_RE.search(body)
        deps = []
        if deps_m:
            deps = [d.strip() for d in deps_m.group(1).split(",")]
        out[tid] = {
            "closed": m.group(1) == "x",
            "parallel": PARALLEL_MARKER in body,
            "deps": deps,
            "title": body.strip(),
        }
    return out


def _dep_evidence(repo: Path, change_id: str, deps: tuple) -> dict:
    """Evidence по зависимостям: чекбокс (flow_check.closed_dev_tasks) + approve
    (flow_check.approved_review_tasks) — J10-логика, без дублирования парсеров."""
    tasks_file = repo / "openspec" / "changes" / change_id / "tasks.md"
    text = ""
    if tasks_file.is_file():
        text = tasks_file.read_text(encoding="utf-8", errors="replace")
    closed = set(flow_check.closed_dev_tasks(text))
    approved = flow_check.approved_review_tasks(repo, change_id)
    ev = {}
    for d in deps:
        ev[d] = {
            "task_closed": d in closed,
            "review_approved": any(
                d in re.findall(r"\d+(?:\.\d+)*", name) for name in approved
            ),
        }
    return ev


def _task_deps_from_repo(repo: Path, change_id: str, task_id: str) -> tuple[dict, bool]:
    """[P]-маркер и зависимости задачи из tasks.md (read-only)."""
    tasks_file = repo / "openspec" / "changes" / change_id / "tasks.md"
    if not tasks_file.is_file():
        return {}, False
    meta = _task_lines(tasks_file.read_text(encoding="utf-8", errors="replace"))
    info = meta.get(task_id, {})
    return info, bool(info.get("parallel"))


def _snapshot_ctx(args) -> tuple[dict, Path]:
    snapshot = flow_state.inspect(
        repo_arg=args.repo,
        project=args.project,
        flow=args.flow,
        change_id=args.change,
        task_id=args.task,
        registry=args.registry,
    )
    return snapshot, Path(args.repo)


def _action_from_args(args, deps: tuple = (), dep_ev: dict | None = None,
                      task_parallel: bool | None = None,
                      parallel_confirmed: bool | None = None) -> ActionRequest:
    paths = tuple(p for p in (args.paths or "").split(",") if p) \
        if getattr(args, "paths", None) else ()
    return ActionRequest(
        actor_role=args.role,
        requested_action=args.action,
        task_id=args.task,
        approval_ref=args.approval_ref,
        expected_snapshot_digest=args.expected_digest,
        task_parallel=task_parallel if task_parallel is not None else args.parallel,
        parallel_confirmed=parallel_confirmed,
        task_dependencies=deps,
        dependency_evidence=dep_ev,
        spec_delta=args.spec_delta,
        incident_ref=args.incident_ref,
        paths=paths,
        pipeline_marker=args.pipeline_marker,
        rules_change=args.rules_change,
        small_change=args.small_change,
    )


def _cmd_check(args) -> int:
    try:
        snapshot, repo = _snapshot_ctx(args)
    except ValueError as exc:
        print(f"FLOW-TRANSITION-ERROR: {exc}")
        return 2
    deps: tuple = ()
    dep_ev = None
    parallel = args.parallel          # None | True | False (три состояния, R5)
    parallel_confirmed = None
    if args.flow == 1 and args.task:
        info, parallel_auto = _task_deps_from_repo(repo, args.change, args.task)
        deps = tuple(info.get("deps", ()))
        if parallel is None:
            parallel = parallel_auto
        # Маркер [P] подтвержден разбором tasks.md (read-only) — тогда
        # parallel_confirmed=True; флаг --parallel вручную без маркера —
        # остается неподтвержденным → UNKNOWN в check_dev_task (R5).
        if parallel:
            parallel_confirmed = bool(info.get("parallel"))
    if deps:
        dep_ev = _dep_evidence(repo, args.change, deps)
    action = _action_from_args(args, deps=deps, dep_ev=dep_ev,
                               task_parallel=parallel,
                               parallel_confirmed=parallel_confirmed)
    decision = check_action(snapshot, action)
    if args.as_json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2,
                         sort_keys=True))
    else:
        print(_decision_human(decision))
    return {ALLOW: 0, DENY: 1, UNKNOWN: 2}[decision.status]


def _cmd_next(args) -> int:
    try:
        snapshot, repo = _snapshot_ctx(args)
    except ValueError as exc:
        print(f"FLOW-TRANSITION-ERROR: {exc}")
        return 2
    stages = STAGE_TABLE[args.flow]
    candidates: list = []
    waiting: list = []
    seen = set()

    def probe_and_add(action: ActionRequest) -> None:
        key = (action.requested_action, action.task_id)
        if key in seen:
            return
        seen.add(key)
        # Каждая задача — свой снимок: task-факт гранулярный (поставка 02).
        probe_snapshot = snapshot
        if action.task_id and action.task_id != args.task:
            try:
                probe_snapshot = flow_state.inspect(
                    repo_arg=args.repo, project=args.project, flow=args.flow,
                    change_id=args.change, task_id=action.task_id,
                    registry=args.registry,
                )
            except ValueError:
                probe_snapshot = snapshot
        d = check_action(probe_snapshot, action)
        if d.status == ALLOW:
            candidates.append({"action": action.requested_action,
                               "task": action.task_id,
                               "actor_role": action.actor_role})
        elif d.status == DENY:
            waiting.append({"action": action.requested_action,
                            "task": action.task_id,
                            "reasons": d.details})

    # 1) действия без задачи (или с указанной задачей)
    for s in stages:
        probe_and_add(ActionRequest(
            actor_role=s.roles[0], requested_action=s.action, task_id=args.task,
            approval_ref=args.approval_ref,
            task_parallel=args.parallel, spec_delta=args.spec_delta,
            incident_ref=args.incident_ref,
            paths=tuple(p for p in (args.paths or "").split(",") if p) if args.paths else (),
            pipeline_marker=args.pipeline_marker,
            rules_change=args.rules_change, small_change=args.small_change,
        ))

    # 2) Флоу 1: открытые dev-задачи tasks.md — каждая как кандидат dev_task
    if args.flow == 1:
        tasks_file = repo / "openspec" / "changes" / args.change / "tasks.md"
        if tasks_file.is_file():
            meta = _task_lines(
                tasks_file.read_text(encoding="utf-8", errors="replace"))
            all_deps = {d for info in meta.values() for d in info.get("deps", ())}
            dep_ev = _dep_evidence(repo, args.change, tuple(all_deps)) \
                if all_deps else {}
            for tid, info in sorted(meta.items()):
                if info["closed"]:
                    continue
                deps = tuple(info.get("deps", ()))
                probe_and_add(ActionRequest(
                    actor_role="dev", requested_action="dev_task", task_id=tid,
                    task_parallel=info["parallel"],
                    parallel_confirmed=info["parallel"],  # маркер из tasks.md
                    task_dependencies=deps,
                    dependency_evidence={d: dep_ev[d] for d in deps} if deps else None,
                ))
    result = {
        "schema_version": DECISION_SCHEMA,
        "action": "next",
        "flow": args.flow,
        "scope": snapshot["scope"],
        "candidates": candidates,
        "waiting": waiting,
        "snapshot_digest": snapshot["snapshot_digest"],
    }
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"flow_transition: next flow={args.flow} "
              f"change={args.change} — кандидатов: {len(candidates)}")
        for c in candidates:
            task = f" task={c['task']}" if c.get("task") else ""
            print(f"  → {c['action']} ({c['actor_role']}){task}")
        for w in waiting:
            task = f" task={w['task']}" if w.get("task") else ""
            print(f"  ⛔ {w['action']}{task}: {w['reasons'][0] if w['reasons'] else ''}")
        print(f"snapshot_digest: {snapshot['snapshot_digest']}")
    return 0 if candidates else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="flow_transition.py",
        description="проверка действий по снимку flow_state (поставка 03, shadow)",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, need_action: bool):
        p.add_argument("--repo", required=True, help="путь к репозиторию/worktree")
        p.add_argument("--project", required=True, help="ID проекта")
        p.add_argument("--flow", required=True, type=int, choices=flow_state.FLOW_IDS)
        p.add_argument("--change", required=True,
                       help="change-id / BUG-NNN / chore")
        p.add_argument("--task", default=None, help="задача tasks.md")
        p.add_argument("--registry", default=None, help="путь к active_sessions.json")
        if need_action:
            p.add_argument("--action", required=True, help="действие из графа (§7)")
            p.add_argument("--role", required=True, help="роль из agents/README.md")
            p.add_argument("--approval-ref", default=None,
                           help="ссылка/цитата решения Заказчика (или JSON decision v1)")
            p.add_argument("--expected-digest", default=None,
                           help="ожидаемый snapshot_digest (STALE_SNAPSHOT)")
            p.add_argument("--parallel", action="store_true", default=None,
                           help="[P]-параллельная задача (без флага — автодетект "
                                "из tasks.md; флаг без [P] в tasks.md → UNKNOWN)")
            p.add_argument("--spec-delta", action="store_true",
                           help="Флоу 2: фикс вводит новое поведение/API")
            p.add_argument("--incident-ref", default=None,
                           help="Флоу 3: ссылка на причину инцидента")
            p.add_argument("--paths", default=None,
                           help="Флоу 4: затрагиваемые пути через запятую")
            p.add_argument("--pipeline-marker", action="store_true",
                           help="Флоу 4: [pipeline]-маркер стоит")
            p.add_argument("--rules-change", action="store_true",
                           help="Флоу 4: действие меняет правила фабрики")
            p.add_argument("--small-change", action="store_true",
                           help="Флоу 5: условия экспресс-режима подтверждены")
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="машинный JSON")

    p_check = sub.add_parser("check", help="проверить одно действие")
    common(p_check, need_action=True)
    p_check.set_defaults(func=_cmd_check)

    p_next = sub.add_parser("next", help="допустимые следующие действия")
    common(p_next, need_action=False)
    p_next.add_argument("--approval-ref", default=None)
    p_next.add_argument("--parallel", action="store_true", default=None)
    p_next.add_argument("--spec-delta", action="store_true")
    p_next.add_argument("--incident-ref", default=None)
    p_next.add_argument("--paths", default=None)
    p_next.add_argument("--pipeline-marker", action="store_true")
    p_next.add_argument("--rules-change", action="store_true")
    p_next.add_argument("--small-change", action="store_true")
    p_next.set_defaults(func=_cmd_next)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
