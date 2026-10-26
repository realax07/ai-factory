# -*- coding: utf-8 -*-
"""J52-w3: gate self-test harness — CI-имитация для ворот конвейера.

Превентивная мера 1 из J52 (поручение Заказчика 2026-10-18, раздел
«Обкатка ворот» backlog/J51-*.md): ворота тестируются в комфортной среде
автора, а работают в CI-среде — класс BUG-022/023/024 (у автора PASS,
в CI ложный STALE/UNKNOWN) и инцидент J53 (test_d_e2e пад в CI: openspec
CLI отсутствует на раннере — FileNotFoundError вместо graceful-деградации).

Harness-имитация CI-среды:
  - shallow-клон (`git clone --depth 1`) реального эталонного tmp-репо
    с полным набором артефакт change-пакета (как actions/checkout
    fetch-depth 1);
  - чистый env (подход env -i): минимальный PATH (только python/git),
    чистый HOME (нет ~/ai-factory и ~/.hermes), нет GITHUB_* (в т.ч.
    GITHUB_EVENT_PATH — как в workflow, env -u), нет VIRTUAL_ENV/
    PYTHONPATH/локальных путей; openspec в PATH отсутствует;
  - ворота (pr_validate, flow_check, factory_init) запускаются
    САБПРОЦЕССОМ в этой среде — как CI-шаг, не импортом в комфортный
    процесс pytest.

Эталонные кейсы (ожидаемый результат ворот):
  TC-J52-030  pass-репо: pr_validate в shallow-клоне — OK, предок
              верифицирован через тихий unshallow (ветка BUG-022);
  TC-J52-031  pass-репо: flow_check в чистом env — OK;
  TC-J52-032  stale-артефакт: commit не предок HEAD → REGRESS_FINAL_STALE;
  TC-J52-033  missing-артефакт: regress-final удален → REGRESS_FINAL_MISSING;
  TC-J52-034  J53-класс: factory_init без openspec CLI в чистом env —
              graceful-деградация (явный WARNING, без FileNotFoundError);
  TC-J52-035  контроль имитации: env действительно чистый (нет GITHUB_*, HOME
              пуст, ~/ai-factory нет, openspec не резолвится) — страж от
              протечки комфортной среды в harness;
  TC-J52-036  fresh-ось (BUG-023/024): мета-коммит code-reviews/** после
              regress-final → PASS (на пре-фиксном pr_validate — ложный
              STALE);
  TC-J52-037  fresh-ось, позитивный контроль: продуктовый tests/** после
              артефакта → STALE (правка после прогона = перегон).

Эталонные коммиты датированы (GIT_AUTHOR/COMMITTER_DATE, NOW минус N
минут, шаг ≥60с): без дат секундная гранулярность схлопывает fresh-сверку
`ts > art_ts` и ось BUG-023/024 непроверяема (review-005 major #1).

Регресс обязателен в CI: harness входит в `pytest tests/` шага Run tests
job test-flow-control (.github/workflows/flow.yml) — конвейер сам
обкатывает свои ворота в CI-условиях до merge (отдельный шаг не несет
отдельного env-контекста — review-005 minor #2).
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"

CHANGE = "add-widget"

# Эталонный requirements.md: преамбула ответственности (контракт 1, C1)
# + 7 обязательных разделов (контракт 1, E3).
REQ_TEXT = """# Requirements {change}

> Статус: черновик r1 | Автор: ba_agent | История: r1

## Описание
Нужен виджет.

## Аудитория
Пользователи проекта.

## Функциональные требования
- **FR-1** виджет работает

## Нефункциональные требования
- **NFR-1** отклик быстрый

## Приоритеты
FR-1 — must.

## Ограничения
Python 3.

## Открытые вопросы
Нет.
""".format(change=CHANGE)

REVIEW_META = "Reviewer-Delegation: deleg_harnessreviewer0001\n"


# Эталонные коммиты датированы (review-005 major #1): шаг ≥60с разносит
# %ct коммитов — fresh-сверка ворот `ts > art_ts` на секундной гранулярности
# схлопывалась в равенство, и свежестная ось (BUG-023/024) была непроверяема.
def ts(minutes_ago: int) -> str:
    """GIT_AUTHOR/COMMITTER_DATE: NOW минус N минут (ISO 8601)."""
    return (datetime.now() - timedelta(minutes=minutes_ago)) \
        .strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True, env=env)
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str, date: str | None = None) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg, date=date)
    return git(repo, "rev-parse", "HEAD")


def make_origin(base: Path) -> tuple[Path, str]:
    """Эталонное origin-репо: main — база; ветка feature/add-widget —
    change-пакет (h1, NOW-8) и regress-final с commit=h1 (h2, NOW-6).
    Коммиты датированы с шагом ≥60с (review-005 major #1): fresh-сверка
    ворот `ts > art_ts` требует разнесенных таймстампов — при секундной
    гранулярности все сравнения схлопываются в равенство и fresh-ось
    (BUG-023/024) непроверяема. Как реальный PR: прогон regress_runner
    удостоверяет h1, артефакт коммитится после (мета-коммит h2), CI
    чекаутит ветку shallow."""
    origin = base / "origin"
    origin.mkdir(parents=True)
    git(origin, "init", "-q", "-b", "main")
    write(origin, "README.md", "# p\n")
    commit_all(origin, "init", date=ts(10))

    git(origin, "checkout", "-q", "-b", f"feature/{CHANGE}")
    write(origin, "requirements.md", REQ_TEXT)
    write(origin, f"openspec/changes/{CHANGE}/requirements.md", REQ_TEXT)
    write(origin, f"openspec/changes/{CHANGE}/proposal.md", "# proposal\n")
    write(origin, f"openspec/changes/{CHANGE}/design.md", "# design\n")
    # J58: impact-карта — обязательный артефакт change-пакета (ворота
    # pr_validate DENY-ят change-PR без нее); эталон «green»-репо обязан
    # ей обладать, как proposal/tasks/reviews.
    write(origin, f"openspec/changes/{CHANGE}/impact.md",
          f"# Impact — {CHANGE}\n\n## Затронутые сервисы\n\n—\n")
    write(origin, f"openspec/changes/{CHANGE}/sdd.md", "# sdd\n")
    write(origin, f"openspec/changes/{CHANGE}/tasks.md",
          "# Tasks\n\n- [x] 1.1 сделано\n")
    write(origin, f"openspec/changes/{CHANGE}/specs/widget/spec.md",
          "## ADDED Requirements\n\n### Requirement: Виджет\n\n"
          "#### Scenario: работает\n\n- WHEN вызов\n- THEN ответ\n")
    write(origin, f"test-model/approved/{CHANGE}/TC-ADD-001.md",
          "# Кейс TC-ADD-001 (одобрить)\n")
    write(origin, f"test-model/reviews/{CHANGE}/review-001-1.1.md",
          f"# Review {CHANGE}\n\n## Вердикт: approve (одобрить)\n\n{REVIEW_META}")
    write(origin, f"code-reviews/{CHANGE}/review-001-1.1.md",
          f"# Review-00001\n\n## Вердикт: approve\n\n{REVIEW_META}")
    write(origin, "tests/test_smoke.py",
          "def test_widget():\n"
          "    assert True  # TC-ADD-001 трассировка\n")
    c_run = commit_all(origin, "change package", date=ts(8))

    write(origin, f"test-model/regress/{CHANGE}/regress-final.md",
          f"# Regress {CHANGE} — regress-final.md\n\n"
          f"- change: {CHANGE}\n"
          f"- date: {ts(5)}\n"
          f"- commit: {c_run}\n"
          "- verdict: PASS\n")
    commit_all(origin, "regress final", date=ts(6))
    return origin, c_run


def shallow_clone_ci(origin: Path, dest: Path) -> Path:
    """CI-имитация actions/checkout (fetch-depth 1): shallow-клон ветки PR."""
    r = subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "-b", f"feature/{CHANGE}",
         f"file://{origin}", str(dest)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    is_shallow = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True)
    assert is_shallow.stdout.strip() == "true"
    return dest


def ci_env(home: Path) -> dict[str, str]:
    """Чистый env (подход env -i): минимальный PATH, чистый HOME,
    никаких GITHUB_*/локальных путей. openspec намеренно НЕ резолвится."""
    dirs: list[str] = []
    for name in ("python3", "python", "git"):
        p = shutil.which(name)
        if p:
            dirs.append(str(Path(p).resolve().parent))
    return {
        "PATH": ":".join(dict.fromkeys(dirs)) or "/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def run_gate(script: str, *args: str, home: Path) -> subprocess.CompletedProcess:
    """Запуск ворот САБПРОЦЕССОМ в CI-имитации (как CI-шаг, не импорт)."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=ci_env(home))


@pytest.fixture()
def ci_home(tmp_path: Path) -> Path:
    """Чистый HOME раннера: без ~/ai-factory и ~/.hermes."""
    home = tmp_path / "runner-home"
    home.mkdir()
    return home


@pytest.fixture()
def green(tmp_path: Path) -> tuple[Path, str]:
    """Эталонный origin (pass-репо) + commit прогона."""
    return make_origin(tmp_path)


# ------------------------------------------------------- эталонные кейсы

class TestHarnessPass:
    def test_pr_validate_pass_in_shallow_clone(
            self, green, ci_home, tmp_path):
        """TC-J52-030: pass-репо, shallow-клон, чистый env: pr_validate —
        OK; commit прогона (не HEAD) верифицирован как предок через тихий
        unshallow — ветка фикса BUG-022 работает в CI-условиях."""
        origin, c_run = green
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        r = run_gate("pr_validate.py", str(clone), "--id", f"[{CHANGE}]",
                     home=ci_home)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PR-VALIDATE OK" in r.stdout
        # unshallow реально отработал в среде без GITHUB_* — история
        # полная, commit прогона присутствует (merge-base мог сверить)
        probe = subprocess.run(
            ["git", "-C", str(clone), "cat-file", "-e", c_run],
            capture_output=True, text=True)
        assert probe.returncode == 0, "commit прогона не в истории после ворот"

    def test_flow_check_pass_in_clean_env(self, green, ci_home, tmp_path):
        """TC-J52-031: pass-репо, shallow-клон, чистый env (нет
        ~/ai-factory — factory-sync сверка молчит, нет openspec):
        flow_check — OK, exit 0."""
        origin, _ = green
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        r = run_gate("flow_check.py", str(clone), home=ci_home)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "flow_check: OK" in r.stdout


class TestHarnessNegative:
    def test_stale_artifact_foreign_commit(self, green, ci_home, tmp_path):
        """TC-J52-032: stale-артефакт — commit артефакта чужой (не предок
        HEAD) → REGRESS_FINAL_STALE, exit 1 в CI-имитации."""
        origin, _ = green
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        art = clone / "test-model" / "regress" / CHANGE / "regress-final.md"
        art.write_text(
            f"# Regress {CHANGE} — regress-final.md\n\n"
            f"- change: {CHANGE}\n- date: 2026-10-18T12:00:00+00:00\n"
            f"- commit: {'d' * 40}\n- verdict: PASS\n", encoding="utf-8")
        r = run_gate("pr_validate.py", str(clone), "--id", f"[{CHANGE}]",
                     home=ci_home)
        assert r.returncode == 1
        assert "REGRESS_FINAL_STALE" in r.stdout
        assert "не является его предком" in r.stdout

    def test_missing_artifact(self, green, ci_home, tmp_path):
        """TC-J52-033: missing-артефакт — regress-final отсутствует →
        REGRESS_FINAL_MISSING, exit 1 в CI-имитации."""
        origin, _ = green
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        (clone / "test-model" / "regress" / CHANGE /
         "regress-final.md").unlink()
        r = run_gate("pr_validate.py", str(clone), "--id", f"[{CHANGE}]",
                     home=ci_home)
        assert r.returncode == 1
        assert "REGRESS_FINAL_MISSING" in r.stdout


# --------------------------------------------------- класс J53 (openspec)

class TestHarnessJ53Class:
    def test_factory_init_without_openspec_degrades(
            self, ci_home, tmp_path):
        """TC-J52-034: заранее известный класс J53 (test_d_e2e пад в CI:
        openspec CLI отсутствует на раннере → FileNotFoundError). Harness
        воспроизводит среду: factory_init обязан деградировать graceful —
        явный WARNING-контракт J53-фикса, не крэш; e2e-глоссарий создан."""
        repo = tmp_path / "proj"
        # autouse-фикстура conftest (J41) уже создала каталог и подложила PLAN
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        r = run_gate("factory_init.py", "--target", str(repo),
                     "--name", "Harness Fixture", "--skip-plugin",
                     home=ci_home)
        # Контракт J53-фикса: отсутствие openspec CLI — WARNING, не крэш:
        # явное сообщение, все артефакты созданы, exit 1 «С ПРЕДУПРЕЖДЕНИЯМИ»
        # (ok=False по дизайну), НЕТ FileNotFoundError-traceback.
        assert "НЕ найден" in r.stdout  # graceful-деградация, не traceback
        assert "ЗАВЕРШЕН С ПРЕДУПРЕЖДЕНИЯМИ" in r.stdout
        assert r.returncode == 1, r.stdout + r.stderr
        assert "Traceback" not in r.stderr
        assert "FileNotFoundError" not in r.stderr
        assert (repo / "docs" / "glossary.md").is_file()


# ------------------------------------------- fresh-ось (BUG-023/024)

class TestHarnessFreshAxis:
    def test_meta_commit_after_artifact_passes(self, green, ci_home,
                                               tmp_path):
        """TC-J52-036: мета-коммит (code-reviews/**) ПОСЛЕ regress-final →
        PASS (exit 0). Датированные коммиты делают fresh-сверку разрешимой:
        мета исключена (BUG-023/024), продуктовых правок после прогона нет.
        На пре-фиксных pr_validate (596d262~1: BUG-023, 12496ec~1: BUG-024)
        тот же кейс дает ложный REGRESS_FINAL_STALE — регрессия исключений
        мета-путей ловится (на старом make_origin без дат — 3/3 passed)."""
        origin, _ = green
        write(origin, f"code-reviews/{CHANGE}/review-002-1.1.md",
              f"# Review-00002\n\n## Вердикт: approve\n\n{REVIEW_META}")
        commit_all(origin, "meta: code review after regress", date=ts(2))
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        r = run_gate("pr_validate.py", str(clone), "--id", f"[{CHANGE}]",
                     home=ci_home)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PR-VALIDATE OK" in r.stdout

    def test_product_commit_after_artifact_stale(self, green, ci_home,
                                                 tmp_path):
        """TC-J52-037: продуктовый коммит (tests/**) ПОСЛЕ regress-final →
        REGRESS_FINAL_STALE (exit 1) — позитивный контроль fresh-ветки
        ворот: commit предок HEAD (ancestry проходит), но файл новее
        прогона (ts > art_ts) — датированные коммиты делают сверку
        осмысленной, правка после прогона = перегон."""
        origin, _ = green
        write(origin, "tests/test_widget_extra.py",
              "def test_widget_extra():\n    assert True\n")
        commit_all(origin, "tests: touch after regress", date=ts(2))
        clone = shallow_clone_ci(origin, tmp_path / "ci-clone")
        r = run_gate("pr_validate.py", str(clone), "--id", f"[{CHANGE}]",
                     home=ci_home)
        assert r.returncode == 1
        assert "REGRESS_FINAL_STALE" in r.stdout
        assert "старше последнего касания" in r.stdout


# ------------------------------------------- контроль чистоты имитации

class TestHarnessSelfCheck:
    def test_ci_env_is_really_clean(self, ci_home):
        """TC-J52-035: страж имитации — env действительно чистый: нет
        GITHUB_*, HOME — пустой раннерный каталог (~/ai-factory и
        ~/.hermes отсутствуют), openspec не резолвится. Иначе harness
        тихо тестирует ворота в комфортной среде автора — тот самый
        класс, против которого построен."""
        probe = (
            "import json, os, shutil, sys\n"
            "from pathlib import Path\n"
            "print(json.dumps({\n"
            "    'github': sorted(k for k in os.environ"
            " if k.startswith('GITHUB_')),\n"
            "    'home': os.environ.get('HOME', ''),\n"
            "    'factory': (Path.home() / 'ai-factory').exists(),\n"
            "    'hermes': (Path.home() / '.hermes').exists(),\n"
            "    'openspec': shutil.which('openspec'),\n"
            "    'virtualenv': os.environ.get('VIRTUAL_ENV', ''),\n"
            "}))\n"
        )
        r = subprocess.run([sys.executable, "-c", probe],
                           capture_output=True, text=True,
                           env=ci_env(ci_home))
        assert r.returncode == 0, r.stderr
        import json
        fact = json.loads(r.stdout)
        assert fact["github"] == [], fact["github"]
        assert Path(fact["home"]) == ci_home
        assert fact["factory"] is False
        assert fact["hermes"] is False
        assert fact["openspec"] is None
        assert fact["virtualenv"] == ""
