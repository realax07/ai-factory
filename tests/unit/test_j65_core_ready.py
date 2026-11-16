# -*- coding: utf-8 -*-
"""J65.6: критерий «ядро готово» — ворота не знают устройства Hermes.

Решения Заказчика 2026-11-16: «SKIPPED в CI, DENY локально», «Добавить
Флоу 2», «Ворота и проверки», «Provenance-файл ревью».

Трассировка:
  TC-J65-CORE-001  граница: в scripts/*.py вне scripts/executors/,
                   установщиков и factory_paths нет обращений к данным Hermes
  TC-J65-CORE-002  независимость ревью без реестров: вне CI — отказ
                   (fail-closed), в CI — SKIPPED, PR не валится, итог
                   pr_validate показывает число SKIPPED
  TC-J65-CORE-003  реестр Hermes доступен: completed — засчитано, иное
                   состояние или нет делегации — отказ
  TC-J65-CORE-004  стадия ревью раннера per_task (scope.task) не считается
                   делегацией разработчика
  TC-J65-CORE-005  Флоу 2: PR [BUG-…] требует ревью с последним вердиктом
                   approve и доказательством независимости
  TC-J65-CORE-006  provenance-sidecar: внешний агент (<агент>:<id>) — как
                   без реестров: в CI SKIPPED, вне CI отказ; автор = ревьюер,
                   расхождение вердикта, чужой scope, неизвестный коммит —
                   отказ всегда; deleg_… в sidecar — по реестрам
  TC-J65-CORE-007  исполнитель hermes отдает транскрипты, session_archive
                   архивирует через адаптер; delegate_watchdog без пакета
                   executors — реестр недоступен, без своего SQL
  TC-J65-CORE-008  scope Флоу 2 без учета регистра и со slug; имя
                   review-NNN.md упорядочивается по номеру
"""
from __future__ import annotations

import ast
import re
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
SCRIPTS = FACTORY / "scripts"
sys.path.insert(0, str(SCRIPTS))

import executors  # noqa: E402
import pr_validate as pv  # noqa: E402

DELEG = "deleg_reviewer0001"
DEV = "deleg_dev0001"

# Скрипты, которым знание о Hermes положено (граница «Ворота и проверки»):
# адаптер (scripts/executors/), установщики плагина и кронов Hermes, единый
# модуль путей и утилита самой платформы Hermes — session_watchdog лечит
# роутинг Telegram-гейтвея в базе Hermes (sessions, gateway_routing) и
# сигналит о залипших и недоставленных делегациях (async_delegations): это
# проверка самой платформы, а не работы конвейера (решение Заказчика
# 2026-11-17 «Исключение: утилита Hermes»).
ALLOWED = {"factory_init.py", "factory_bootstrap.py", "factory_paths.py",
           "session_watchdog.py"}
BANNED_SUBSTR = ("state.db", "async_delegations", "HERMES_HOME", "errors.log",
                 "/.hermes/")
# Компоненты путей данных Hermes (кеш делегаций: cache/delegation/live;
# Path.home() / ".hermes").
BANNED_EXACT = ("delegation", "live", "cache", ".hermes")
# Упоминание памяти движка (~/.hermes/state как каталог) — не данные Hermes;
# ~/.hermes/state.db и ~/.hermes/statefoo — данные (review-002 m8).
STATE_DIR_MENTION = re.compile(r"~/\.hermes/state(?=$|[/\s)»,;:])")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant):
            out.add(id(body[0].value))
    return out


def hermes_touches(path: Path) -> list[str]:
    """Обращения к данным Hermes в коде (не в докстрингах и комментариях):
    вызов hermes_home(), строки с путями/таблицами Hermes, путь кеша
    делегаций."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstring_nodes(tree)
    hits = []
    for node in ast.walk(tree):
        # любая ссылка на hermes_home (вызов, алиас H = fp.hermes_home)
        if isinstance(node, ast.Attribute) and node.attr == "hermes_home" \
                or isinstance(node, ast.Name) and node.id == "hermes_home":
            hits.append(f"{path.name}:{node.lineno}: hermes_home")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            val = STATE_DIR_MENTION.sub("", node.value)
            for s in BANNED_SUBSTR:
                if s in val:
                    hits.append(f"{path.name}:{node.lineno}: {s!r}")
            if val in BANNED_EXACT:
                hits.append(f"{path.name}:{node.lineno}: {val!r}")
    return hits


def test_core_boundary_no_hermes_outside_adapter():
    """TC-J65-CORE-001."""
    hits = []
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name in ALLOWED:
            continue
        hits.extend(hermes_touches(path))
    assert not hits, "данные Hermes вне scripts/executors/:\n" + "\n".join(hits)
    # сам адаптер — единственный, кто их знает
    assert hermes_touches(SCRIPTS / "executors" / "hermes.py")


def test_boundary_detector_catches_violation(tmp_path):
    """TC-J65-CORE-001: детектор не ложнозеленый."""
    bad = tmp_path / "bad.py"
    bad.write_text('"""state.db в докстринге не считается."""\n'
                   'import factory_paths as fp\n'
                   'DB = fp.hermes_home() / "state.db"\n'
                   'H = fp.hermes_home\n'
                   'LIVE = H() / "cache" / "delegation" / "live"\n'
                   'LOG = "~/.hermes/logs/errors.log"\n'
                   'OK = "~/.hermes/state"\n'
                   'DB2 = "~/.hermes/state.db"\n'
                   'H2 = Path.home() / ".hermes" / "logs"\n', encoding="utf-8")
    hits = hermes_touches(bad)
    assert sum("hermes_home" in h for h in hits) == 2, hits
    for needle in ("'state.db'", "'cache'", "'delegation'", "'live'",
                   "'errors.log'", "'/.hermes/'"):
        assert any(needle in h for h in hits), (needle, hits)
    assert not any(":7:" in h for h in hits), hits   # state_dir — не Hermes
    assert any(":8:" in h and "state.db" in h for h in hits), hits
    assert any(":9:" in h and "'.hermes'" in h for h in hits), hits


# ------------------------------------------------------------- окружение

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Пустые реестры: HERMES_HOME без state.db, state раннера пуст; вне CI."""
    hermes = tmp_path / "hermes"
    hermes.mkdir()
    state = tmp_path / "state" / "flowctl_state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"runs": {}}), encoding="utf-8")
    monkeypatch.setattr(pv.fp, "hermes_home", lambda: hermes)
    monkeypatch.setattr(pv.fp, "flowctl_state_path", lambda: state)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    return {"hermes": hermes, "state": state}


def hermes_db(home: Path, rows: list[tuple[str, str]]):
    con = sqlite3.connect(home / "state.db")
    con.execute("CREATE TABLE async_delegations (delegation_id TEXT, state TEXT)")
    con.executemany("INSERT INTO async_delegations VALUES (?, ?)", rows)
    con.commit()
    con.close()


def review(d: Path, name: str = "review-001.md", verdict: str = "approve",
           deleg: str | None = DELEG) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    meta = f"Reviewer-Delegation: {deleg}\n" if deleg else ""
    p = d / name
    p.write_text(f"# Ревью\n{meta}\n## Вердикт: {verdict}\n", encoding="utf-8")
    return p


# ------------------------------------------------- CI / вне CI / реестр

def test_no_registry_outside_ci_denies(tmp_path, env, capsys):
    """TC-J65-CORE-002."""
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd)
    out = pv.review_independence_findings(tmp_path / "proj", "add-x", rd)
    assert len(out) == 1 and "fail-closed вне CI" in out[0], out
    assert "SKIPPED" not in capsys.readouterr().err


def test_no_registry_in_ci_unverified(tmp_path, env, capsys, monkeypatch):
    """TC-J65-CORE-002."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd)
    assert pv.review_independence_findings(tmp_path / "proj", "add-x", rd) == []
    err = capsys.readouterr().err
    assert "SKIPPED (независимость ревью)" in err and DELEG in err


def test_no_registry_broken_db_outside_ci_denies(tmp_path, env):
    """TC-J65-CORE-002: битый state.db — недоступный реестр, не PASS."""
    (env["hermes"] / "state.db").write_text("not sqlite", encoding="utf-8")
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd)
    out = pv.review_independence_findings(tmp_path / "proj", "add-x", rd)
    assert out and "fail-closed" in out[0]


def test_missing_meta_denied_even_in_ci(tmp_path, env, monkeypatch):
    """TC-J65-CORE-002: нет ни строки, ни sidecar — отказ и в CI."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd, deleg=None)
    out = pv.review_independence_findings(tmp_path / "proj", "add-x", rd)
    assert out and "нет Reviewer-Delegation и provenance-sidecar" in out[0]


@pytest.mark.parametrize("rows,ok,needle", [
    ([(DELEG, "completed")], True, ""),
    ([(DELEG, "running")], False, "не completed"),
    ([], False, "не найдена в реестре делегаций"),
])
def test_registry_states(tmp_path, env, rows, ok, needle):
    """TC-J65-CORE-003."""
    hermes_db(env["hermes"], rows)
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd)
    out = pv.review_independence_findings(tmp_path / "proj", "add-x", rd)
    assert (out == []) is ok, out
    if needle:
        assert needle in out[0]


def runner_run(deleg: str, role: str, task: str | None = None, **over) -> dict:
    rec = {"delegation_id": deleg, "actor_role": role, "status": "accepted",
           "scope": {"change": "add-x", **({"task": task} if task else {})},
           "package_runner": {"plan": "PLAN-x.md"}}
    rec.update(over)
    return rec


def test_runner_per_task_reviewer_is_not_dev(tmp_path, env):
    """TC-J65-CORE-004."""
    env["state"].write_text(json.dumps({"runs": {
        "d": runner_run(DEV, "dev", task="1.1"),
        "r": runner_run(DELEG, "code_reviewer", task="1.1"),
    }}), encoding="utf-8")
    rd = tmp_path / "proj" / "code-reviews" / "add-x"
    review(rd)
    assert pv.review_independence_findings(tmp_path / "proj", "add-x", rd) == []
    # ревью от делегации разработчика — SELF_REVIEW
    review(rd, deleg=DEV)
    out = pv.review_independence_findings(tmp_path / "proj", "add-x", rd)
    assert out and "SELF_REVIEW" in out[0]


# --------------------------------------------------------------- Флоу 2

def bug_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / "test-model" / "bugs").mkdir(parents=True)
    (repo / "test-model" / "bugs" / "BUG-042.md").write_text(
        "# BUG-042\n\nСтатус: OPEN\n", encoding="utf-8")
    return repo


def test_flow2_requires_review(tmp_path, env):
    """TC-J65-CORE-005."""
    repo = bug_repo(tmp_path)
    out = pv.check_bug(repo, "BUG-042")
    assert out == ["code-reviews/BUG-042/: нет review-файла ревью багфикса "
                   "(Флоу 2, стадия code_review)"]


def test_flow2_last_verdict_must_be_approve(tmp_path, env):
    """TC-J65-CORE-005."""
    hermes_db(env["hermes"], [(DELEG, "completed")])
    repo = bug_repo(tmp_path)
    rd = repo / "code-reviews" / "BUG-042"
    review(rd, "review-001.md", "approve")
    review(rd, "review-002.md", "return")
    out = pv.check_bug(repo, "BUG-042")
    assert len(out) == 1 and "review-002.md" in out[0] and "approve" in out[0]
    review(rd, "review-003.md", "approve")
    assert pv.check_bug(repo, "042") == []


def test_flow2_lowercase_dir_and_independence(tmp_path, env):
    """TC-J65-CORE-005: каталог фабрики bug-042, независимость — как Флоу 1."""
    repo = bug_repo(tmp_path)
    review(repo / "code-reviews" / "bug-042")
    out = pv.check_bug(repo, "BUG-042")
    assert len(out) == 1 and "bug-042/review-001.md" in out[0]
    assert "fail-closed" in out[0]


# ------------------------------------------------------- provenance-sidecar

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def sidecar_repo(tmp_path: Path, **over) -> tuple[Path, Path]:
    repo = bug_repo(tmp_path)
    git(repo, "init", "-q")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
        "--allow-empty", "-m", "base")
    sha = git(repo, "rev-parse", "HEAD")
    rf = review(repo / "code-reviews" / "BUG-042", deleg=None)
    data = {"schema_version": "review-provenance/1", "project": "factory",
            "change": "BUG-042", "task_ids": ["fix"],
            "author_delegation": "claude:author-1",
            "reviewer_delegation": "claude:review-1",
            "reviewed_commit_sha": sha, "diff_digest": "abc", "verdict": "approve"}
    data.update(over)
    Path(str(rf) + ".provenance.json").write_text(json.dumps(data), encoding="utf-8")
    return repo, rf


def test_sidecar_external_agent_skipped_in_ci_denied_outside(tmp_path, env,
                                                            capsys, monkeypatch):
    """TC-J65-CORE-006."""
    repo, _ = sidecar_repo(tmp_path)
    out = pv.check_bug(repo, "BUG-042")
    assert len(out) == 1 and "внешнего агента" in out[0] and "вне CI" in out[0]
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    pv.SKIPPED_REVIEW_CHECKS.clear()
    assert pv.check_bug(repo, "BUG-042") == []
    assert "SKIPPED (независимость ревью)" in capsys.readouterr().err
    assert len(pv.SKIPPED_REVIEW_CHECKS) == 1
    pv.SKIPPED_REVIEW_CHECKS.clear()


@pytest.mark.parametrize("over,needle", [
    ({"reviewer_delegation": "claude:author-1"}, "SELF_REVIEW"),
    ({"verdict": "return"}, "verdict"),
    ({"change": "BUG-099"}, "change"),
    ({"reviewed_commit_sha": "0" * 40}, "нет в репозитории"),
    ({"diff_digest": ""}, "diff_digest"),
    ({"schema_version": "x"}, "schema_version"),
    ({"reviewer_delegation": "просто текст"}, "ни deleg_"),
])
def test_sidecar_rejections(tmp_path, env, over, needle):
    """TC-J65-CORE-006."""
    repo, _ = sidecar_repo(tmp_path, **over)
    out = pv.check_bug(repo, "BUG-042")
    assert len(out) == 1 and needle in out[0], out


def test_sidecar_with_platform_reviewer_checks_registry(tmp_path, env):
    """TC-J65-CORE-006: deleg_… в sidecar проверяется по реестрам."""
    repo, _ = sidecar_repo(tmp_path, reviewer_delegation=DELEG)
    out = pv.check_bug(repo, "BUG-042")
    assert out and "fail-closed" in out[0]
    hermes_db(env["hermes"], [(DELEG, "completed")])
    assert pv.check_bug(repo, "BUG-042") == []


# ----------------------------------------------- архив и вотчдог через адаптер

def test_session_archive_through_adapter(tmp_path, monkeypatch):
    """TC-J65-CORE-007."""
    import factory_paths as fp
    import session_archive as sa
    home = tmp_path / "hermes"
    live = home / "cache" / "delegation" / "live"
    (live / "deleg_a1").mkdir(parents=True)
    (live / "deleg_a1" / "task-0.log").write_text("status=completed\n", encoding="utf-8")
    (live / "deleg_empty").mkdir()
    monkeypatch.setattr(fp, "hermes_home", lambda: home)
    h = executors.get("hermes")
    assert h.finished_runs() == [("deleg_a1", live / "deleg_a1" / "task-0.log")]
    assert h.transcript("deleg_a1") == "status=completed\n"
    assert h.errors_log() == home / "logs" / "errors.log"
    assert ("hermes", "deleg_a1", live / "deleg_a1" / "task-0.log") in sa.finished_runs()
    monkeypatch.setattr(sa, "ARCHIVE_DIR", tmp_path / "archive")
    res = sa.archive_session("deleg_a1", live / "deleg_a1" / "task-0.log")
    assert res["archived"] and res["executor"] == "hermes"
    meta = json.loads((tmp_path / "archive" / "deleg_a1" / "meta.json").read_text(encoding="utf-8"))
    assert meta["deleg_id"] == "deleg_a1" and meta["status"] == "completed"


def test_delegate_watchdog_without_executors(monkeypatch, capsys):
    """TC-J65-CORE-007."""
    import delegate_watchdog as dw
    monkeypatch.setattr(dw, "_hermes", None)
    assert dw.load_delegations() is None
    assert "нет пакета scripts/executors" in capsys.readouterr().err


def test_flow2_scope_slug_and_plain_review_order(tmp_path, env):
    """TC-J65-CORE-008."""
    env["state"].write_text(json.dumps({"runs": {
        "r": {**runner_run(DELEG, "code_reviewer"), "scope": {"change": "BUG-042-fix"}},
    }}), encoding="utf-8")
    assert pv.scope_matches("BUG-042-fix", "BUG-042")
    assert pv.scope_matches("bug-042", "BUG-042")
    assert not pv.scope_matches("BUG-0421", "BUG-042")
    repo = bug_repo(tmp_path)
    rd = repo / "code-reviews" / "BUG-042"
    # review-005.md (без задачи в имени) — итерация 5, позже review-fix-003.md;
    # до правки m5 простое имя получало номер 0 и решал старый return
    review(rd, "review-fix-003.md", "return")
    review(rd, "review-005.md", "approve")
    assert pv.check_bug(repo, "BUG-042") == []
    review(rd, "review-fix-006.md", "return")
    out = pv.check_bug(repo, "BUG-042")
    assert len(out) == 1 and "review-fix-006.md" in out[0], out


def test_scope_match_not_for_change_ids(tmp_path, env):
    """TC-J65-CORE-008: slug-правило только у bug-id (review-002 m7, m9)."""
    assert not pv.scope_matches("bug-tracker-v2", "bug-tracker")
    assert not pv.scope_matches("bug-tracker", "bug-tracker-v2")
    assert not pv.scope_matches("BUG-0420", "BUG-042")
    # review-003 m11: другой баг по грамматике и пустой slug
    for a, b in (("BUG-042-RECHECK-003", "BUG-042"), ("BUG-001-002", "BUG-001"),
                 ("bug-fix-001-v2", "bug-fix-001"), ("BUG-042-", "BUG-042")):
        assert not pv.scope_matches(a, b), (a, b)
        assert not pv.scope_matches(b, a), (b, a)
    assert pv.scope_matches("BUG-AF-RECHECK-003-x", "BUG-AF-RECHECK-003")
    assert pv.scope_matches("bug-026", "BUG-026")
    root = tmp_path / "dirs"
    (root / "code-reviews" / "BUG-042-RECHECK-003").mkdir(parents=True)
    assert pv.bug_review_dir(root, "042") is None
    (root / "code-reviews" / "BUG-042-fix").mkdir()
    assert pv.bug_review_dir(root, "042").name == "BUG-042-fix"
    repo, _ = sidecar_repo(tmp_path, change="BUG-042-fix",
                           reviewer_delegation=DELEG)
    hermes_db(env["hermes"], [(DELEG, "completed")])
    assert pv.check_bug(repo, "BUG-042") == []
