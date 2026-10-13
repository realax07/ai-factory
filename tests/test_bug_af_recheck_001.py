# -*- coding: utf-8 -*-
"""BUG-AF-RECHECK-001: flow-enforcer терял пути задачи → продуктовая dev-задача
проходила без архитектурного ревью (J43×J46).

Фикс: маркер-грамматика дополнена paths=<путь1,путь2,...> (относительные пути,
запятая-разделитель; идут в flowctl prepare как --path) и kind=docs|product:
  - kind=docs — облегченный маршрут, пути не обязательны;
  - kind=product без paths — block PATHS_MISSING (не docs-only по умолчанию);
  - kind не указан — WARNING + трактовка как product (без paths → PATHS_MISSING,
    fail-closed, честный MISSING-класс).

Интеграционные кейсы (критерии репорта) гоняют РЕАЛЬНЫЙ flowctl prepare
--dry-run на fixture-репо (по образцу tests/test_j43_flow_enforcer.py):
  - продуктовая задача без arch-review → block + ARCH_REVIEW_MISSING;
  - с approve-файлом test-model/reviews/<change>/review-001-architecture.md
    («## Вердикт: approve») → allow;
  - docs-only (непродуктовые пути / kind=docs) → allow без arch-review.
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
    monkeypatch.delenv("FLOW_ENFORCER_FLOW", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_SEQUENCE", raising=False)
    monkeypatch.delenv("FLOW_ENFORCER_PROJECT", raising=False)
    monkeypatch.delenv("FLOW_BYPASS_REGISTRY", raising=False)
    yield state


def delegate_args(goal: str, context: str | None = None) -> dict:
    a = {"goal": goal}
    if context is not None:
        a["context"] = context
    return a


def install_fake_run(monkeypatch, rc: int, out: str, err: str = "") -> list:
    calls: list[list[str]] = []

    def _fake(argv, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess([], rc, out, err)

    monkeypatch.setattr(enforcer.subprocess, "run", _fake)
    return calls


def _log_entries(plugin_env) -> list[dict]:
    return [json.loads(l) for l in
            (plugin_env / "flow-enforcer.log").read_text("utf-8").splitlines()
            if l.strip()]


# ------------------------------------------------- парсер: paths= и kind=


def test_parse_paths_and_kind_from_header():
    """TC-AF-RECHECK-001-01: paths=<p1,p2> → список путей; kind=product — в
    markers (BUG-AF-RECHECK-001)."""
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "kind=product paths=backend/app/w.py,src/x.py\n")
    m = enforcer.parse_markers(delegate_args(goal))
    assert m["kind"] == "product"
    assert m["paths"] == ["backend/app/w.py", "src/x.py"]


def test_parse_paths_single_marker_and_defaults():
    """TC-AF-RECHECK-001-02: одиночный маркер 'paths: ...' распознается; без
    kind/paths маркеры нейтральны (kind=None, paths=[])."""
    m = enforcer.parse_markers(delegate_args(
        "flow: flow=1 role=dev repo=/tmp/proj scope=add-widget\n"
        "paths: docs/guide.md\n"))
    assert m["paths"] == ["docs/guide.md"] and m["kind"] is None
    m2 = enforcer.parse_markers(delegate_args(
        "flow: flow=1 role=dev repo=/tmp/proj scope=add-widget\n"))
    assert m2["paths"] == [] and m2["kind"] is None


def test_unknown_kind_is_marker_error():
    """TC-AF-RECHECK-001-03: kind=docs2 → FLOW_MARKER_INVALID (очевидная
    ошибка маркера блокирует в любом режиме)."""
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "kind=docs2 paths=docs/x.md\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "k1")
    assert res is not None and res["action"] == "block"
    assert "FLOW_MARKER_INVALID" in res["message"]


def test_empty_paths_is_marker_error():
    """TC-AF-RECHECK-001-04: пустой paths= в заголовке — очевидная ошибка
    (не молчаливое «нет путей»)."""
    goal = "flow: flow=1 role=dev repo=/tmp/proj scope=add-widget paths=\n"
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "k2")
    assert res is not None and res["action"] == "block"
    assert "FLOW_MARKER_INVALID" in res["message"]
    assert "paths" in res["message"]


# -------------------------------------------- kind/paths: маршрут энфорсера


def test_prepare_command_passes_each_path():
    """TC-AF-RECHECK-001-05: prepare_command добавляет --path для КАЖДОГО пути
    (пути задачи не теряются при построении команды)."""
    markers = {"role": "dev", "repo": "/tmp/proj", "scope": "add-widget",
               "task": None, "flow": 1, "kind": "product",
               "paths": ["backend/app/w.py", "src/x.py"]}
    argv = enforcer.prepare_command(markers, 1, "dev_task")
    paths = [argv[i + 1] for i, v in enumerate(argv) if v == "--path"]
    assert paths == ["backend/app/w.py", "src/x.py"]


def test_product_without_paths_blocked_paths_missing(monkeypatch):
    """TC-AF-RECHECK-001-06: kind=product без paths — block PATHS_MISSING,
    prepare НЕ вызывается (отсутствие путей ≠ docs-only)."""
    calls = install_fake_run(monkeypatch, rc=0, out="")
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "kind=product\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "p1")
    assert res is not None and res["action"] == "block"
    assert "PATHS_MISSING" in res["message"]
    assert calls == []


def test_kind_unspecified_assumed_product_with_warning(monkeypatch):
    """TC-AF-RECHECK-001-07: kind не указан → WARNING kind_assumed_product в
    логе и тот же честный PATHS_MISSING при отсутствии paths (fail-closed)."""
    install_fake_run(monkeypatch, rc=0, out="")
    goal = "flow: flow=1 role=dev repo=/tmp/proj scope=add-widget\n"
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "p2")
    assert res is not None and res["action"] == "block"
    assert "PATHS_MISSING" in res["message"]
    events = [e.get("event") for e in _log_entries(plugin_env_from(res))]
    assert "kind_assumed_product" in events


def plugin_env_from(_res):
    """Лог читается через FLOW_ENFORCER_STATE_DIR (фикстура plugin_env)."""
    import os
    return Path(os.environ["FLOW_ENFORCER_STATE_DIR"])


def test_kind_docs_without_paths_runs_prepare(monkeypatch):
    """TC-AF-RECHECK-001-08: kind=docs без paths — облегченный маршрут:
    prepare вызывается (без PATHS_MISSING), ALLOW при ok-воротах."""
    calls = install_fake_run(monkeypatch, rc=0, out="prepared: true\n")
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "kind=docs\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "p3")
    assert res is None
    assert len(calls) == 1
    assert "--path" not in calls[0]


def test_paths_reach_prepare_via_hook(monkeypatch):
    """TC-AF-RECHECK-001-09: сквозной прогон хука (мок subprocess): paths из
    goal попадают в argv prepare (--path, по одному на путь)."""
    calls = install_fake_run(monkeypatch, rc=0, out="")
    goal = ("flow: flow=1 role=dev repo=/tmp/proj scope=add-widget "
            "paths=backend/app/w.py,src/x.py\n")
    res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "p4")
    assert res is None
    argv = calls[0]
    assert argv.count("--path") == 2


# ------------------------- интеграция: hook × РЕАЛЬНЫЙ flowctl prepare


REQ_APPROVED = ("# ТЗ\n\n> Статус: УТВЕРЖДЕН | Автор: ba_agent | "
                "История: r1\n\n## Описание\n...\n\n## Аудитория\nПМ, dev.\n\n"
                "## Функциональные требования\n- FR-1 виджет\n\n"
                "## Нефункциональные требования\n- NFR-1 быстро\n\n"
                "## Приоритеты\n- P1\n\n## Ограничения\n- без push\n\n"
                "## Открытые вопросы\n- нет\n")
ARCH_APPROVE = "# Architecture review\n\n## Вердикт: approve\n"


def _make_repo(tmp_path: Path, name: str = "proj") -> Path:
    """Git-репо Флоу 1 (change add-widget), собранный пакет + backend-файл.
    PLAN-add-widget.md подкладывает autouse-фикстура conftest до коммита."""
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)

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
           "### Requirement: W\n#### Scenario: S\n"
           "- GIVEN a\n- WHEN b\n- THEN c\n")
    _write("sdd.md", "# SDD\n")
    _write("backend/app/widget.py", "X = 1\n")
    _git("add", "-A")
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


def _write_arch_review(repo: Path, text: str, name: str =
                       "review-001-architecture.md") -> None:
    p = repo / "test-model" / "reviews" / "add-widget" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "arch review"],
                   check=True, capture_output=True)


class TestHookTimesRealFlowctl:
    """Критерии репорта: hook + настоящий flowctl prepare на fixture-репо."""

    def test_product_task_without_arch_review_blocked(self, tmp_path,
                                                      monkeypatch):
        """TC-AF-RECHECK-001-10: продуктовая dev-задача (paths=backend/…)
        без architecture-ревью → block + ARCH_REVIEW_MISSING (раньше проходила:
        prepare без --path оставлял product_paths пустым)."""
        repo = _make_repo(tmp_path)
        monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
        goal = (f"flow: flow=1 role=dev repo={repo} scope=add-widget "
                "paths=backend/app/widget.py\n"
                "task: 1.1\nЗадача: виджет без ревью.\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "i1")
        assert res is not None and res["action"] == "block", \
            f"ожидался block, получен ALLOW: {res}"
        # Код ворот может обрезаться в тексте block (хвост 2000 символов) —
        # вердикт ворот сверяем по полному выводу РЕАЛЬНОГО prepare.
        markers = enforcer.parse_markers(delegate_args(goal))
        rc, out, _ = enforcer.run_prepare(markers, 1, "dev_task")
        decision = enforcer.parse_decision_output(out)
        assert rc != 0 and decision is not None
        assert "ARCH_REVIEW_MISSING" in (decision.get("blocking_reasons") or []), \
            decision

    def test_product_task_with_arch_approve_allowed(self, tmp_path,
                                                    monkeypatch):
        """TC-AF-RECHECK-001-11: та же задача с approve-файлом
        test-model/reviews/<change>/review-001-architecture.md
        («## Вердикт: approve») → allow."""
        repo = _make_repo(tmp_path)
        _write_arch_review(repo, ARCH_APPROVE)
        monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
        goal = (f"flow: flow=1 role=dev repo={repo} scope=add-widget "
                "paths=backend/app/widget.py\n"
                "task: 1.1\nЗадача: виджет.\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "i2")
        assert res is None, f"ожидался ALLOW, получен block: {res}"

    def test_docs_only_paths_allowed_without_arch_review(self, tmp_path,
                                                         monkeypatch):
        """TC-AF-RECHECK-001-12: непродуктовые пути (docs-only маршрут) —
        allow БЕЗ architecture-ревью."""
        repo = _make_repo(tmp_path)
        monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
        goal = (f"flow: flow=1 role=dev repo={repo} scope=add-widget "
                "paths=openspec/changes/add-widget/tasks.md\n"
                "task: 1.1\nЗадача: правка задач пакета.\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "i3")
        assert res is None, f"ожидался ALLOW, получен block: {res}"

    def test_kind_docs_no_paths_allowed_on_real_repo(self, tmp_path,
                                                     monkeypatch):
        """TC-AF-RECHECK-001-13: kind=docs без paths — облегченный маршрут на
        РЕАЛЬНОМ prepare (prepare без --path, как раньше для docs)."""
        repo = _make_repo(tmp_path)
        monkeypatch.setenv("FLOW_ENFORCER_MODE", "strict")
        goal = (f"flow: flow=1 role=dev repo={repo} scope=add-widget "
                "kind=docs\n"
                "task: 1.1\nЗадача: описание задачи пакета.\n")
        res = enforcer.flow_enforce("delegate_task", delegate_args(goal), "i4")
        assert res is None, f"ожидался ALLOW, получен block: {res}"
