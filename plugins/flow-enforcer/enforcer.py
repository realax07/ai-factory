# -*- coding: utf-8 -*-
"""flow-enforcer — ядро pre_tool_call-энфорсера делегаций (J43, J43.1 flow-aware).

Перехватывает только tool_name == 'delegate_task'. Из args.goal/args.context
парсит маркеры конвейера:

  1. Заголовок (канонический формат J43.1, см. templates/task_delegation.md):
         flow: flow=<1-5> role=<роль> repo=<путь> scope=<идентификатор>
               [paths=<путь1,путь2,...>] [kind=docs|product]
     scope — по флоу: Ф1 change-id; Ф2 BUG-<КОМПЛЕКС>-NNN (репорт
     test-model/bugs/; BUG-001 и BUG-AF-RECHECK-001 оба валидны);
     Ф3 incident-id (формат любой, обязателен); Ф4 chore-slug; Ф5 slug.
     paths — относительные пути задачи через запятую (ТОЛЬКО относительные,
     без '..'-сегментов — иначе FLOW_MARKER_INVALID; MAJ-2 ревью
     BUG-AF-RECHECK); попадают в flowctl prepare как --path (зоны/вороты
     видят РЕАЛЬНЫЕ пути задачи; BUG-AF-RECHECK-001: отсутствие путей ≠
     docs-only). kind — тип задачи: docs | product. kind=docs без путей
     валиден ТОЛЬКО для docs_task/chore_task (MAJ-1 ревью BUG-AF-RECHECK:
     для dev_task kind=docs без путей — отказ PATHS_MISSING, продуктовая
     задача не может быть docs по определению). kind не указан → WARNING и
     трактовка как product: без paths — block PATHS_MISSING (fail-closed,
     честный MISSING-класс).
  2. Старый формат (обратная совместимость): 'flow: role=R repo=P change=C'
     без flow= — трактуется как Флоу 1 (env-fallback), с WARNING в лог.
  3. Одиночные маркеры: 'role: X', 'repo: P', 'change:/scope: C' в тех же
     строках; task: — опциональный (dev_task уровня задачи).

Очевидные ошибки маркера (flow=9, пустой scope, Ф2 без формата
BUG-<КОМПЛЕКС>-NNN) → block FLOW_MARKER_INVALID в ЛЮБОМ режиме: битый
маркер хуже отсутствующего.

Без маркеров решение по режиму FLOW_ENFORCER_MODE:
  - 'strict'     → block MARKERS_MISSING;
  - 'permissive' (дефолт) → пропуск + запись в лог (аудит-след).

Bypass: дословная строка 'flow: bypass --by customer' в goal — ЗАЯВКА на
обход, но сама по себе ничего не разрешает (BUG-AF-RECHECK-002: goal
формирует оркестратор, цитата маркера в тексте тоже выглядит как маркер).
Обход действует ТОЛЬКО при действующей записи в реестре решений Заказчика
~/.hermes/state/flow-bypass-decisions.json (список записей
{repo, scope, action, decision_ref, expires}; expires — UTC ISO): запись
ищется по (repo, scope, action) и обязана быть неистекшей. Нет записи /
просрочена / другой scope или action → bypass-ветка НЕ срабатывает, идет
обычная проверка (как правило DENY). Ошибка чтения/разбора реестра — не
разрешение (fail-closed). Запись в bypass-лог дополняется decision_ref и
match (что именно совпало).

Валидация: subprocess flowctl prepare --dry-run --json (--dry-run, чтобы
энфорсер НЕ создавал reservation/zone-резерв; --json — чтобы вердикт парсился
машинно). Номер флоу — из маркера (flow=); env FLOW_ENFORCER_FLOW — ТОЛЬКО
fallback, когда в маркере нет flow= (с WARNING в лог). prepare вызывается с
--flow <N> и --change <scope>; роль отображается в действие СВОЕГО флоу
(ROLE_ACTIONS_FLOW: Ф2 dev→bug_fix, Ф3 →emergency_stabilize, Ф4 →chore_task,
Ф5 →express_task/express_close).

Post-filter «no-change scope» (J43.1): для Флоу 2/4/5 отказ prepare, в котором
ВСЕ причины — ожидаемый класс «нет change-пакета / scope-id другого формата»,
а scope-файл существует (Ф2 test-model/bugs/<scope>.md; Ф4/Ф5 PLAN-<scope>.md
или <scope>.md в корне), трактуется как ALLOW с записью в лог
'flow-N no-change scope ok'. Выбран post-filter вердикта, а не отдельный
лайт-валидатор: лайт-валидатор дублировал бы логику ворот flow_transition
(два источника истины → расхождение), post-filter переиспользует ЕДИНУЮ
проверку prepare и сужает ровно один класс отказов, независимо подтверждая
существование scope-файла. Ошибки по существу (нет плана Ф2/Ф4, нет
BUG-репорта, нет спеки, WRONG_ROLE, ...) — block как раньше.

Память фазы и последовательность (J43.1, опционально): flowctl phase
возвращает последний run scope из flowctl_state.json. При
FLOW_ENFORCER_SEQUENCE=1 после prepare-ALLOW проверяется, что запрошенное
действие имеет выполненных обязательных предшественников среди завершенных
этапов scope (SEQUENCE_PREREQS — производная от STAGE_TABLE
flow_transition.py; синхронизируется тестом test_j431). Нарушение → block
SEQUENCE_VIOLATION (дефолт off; фаза недоступна → WARNING, не блок —

проверка best-effort поверх ворот prepare).

Fail-closed: любое исключение в хуке → block
'flow-enforcer internal error: ... (fail-closed)'. Плюс платформенный
fail-closed на таймаут (hooks.md §pre_tool_call).

Env:
  FLOW_ENFORCER_MODE       strict | permissive (дефолт permissive)
  FLOW_ENFORCER_STATE_DIR  каталог логов (дефолт ~/.hermes/state)
  AI_FACTORY_HOME          путь к фабрике (дефолт ~/ai-factory)
  FLOW_ENFORCER_REGISTRY   путь к active_sessions.json (проброс --registry;
                           рядом с ним ищется flowctl_state.json для phase)
  FLOW_ENFORCER_PROJECT    project-id для prepare/phase (дефолт: имя repo)
  FLOW_ENFORCER_FLOW       fallback-номер флоу, если в маркере нет flow=
  FLOW_ENFORCER_SEQUENCE   1 → проверка последовательности этапов (дефолт off)
  FLOW_BYPASS_REGISTRY     путь к реестру bypass-решений (дефолт
                           ~/.hermes/state/flow-bypass-decisions.json)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TRIGGER_TOOL = "delegate_task"
BYPASS_MARKER = "flow: bypass --by customer"
FLOW_MARKER_INVALID = "FLOW_MARKER_INVALID"

# Канонический заголовок J43.1: 'flow: flow=N role=R repo=P scope=S'
# (порядок ключей не строгий; change= — легаси-алиас scope).
HEADER_LINE_RE = re.compile(r"^\s*flow:\s*(?P<rest>\S.*?)\s*$")
HEADER_PAIR_RE = re.compile(
    r"\b(flow|role|repo|scope|change|task|kind|paths)=([^\s]+)")
EMPTY_VALUE_RE = re.compile(r"\b(?:scope|change|paths)=(?:\s|$)")
MARKER_KINDS = ("docs", "product")
# MAJ-1 ревью BUG-AF-RECHECK: kind=docs валиден ТОЛЬКО для этих действий —
# документная/обслуживающая задача без путей; для dev_task (и любого другого
# продуктового действия) kind=docs без paths → PATHS_MISSING (иначе
# продуктовая dev-задача с kind=docs обходит arch-gate).
DOCS_KIND_ACTIONS = ("docs_task", "chore_task")
SINGLE_RE = {
    "role": re.compile(r"\brole:\s*([^\s,;]+)"),
    "repo": re.compile(r"\brepo:\s*([^\s,;]+)"),
    "change": re.compile(r"\bchange:\s*([^\s,;]+)"),
    "scope": re.compile(r"\bscope:\s*([^\s,;]+)"),
    "task": re.compile(r"\btask:\s*([^\s,;]+)"),  # опциональный (dev_task)
    "kind": re.compile(r"\bkind:\s*(docs|product)\b"),
    # paths: список через запятую — запятая НЕ разделитель маркера
    "paths": re.compile(r"\bpaths:\s*(\S+)"),
}

# Формат scope Флоу 2 (BUG-AF-RECHECK: синхронно с правилом имен репортов
# test-model/bugs/): единая грамматика — регекс-строка BUG_ID_PATTERN из
# scripts/flow_check.py (MIN-3 ревью BUG-AF-RECHECK: один источник истины;
# покрывает BUG-001, BUG-AF-RECHECK-001 и репорты с суффиксом-slug вида
# BUG-001-search-card-click.md; lowercase/кириллица/пробелы — отклонение,
# поэтому БЕЗ re.IGNORECASE). Фабрика недоступна → встроенная fallback-копия
# (синхронизируется тестом tests/test_recheck2_fixes.py).
def _bug_id_pattern() -> str:
    try:
        scripts_dir = str(factory_home() / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import flow_check
        return flow_check.BUG_ID_PATTERN
    except Exception:  # noqa: BLE001 — плагин не зависит от доступности фабрики
        return r"^BUG-(?:[A-Z0-9]+-)*\d{3}(?:-[a-z0-9][a-z0-9.-]*)?$"


BUG_ID_RE = re.compile(_bug_id_pattern())
FLOW_IDS = (1, 2, 3, 4, 5)

# Действие по роли: этапы STAGE_TABLE Флоу 1 (flow_transition.py).
ROLE_ACTIONS = {
    "dev": "dev_task",
    "sa": "create_change",
    # J46: архитектор — актор architecture_review (синхронно с STAGE_TABLE:
    # этап после create_change, до dev_task).
    "architect": "architecture_review",
    "code_reviewer": "code_review",
    "qa_automation": "qa_automation",
    # remove-qa-checklist: роль/действие qa_checklist упразднены.
    "qa_author": "qa_cases",
    "qa_case_author": "qa_cases",
    "qa_case_reviewer": "qa_review",
    "qa_impact_analyst": "qa_impact_analysis",
    "design_validator": "design_validation",
    "ui_designer": "design_task",
}
DEFAULT_ACTION = "dev_task"

# J43.1: flow-aware отображение роли в действие (этапы STAGE_TABLE Флоу 2–5;
# не переопределенные роли берутся из ROLE_ACTIONS — code_review/merge и др.
# совпадают по флоу).
ROLE_ACTIONS_FLOW = {
    2: {"dev": "bug_fix"},
    3: {"dev": "emergency_stabilize", "devops": "emergency_stabilize"},
    4: {"dev": "chore_task"},
    5: {"dev": "express_task", "pm": "express_close"},
}


def action_for_role(role: str, flow: int) -> str:
    """Действие роли В СВОЕМ флоу (J43.1): dev во Флоу 2 — bug_fix, не dev_task."""
    return ROLE_ACTIONS_FLOW.get(flow, {}).get(
        role, ROLE_ACTIONS.get(role, DEFAULT_ACTION))


# Ожидаемый класс отказов «нет change-пакета» (J43.1): Флоу 2/4/5 живут БЕЗ
# change-пакета openspec/changes/<id>/, поэтому отказ prepare, в котором все
# причины — из этого класса, при существующем scope-файле трактуется как ALLOW.
NO_CHANGE_DETAIL_PATTERNS = (
    # тексты ворот Флоу 1 о отсутствующем/несозданном change-пакете
    "change-пакет openspec/changes/",
    # Ф4: scope=chore-slug легален маркеру, но не формату [chore] flow_state
    "scope не соответствует выбранному флоу",
)

# Последовательность этапов (J43.1, FLOW_ENFORCER_SEQUENCE=1): действие →
# обязательные предшественники среди ЗАВЕРШЕННЫХ этапов того же scope.
# Производная от STAGE_TABLE (scripts/flow_transition.py): каждый предшественник
# стоит в таблице флоу РАНЬШЕ действия — синхронизация проверяется тестом
# (tests/test_j431_flow_aware.py::test_sequence_prereqs_match_stage_table).
# Возврат на доработку легален: предшественники уже в completed_actions.
SEQUENCE_PREREQS: dict[int, dict[str, frozenset]] = {
    1: {
        "approve_requirements": frozenset(),
        "create_change": frozenset(),
        "architecture_review": frozenset({"create_change"}),
        "dev_task": frozenset({"create_change"}),
        "design_task": frozenset({"create_change"}),
        "code_review": frozenset({"dev_task"}),
        "accept_review": frozenset({"code_review"}),
        "merge_task": frozenset({"accept_review"}),
        # remove-qa-checklist: этап qa_checklist удален — qa_cases принимает
        # вход напрямую от merge_task (и design_validation, когда фаза была).
        "qa_cases": frozenset({"merge_task"}),
        "qa_review": frozenset({"qa_cases"}),
        "qa_impact_analysis": frozenset({"merge_task"}),
        "qa_automation": frozenset({"qa_cases"}),
        "design_validation": frozenset({"merge_task"}),
        "archive_change": frozenset({"merge_task"}),
        "release": frozenset({"merge_task"}),
    },
    2: {
        "bug_fix": frozenset(),
        "code_review": frozenset({"bug_fix"}),
        "accept_review": frozenset({"code_review"}),
        "merge_task": frozenset({"accept_review"}),
    },
    3: {
        "emergency_stabilize": frozenset(),
        "accept_review": frozenset({"emergency_stabilize"}),
        "merge_task": frozenset({"accept_review"}),
        "deploy_rollback": frozenset({"merge_task"}),
    },
    4: {
        "chore_task": frozenset(),
        "code_review": frozenset({"chore_task"}),
        "accept_review": frozenset({"code_review"}),
        "merge_task": frozenset({"accept_review"}),
    },
    5: {
        "express_task": frozenset(),
        "express_close": frozenset({"express_task"}),
    },
}
# finished_status, означающий, что этап СОСТОЛСЯ (зеркало
# flowctl.PHASE_COMPLETED_STATUSES; returned = завершен возвратом на доработку).
COMPLETED_STATUSES = ("accepted", "returned")

SLOW_PREPARE_SECONDS = 10.0


class FlowMarkerError(ValueError):
    """Очевидная ошибка маркера → block FLOW_MARKER_INVALID (J43.1)."""


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


def _parse_header(texts: list[str]) -> dict | None:
    """Канонический/легаси заголовок 'flow: k=v ...' → пары или None."""
    for text in texts:
        for line in text.splitlines():
            m = HEADER_LINE_RE.match(line)
            if not m:
                continue
            rest = m.group("rest")
            if rest.startswith("bypass"):
                continue  # bypass-маркер обрабатывается до разбора
            if EMPTY_VALUE_RE.search(rest):
                which = "paths" if re.search(r"\bpaths=", rest) else "scope"
                if which == "paths":
                    raise FlowMarkerError(
                        "пустой paths в заголовке flow: — перечисли "
                        "относительные пути через запятую (paths=src/x.py,"
                        "backend/y.py) или убери поле (kind=docs — пути не "
                        "обязательны)")
                raise FlowMarkerError(
                    "пустой scope в заголовке flow: — scope обязателен "
                    "(Ф1 change-id, Ф2 BUG-<КОМПЛЕКС>-NNN, Ф3 incident-id, "
                    "Ф4 chore-slug, Ф5 slug; см. templates/task_delegation.md)")
            pairs = dict(HEADER_PAIR_RE.findall(rest))
            if pairs.get("role") and pairs.get("repo") and (
                pairs.get("scope") or pairs.get("change")
            ):
                return pairs
    return None


def parse_markers(args: dict) -> dict | None:
    """Достает role/repo/scope/flow/kind/paths: сначала заголовок 'flow: ...',
    затем одиночные маркеры 'role:/repo:/change:/scope:/kind:/paths:'.
    flow — ТОЛЬКО из заголовка (flow=N); None — если в маркере нет flow=
    (энфорсер возьмет env-fallback с WARNING). paths — список относительных
    путей (запятая-разделитель; BUG-AF-RECHECK-001). Очевидные ошибки (flow
    вне 1–5, пустой scope, неизвестный kind, пустой paths) → FlowMarkerError.
    Возвращает None, если обязательных маркеров нет."""
    texts = _marker_texts(args)
    header = _parse_header(texts)
    found: dict = {"role": None, "repo": None, "scope": None,
                   "task": None, "flow": None, "kind": None, "paths": None}
    if header:
        found["role"] = header.get("role")
        found["repo"] = header.get("repo")
        found["scope"] = header.get("scope") or header.get("change")
        found["task"] = header.get("task")
        found["kind"] = header.get("kind")
        found["paths"] = header.get("paths")
        raw_flow = header.get("flow")
        if raw_flow is not None:
            found["flow"] = _validate_flow(raw_flow)
    for text in texts:
        for key, rx in SINGLE_RE.items():
            if not found.get(key):
                m = rx.search(text)
                if m:
                    found[key] = m.group(1).strip("<>")
        # MIN-2 ревью BUG-AF-RECHECK: НЕ прерываем цикл, пока не собраны
        # ВСЕ маркеры — kind/paths могут жить в другом тексте (context), чем
        # role/repo/scope; ранний выход обрывал их поиск.
        if all(found.get(k)
               for k in ("role", "repo", "scope", "task", "kind", "paths")):
            break
    role, repo, scope = found["role"], found["repo"], found["scope"]
    if role and repo and scope:
        return {"role": role, "repo": repo, "scope": scope,
                "task": found["task"], "flow": found["flow"],
                "kind": _validate_kind(found["kind"]),
                "paths": _split_paths(found["paths"])}
    return None


def _validate_kind(kind: str | None) -> str | None:
    """kind маркера (BUG-AF-RECHECK-001): docs | product; неизвестный —
    очевидная ошибка маркера (FLOW_MARKER_INVALID)."""
    if kind is None:
        return None
    if kind not in MARKER_KINDS:
        raise FlowMarkerError(
            f"kind={kind!r} не поддерживается — ожидается kind=docs|product "
            "(docs — облегченный маршрут без путей; product — пути "
            "обязательны)")
    return kind


def _validate_rel_path(p: str) -> str:
    """MAJ-2 ревью BUG-AF-RECHECK: --path принимает ТОЛЬКО относительный путь
    без подъема выше корня. Абсолютный путь или '..'-сегмент — очевидная
    ошибка маркера (fail-closed на границе энфорсера, до ворот prepare)."""
    norm = p.replace("\\", "/")
    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        raise FlowMarkerError(
            f"paths={p!r} — абсолютный путь запрещен: --path ожидает путь "
            "ОТНОСИТЕЛЬНО корня репозитория (например backend/app/x.py)")
    if ".." in norm.split("/"):
        raise FlowMarkerError(
            f"paths={p!r} — сегмент '..' запрещен (подъем выше корня "
            "репозитория; укажи путь от корня, например backend/app/x.py)")
    return p


def _split_paths(raw: str | None) -> list[str]:
    """paths=<путь1,путь2,...> → список относительных путей (без пустых).
    Каждый путь валидируется (_validate_rel_path): абсолютные и '..'-пути —
    FlowMarkerError (MAJ-2 ревью BUG-AF-RECHECK)."""
    if not raw:
        return []
    return [_validate_rel_path(p) for p in
            (s.strip() for s in raw.split(",")) if p]


def _validate_flow(raw_flow: str) -> int:
    try:
        flow = int(str(raw_flow).strip())
    except ValueError:
        raise FlowMarkerError(
            f"flow={raw_flow!r} не число — ожидается flow=<1-5> (J43.1)")
    if flow not in FLOW_IDS:
        raise FlowMarkerError(
            f"flow={raw_flow} вне 1–5 — ожидается flow=<1-5> (J43.1)")
    return flow


def validate_scope_for_flow(flow: int, scope: str) -> None:
    """Формат scope своего флоу (J43.1): Ф2 — BUG-<КОМПЛЕКС>-NNN (формат
    репорта test-model/bugs/, расширен 5c21489: BUG-001 и BUG-AF-RECHECK-001
    оба валидны); Ф1 change-id / Ф3 incident-id / Ф4 chore-slug /
    Ф5 slug — непустая строка (пустой отсечен при разборе)."""
    if not scope:
        raise FlowMarkerError(
            "пустой scope — scope обязателен (Ф1 change-id, "
            "Ф2 BUG-<КОМПЛЕКС>-NNN, Ф3 incident-id, Ф4 chore-slug, Ф5 slug)")
    if flow == 2 and not BUG_ID_RE.match(scope):
        raise FlowMarkerError(
            f"Флоу 2 требует scope формата BUG-<КОМПЛЕКС>-NNN "
            f"(BUG-001 или BUG-AF-RECHECK-001; A-Z0-9, дефис-разделитель), "
            f"получено {scope!r} (репорт test-model/bugs/<scope>.md)")


def resolve_flow(markers: dict) -> tuple[int, bool]:
    """(flow, from_marker). Из маркера — без предупреждений; env
    FLOW_ENFORCER_FLOW — ТОЛЬКО fallback (WARNING в лог), дефолт 1."""
    if markers.get("flow"):
        return int(markers["flow"]), True
    raw = os.environ.get("FLOW_ENFORCER_FLOW", "1")
    try:
        flow = int(str(raw).strip())
    except ValueError:
        flow = 1
    if flow not in FLOW_IDS:
        flow = 1
    log_event({"event": "flow_fallback", "level": "WARNING",
               "flow": flow, "source": "FLOW_ENFORCER_FLOW/default",
               "note": "в маркере нет flow= — флоу взят из env/дефолта; "
                       "обнови заголовок до 'flow: flow=<1-5> role=... "
                       "repo=... scope=...' (J43.1)"})
    return flow, False


def bypass_requested(goal: str) -> bool:
    """Маркер 'flow: bypass --by customer' в goal. Это ЗАЯВКА на обход, а не
    разрешение (BUG-AF-RECHECK-002): goal формирует сам оркестратор, цитата
    маркера внутри текста неотличима от распоряжения. Разрешает только
    find_bypass_decision() — действующая запись в реестре решений."""
    return BYPASS_MARKER in (goal or "")


def bypass_registry_path() -> Path:
    """Путь реестра решений Заказчика (env FLOW_BYPASS_REGISTRY — для
    изоляции тестов; дефолт ~/.hermes/state/flow-bypass-decisions.json)."""
    return Path(os.environ.get(
        "FLOW_BYPASS_REGISTRY",
        str(state_dir() / "flow-bypass-decisions.json"))).expanduser()


def find_bypass_decision(repo: str, scope: str, action: str) -> dict | None:
    """Действующая запись реестра решений для (repo, scope, action) или None.

    Запись действует, если совпадают repo/scope/action И expires (UTC, ISO —
    ОБЯЗАТЕЛЬНО с таймзоной) еще не наступил. Нет файла, битый JSON, битая
    запись, нет/битый срок, expires БЕЗ таймзоны (naive — MAJ-3 ревью
    BUG-AF-RECHECK: молчаливая трактовка naive как UTC — fail-open сдвиг),
    просрочено, другой scope/action — обхода НЕТ (ошибка проверки решения не
    превращается в разрешение; BUG-AF-RECHECK-002). НЕСКОЛЬКО одновременных
    неистекших записей — отказ (неоднозначность, fail-closed; MAJ-3).
    """
    try:
        data = json.loads(bypass_registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    now = datetime.now(timezone.utc)
    live: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if (str(entry.get("repo", "")) != repo
                or str(entry.get("scope", "")) != scope
                or str(entry.get("action", "")) != action):
            continue
        raw = entry.get("expires")
        try:
            expires = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue  # нет/нечитаемый срок — запись не действует
        if expires.tzinfo is None:
            continue  # naive expires — НЕВАЛИДНАЯ запись (не «UTC по умолчанию»)
        if expires <= now:
            continue  # истекла
        live.append(entry)
    if len(live) == 1:
        return live[0]
    return None  # ни одной действующей ИЛИ несколько (неоднозначность)


def _append_log(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": datetime.now(timezone.utc).isoformat(
            timespec="seconds"), **payload}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass  # лог — best-effort; на отказ лога вердикт не меняется


def log_event(payload: dict) -> None:
    _append_log(state_dir() / "flow-enforcer.log", payload)


def log_bypass(task_id: str, goal: str, decision_ref: str | None = None,
               match: dict | None = None) -> None:
    """Аудит bypass: привязка к решению Заказчика (decision_ref из реестра) и
    что именно совпало (repo/scope/action); BUG-AF-RECHECK-002."""
    _append_log(state_dir() / "flow-enforcer-bypass.log", {
        "task_id": task_id, "goal_head": (goal or "")[:200],
        "kind": "bypass --by customer",
        "decision_ref": decision_ref,
        "match": match or {},
    })


def _project(repo: str) -> str:
    return os.environ.get("FLOW_ENFORCER_PROJECT") or Path(repo).name


def prepare_command(markers: dict, flow: int, action: str) -> list[str]:
    """argv проверки: flowctl prepare --dry-run --json (без side effects;
    JSON — чтобы вердикт парсился машинно). J43.1: --flow <N> из маркера,
    --change <scope>."""
    role = markers["role"]
    repo = markers["repo"]
    argv = [
        sys.executable, str(factory_home() / "scripts" / "flowctl.py"),
        "prepare", "--dry-run", "--json",
        "--role", role, "--repo", repo, "--change", markers["scope"],
        "--action", action,
        "--project", _project(repo), "--flow", str(flow),
        "--owner-pm", "flow-enforcer",
    ]
    if markers.get("task"):
        argv += ["--task", markers["task"]]
    # BUG-AF-RECHECK-001: пути задачи попадают в prepare (--path, повторяемый)
    # — ворота зон/конфликтов/arch-review работают с РЕАЛЬНЫМИ путями задачи.
    for path in markers.get("paths") or ():
        argv += ["--path", path]
    # Флоу 3: scope = incident-id — фиксируется как incident_ref (ТЗ 03 п.4).
    if flow == 3:
        argv += ["--incident-ref", markers["scope"]]
    # Флоу 5: условия экспресс-режима подтверждает сам выбор Флоу 5 ПМ;
    # содержательную проверку несет express_close (ретроспективные артефакты).
    if flow == 5:
        argv += ["--small-change"]
    registry = os.environ.get("FLOW_ENFORCER_REGISTRY")
    if registry:
        argv += ["--registry", registry]
    return argv


def run_prepare(markers: dict, flow: int, action: str) -> tuple[int, str, float]:
    """Прогон flowctl prepare --dry-run: (returncode, вывод, длительность)."""
    argv = prepare_command(markers, flow, action)
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


def parse_decision_output(out: str) -> dict | None:
    """Decision-словарь из вывода prepare --json (устойчиво к stderr-мусору)."""
    idx = out.find("{")
    if idx < 0:
        return None
    try:
        data = json.loads(out[idx:])
    except ValueError:
        return None
    return data.get("decision") if isinstance(data, dict) else None


def scope_file_candidates(flow: int, repo: Path, scope: str) -> list[Path]:
    """Scope-файлы Флоу 2/4/5 (J43.1): независимое подтверждение, что работа
    этого scope существует, хотя change-пакета нет и не должно быть."""
    if flow == 2:
        return [repo / "test-model" / "bugs" / f"{scope}.md"]
    if flow in (4, 5):
        return [repo / f"PLAN-{scope}.md", repo / f"{scope}.md"]
    return []


def no_change_scope_ok(markers: dict, flow: int, decision: dict | None) -> bool:
    """Post-filter J43.1: отказ prepare ровно из ожидаемого класса «нет
    change-пакета» (все причины — NO_CHANGE_DETAIL_PATTERNS) + существующий
    scope-файл → ожидаемая ситуация Флоу 2/4/5, не блок."""
    if flow not in (2, 4, 5) or not isinstance(decision, dict):
        return False
    details = [str(d) for d in (decision.get("details") or [])]
    if not details:
        return False
    for d in details:
        if not any(p in d for p in NO_CHANGE_DETAIL_PATTERNS):
            return False  # есть причина по существу — фильтр не применяется
    repo = Path(markers["repo"])
    return any(p.is_file() for p in scope_file_candidates(flow, repo,
                                                          markers["scope"]))


# --------------------------------------------------- память фазы (J43.1)


def _flowctl_state_path() -> Path:
    """flowctl_state.json: рядом с реестром (как default_state_path flowctl),
    иначе в FLOW_ENFORCER_STATE_DIR."""
    registry = os.environ.get("FLOW_ENFORCER_REGISTRY")
    if registry:
        return Path(registry).parent / "flowctl_state.json"
    return state_dir() / "flowctl_state.json"


def phase_command(markers: dict, flow: int) -> list[str]:
    return [
        sys.executable, str(factory_home() / "scripts" / "flowctl.py"),
        "phase",
        "--repo", markers["repo"], "--project", _project(markers["repo"]),
        "--flow", str(flow), "--scope", markers["scope"],
        "--state", str(_flowctl_state_path()),
    ]


def run_phase(markers: dict, flow: int) -> dict | None:
    """flowctl phase → JSON-словарь; недоступность (нет state/битый вывод) —
    None + WARNING: проверка последовательности best-effort, ворота prepare
    уже прошли (fail-open ТОЛЬКО у опциональной проверки, не у ворот)."""
    argv = phase_command(markers, flow)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log_event({"event": "phase_unavailable", "level": "WARNING",
                   "detail": str(exc)})
        return None
    idx = (proc.stdout or "").find("{")
    if proc.returncode != 0 or idx < 0:
        log_event({"event": "phase_unavailable", "level": "WARNING",
                   "rc": proc.returncode, "out_head": (proc.stdout or "")[:200]})
        return None
    try:
        return json.loads(proc.stdout[idx:])
    except ValueError:
        log_event({"event": "phase_unavailable", "level": "WARNING",
                   "detail": "phase stdout не JSON"})
        return None


def sequence_violation(flow: int, action: str, phase_data: dict | None) -> str | None:
    """Текст нарушения SEQUENCE_VIOLATION или None (J43.1): у запрошенного
    действия обязаны быть выполнены предшественники среди завершенных этапов
    scope. Возврат на доработку легален — предшественники уже завершены."""
    prereqs = SEQUENCE_PREREQS.get(flow, {}).get(action)
    if prereqs is None or phase_data is None:
        return None  # неизвестное действие/нет данных — решают ворота prepare
    completed = set(phase_data.get("completed_actions") or [])
    phase = phase_data.get("phase")
    last = phase.get("action") if isinstance(phase, dict) else None
    if not completed and isinstance(phase, dict) and (
        phase.get("finished_status") in COMPLETED_STATUSES
    ):
        completed = {last} if last else set()
    missing = sorted(prereqs - completed)
    if missing:
        return (f"последний завершенный этап был {last or '— (ничего)'}, "
                f"запрошен {action}; не завершены обязательные "
                f"предшественники: {', '.join(missing)}")
    return None


def sequence_gate(markers: dict, flow: int, action: str,
                  task_id: str) -> dict | None:
    """Опциональная проверка последовательности (FLOW_ENFORCER_SEQUENCE=1,
    дефолт off): после prepare-ALLOW — допустим ли action как следующий этап
    этого scope. Нарушение → block SEQUENCE_VIOLATION."""
    flag = os.environ.get("FLOW_ENFORCER_SEQUENCE", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return None
    data = run_phase(markers, flow)
    violation = sequence_violation(flow, action, data)
    if violation:
        log_event({"event": "sequence_violation", "task_id": task_id,
                   "flow": flow, "action": action, "scope": markers["scope"]})
        return {"action": "block", "message": (
            f"FLOW-ENFORCER [SEQUENCE_VIOLATION]: нарушение порядка этапов "
            f"Флоу {flow} (scope={markers['scope']}): {violation}. "
            f"Заверши предшествующие этапы через flowctl prepare/run/finish." )}
    return None


def flow_enforce(tool_name: str, args: dict, task_id: str = "",
                 **kwargs):  # noqa: ANN201 — None или directive-dict
    """pre_tool_call-хук: валидирует delegate_task против ворот конвейера."""
    try:
        if tool_name != TRIGGER_TOOL:
            return None  # не делегация — без директивы

        args = args or {}
        goal = args.get("goal") if isinstance(args.get("goal"), str) else ""
        log_event({"event": "delegate_task_seen", "task_id": task_id})

        # BUG-AF-RECHECK-002: маркер bypass — ЗАЯВКА; разрешает только запись
        # в реестре решений. Проверка возможна только когда известны
        # repo/scope/action — после разбора маркеров (см. ниже).
        bypass_wanted = bypass_requested(goal)

        try:
            markers = parse_markers(args)
        except FlowMarkerError as exc:
            log_event({"event": "flow_marker_invalid", "task_id": task_id,
                       "detail": str(exc)})
            return {"action": "block", "message": (
                f"FLOW-ENFORCER [{FLOW_MARKER_INVALID}]: {exc}. Канонический "
                "заголовок: 'flow: flow=<1-5> role=<роль> repo=<путь> "
                "scope=<идентификатор>' (см. templates/task_delegation.md).")}
        if markers is None:
            if mode() == "strict":
                return {"action": "block", "message": (
                    "FLOW-ENFORCER [MARKERS_MISSING]: делегация без маркеров "
                    "конвейера. Добавь в goal заголовок "
                    "'flow: flow=<1-5> role=<роль> repo=<путь> "
                    "scope=<идентификатор>' (см. templates/task_delegation.md) "
                    "или пройди flowctl prepare. Bypass — только 'flow: "
                    "bypass --by customer' ПРИ действующей записи в реестре "
                    "решений (~/.hermes/state/flow-bypass-decisions.json).")}
            # MIN-1 ревью BUG-AF-RECHECK: bypass-ЗАЯВКА без маркеров в
            # permissive-режиме — тоже аудит-факт: пишем в bypass-лог
            # bypass_requested_unfulfilled (заявка не могла быть проверена
            # против реестра — обход не состоялся).
            if bypass_wanted:
                _append_log(state_dir() / "flow-enforcer-bypass.log", {
                    "task_id": task_id,
                    "goal_head": (goal or "")[:200],
                    "kind": "bypass_requested_unfulfilled",
                    "note": "заявка bypass без маркеров конвейера "
                            "(permissive-пропуск) — запись реестра решений "
                            "не проверялась и не найдена",
                })
            log_event({"event": "markers_missing_permissive",
                       "task_id": task_id})
            return None

        flow, from_marker = resolve_flow(markers)
        validate_scope_for_flow(flow, markers["scope"])
        action = action_for_role(markers["role"], flow)
        if not from_marker:
            # WARNING уже в логе (flow_fallback); дублируем факт в prepare_result
            pass

        if bypass_wanted:
            # BUG-AF-RECHECK-002: обход — только по действующей записи реестра
            # решений Заказчика (repo/scope/action, неистекший expires).
            decision = find_bypass_decision(markers["repo"], markers["scope"],
                                            action)
            if decision is not None:
                match = {"repo": markers["repo"], "scope": markers["scope"],
                         "action": action}
                log_bypass(task_id, goal,
                           decision_ref=decision.get("decision_ref"),
                           match=match)
                log_event({"event": "bypass", "task_id": task_id,
                           "decision_ref": decision.get("decision_ref")})
                return None
            log_event({"event": "bypass_denied", "level": "WARNING",
                       "task_id": task_id,
                       "note": "маркер bypass без действующей записи реестра "
                               "решений (нет/просрочена/другой scope|action) "
                               "— обычная проверка ворот"})

        # BUG-AF-RECHECK-001: отсутствие путей ≠ docs-only. kind не указан →
        # WARNING + трактовка как product (без paths честный MISSING-отказ).
        # MAJ-1 ревью BUG-AF-RECHECK: kind=docs валиден ТОЛЬКО для
        # документных/обслуживающих действий (docs_task/chore_task).
        # Продуктовая dev-задача с kind=docs без paths обходит arch-gate →
        # честный отказ PATHS_MISSING (dev-задача без путей не может быть
        # docs по определению).
        kind = markers.get("kind")
        paths = markers.get("paths") or []
        if kind is None:
            log_event({"event": "kind_assumed_product", "level": "WARNING",
                       "task_id": task_id,
                       "note": "kind не указан — задача трактуется как "
                               "product (fail-closed); для docs-задачи укажи "
                               "kind=docs в заголовке flow:"})
        if not paths and (kind != "docs"
                          or action not in DOCS_KIND_ACTIONS):
            why_docs = ("действие не docs_task/chore_task"
                        if kind == "docs" else
                        "отсутствие путей ≠ docs-only (BUG-AF-RECHECK-001)")
            return {"action": "block", "message": (
                "FLOW-ENFORCER [PATHS_MISSING]: задача без путей "
                f"({why_docs}; MAJ-1 ревью BUG-AF-RECHECK: kind=docs валиден "
                "только для docs_task/chore_task). Добавь в заголовок "
                "paths=<путь1,путь2,...> (относительные пути задачи через "
                "запятую) или kind=docs для docs-задачи (действие "
                "docs_task/chore_task) без продуктовых путей.")}

        rc, out, duration = run_prepare(markers, flow, action)
        log_event({"event": "prepare_result", "task_id": task_id,
                   "rc": rc, "duration_s": round(duration, 2),
                   "flow": flow, "from_marker": from_marker,
                   "role": markers["role"], "repo": markers["repo"],
                   "scope": markers["scope"], "action": action})
        allowed = rc == 0
        if not allowed:
            # Post-filter J43.1: ожидаемый отказ «нет change-пакета» при
            # существующем scope-файле — ALLOW (Флоу 2/4/5 живут без пакета).
            decision = parse_decision_output(out)
            if no_change_scope_ok(markers, flow, decision):
                log_event({"event": f"flow-{flow} no-change scope ok",
                           "task_id": task_id, "scope": markers["scope"],
                           "prepare_rc": rc})
                allowed = True
        if allowed:
            return sequence_gate(markers, flow, action, task_id)
        return {"action": "block", "message": (
            f"FLOW-ENFORCER: flowctl prepare отклонил делегацию "
            f"(exit {rc}, flow={flow}, role={markers['role']}, "
            f"repo={markers['repo']}, scope={markers['scope']}). "
            f"Вывод ворот:\n"
            f"{out.strip()[-2000:]}")}
    except FlowMarkerError as exc:
        log_event({"event": "flow_marker_invalid", "task_id": task_id,
                   "detail": str(exc)})
        return {"action": "block", "message": (
            f"FLOW-ENFORCER [{FLOW_MARKER_INVALID}]: {exc}. Канонический "
            "заголовок: 'flow: flow=<1-5> role=<роль> repo=<путь> "
            "scope=<идентификатор>'.")}
    except Exception as e:  # noqa: BLE001 — сознательный fail-closed (J43)
        return {"action": "block", "message": (
            f"flow-enforcer internal error: {e} (fail-closed)")}


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", flow_enforce)
