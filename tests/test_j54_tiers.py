# -*- coding: utf-8 -*-
"""J54: эшелонированный регресс — tier smoke, baseline, xdist, factory_init.

Эшелоны (решение Заказчика 2026-10-18, backlog J54): полный regress НЕ на
каждый change; change = доменный regress (эшелон 1) + cross-domain smoke
(эшелон 2); regress-final (эшелон 3) — пакетно перед плановым деплоем.

  TC-J54-001  --tier smoke: манифеста нет → WARN, exit 0 (дефолт пустого
              контура), артефакт с пометкой
  TC-J54-002  --tier smoke: манифест пуст (suites: []) → WARN, exit 0
  TC-J54-003  --tier smoke: манифест с сьютами → PASS, время прогона (duration)
              и tier в артефакте; сьют, которого нет, — suites_skipped
  TC-J54-004  --tier smoke: падение → FAIL, exit 1
  TC-J54-005  baseline: тест из baseline падает → вердикт НЕ краснится
              (PASS, exit 0), в артефакте «baseline: ожидаемо-падающий
              (reason)»
  TC-J54-006  baseline: неожиданное падение краснит (FAIL) даже при фоне
  TC-J54-007  --final ИГНОРИРУЕТ baseline: падающий из baseline → FAIL
  TC-J54-008  --suggest-baseline: упавшие (не из baseline) дописываются в
              baseline-suggestions.json с заполнителем reason; повтор —
              без дублей; baseline.json НЕ меняется
  TC-J54-009  --xdist N: в argv pytest добавлен -n N; в артефакте
              предупреждение о детерминированности (xdist)
  TC-J54-010  regress_pytest_args: -rf для baseline-сверки; -n N при --xdist;
              parse_failed_tests читает короткую сводку -rf
  TC-J54-011  factory_init: скелеты tests/smoke_cross/README.md,
              test-model/smoke-cross/manifest.json (пустой),
              test-model/regress-domains.json (пустой),
              test-model/regress/baseline.json ([]); идемпотентны (контент
              проекта без --force не перезаписывается)
  TC-J54-012  load_domain_map: скелет {"rules": []} — не «error», дефолт
              применяется (пустая карта — легитимное состояние нового проекта)
  TC-J54-013  regress (эшелон 1) без изменений прежних контрактов: артефакт
              содержит tier/duration, доменный прогон PASS
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
SCRIPTS = FACTORY / "scripts"
for p in (str(SCRIPTS),):
    if p not in sys.path:
        sys.path.insert(0, p)

import factory_init  # noqa: E402
import flowctl  # noqa: E402


# --------------------------------------------------------------- helpers

def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    return r.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit_all(repo: Path, msg: str = "init") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def stage(repo: Path, rel: str, text: str) -> None:
    """Дифф в индексе (staged) — источник regress эшелона 1."""
    write(repo, rel, text)
    git(repo, "add", rel.replace("\\", "/"))


def make_repo(tmp_path: Path) -> Path:
    """Минимальный git-репозиторий: smoke-сьют и домен tests/web.
    tmp_path/proj уже создан autouse-фикстурой plan_release_fixture
    (tests/conftest.py, J41) — exist_ok обязателен."""
    repo = tmp_path / "proj"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    write(repo, "README.md", "# r\n")
    write(repo, "tests/web/test_ok.py", "def test_ok():\n    assert True\n")
    write(repo, "tests/smoke_cross/.keep", "")
    commit_all(repo)
    return repo


def set_baseline(repo: Path, entries: list[dict]) -> None:
    write(repo, flowctl.REGRESS_BASELINE_REL, json.dumps(entries))


def set_manifest(repo: Path, suites: list[str]) -> None:
    write(repo, flowctl.SMOKE_CROSS_MANIFEST_REL,
          json.dumps({"suites": suites}, ensure_ascii=False))


def regress(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "flowctl.py"), "regress",
         "--repo", str(repo), "--change", "j54-demo", "--json", *extra],
        capture_output=True, text=True,
    )


def artifact_of(result: subprocess.CompletedProcess) -> str:
    return Path(json.loads(result.stdout)["artifact"]).read_text(
        encoding="utf-8")


BASELINE_ENTRY = {"test": "tests/web/test_bad.py::test_bg",
                  "reason": "известный фон main (ISSUE-77)",
                  "added": "2026-10-18"}


# --------------------------------------------------- эшелон 2: tier smoke

class TestTierSmoke:
    def test_smoke_without_manifest_is_warn_exit0(self, tmp_path):
        """TC-J54-001: каталога/манифеста smoke-cross нет → WARN и exit 0
        (дефолт: контур не настроен — легитимное состояние), пометка в
        артефакте."""
        repo = make_repo(tmp_path)
        r = regress(repo, "--tier", "smoke")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "WARN"
        assert data["tier"] == "smoke"
        assert data["suites"] == []
        assert data["pytest_exit"] is None
        text = artifact_of(r)
        assert "verdict: WARN" in text
        assert "tier: smoke (эшелон 2: cross-domain smoke)" in text
        assert "smoke-контур не настроен" in text

    def test_smoke_empty_manifest_is_warn_exit0(self, tmp_path):
        """TC-J54-002: манифест есть, suites пуст (скелет factory_init) →
        WARN и exit 0, прогон не выполнялся."""
        repo = make_repo(tmp_path)
        set_manifest(repo, [])
        r = regress(repo, "--tier", "smoke")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "WARN"
        assert data["suites"] == []
        assert "suites: []" in data["smoke_manifest"]

    def test_smoke_with_manifest_pass_duration_in_artifact(self, tmp_path):
        """TC-J54-003: манифест с сьютами → прогон, PASS; время прогона
        (duration) и tier в артефакте. Сьют без каталога — suites_skipped и
        WARN (частичное покрытие манифеста не молчит)."""
        repo = make_repo(tmp_path)
        set_manifest(repo, ["tests/web"])
        r = regress(repo, "--tier", "smoke")
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["suites"] == ["tests/web"]
        assert data["suites_skipped"] == []
        assert data["duration_s"] is not None
        text = artifact_of(r)
        assert "duration:" in text and "duration: —" not in text
        assert "tier: smoke" in text
        assert "smoke manifest: манифест" in text
        assert "1 passed" in text  # факт прогона в хвосте лога
        # сьют манифеста без каталога → WARN (не молчаливый прогон части)
        set_manifest(repo, ["tests/web", "tests/missing_domain"])
        r2 = regress(repo, "--tier", "smoke")
        assert r2.returncode == 0
        data2 = json.loads(r2.stdout)
        assert data2["verdict"] == "WARN"
        assert data2["suites_skipped"] == ["tests/missing_domain"]

    def test_smoke_failure_fails(self, tmp_path):
        """TC-J54-004: падение в smoke-сьютах → FAIL, exit 1."""
        repo = make_repo(tmp_path)
        write(repo, "tests/web/test_bad.py",
              "def test_bg():\n    assert False\n")
        set_manifest(repo, ["tests/web"])
        r = regress(repo, "--tier", "smoke")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "FAIL"
        assert data["failed_tests"] == ["tests/web/test_bad.py::test_bg"]


# --------------------------------------------------------------- baseline

class TestBaseline:
    def test_baseline_failure_does_not_redden(self, tmp_path):
        """TC-J54-005: тест из baseline падает на regress → вердикт PASS
        (не краснится), exit 0; в артефакте «baseline: ожидаемо-падающий
        (reason)»; в payload baseline.skipped."""
        repo = make_repo(tmp_path)
        write(repo, "tests/web/test_bad.py",
              "def test_bg():\n    assert False\n")
        set_baseline(repo, [BASELINE_ENTRY])
        stage(repo, "scripts/x.py", "A = 1\n")  # дифф → домен tests/
        r = regress(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["pytest_exit"] == 1  # падение было — но фон
        assert data["baseline"]["skipped"] == [
            {"test": BASELINE_ENTRY["test"],
             "reason": BASELINE_ENTRY["reason"]}]
        text = artifact_of(r)
        assert ("baseline: ожидаемо-падающий "
                "(известный фон main (ISSUE-77))") in text

    def test_unexpected_failure_reddens_despite_baseline(self, tmp_path):
        """TC-J54-006: неожиданное падение краснит (FAIL) даже при непустом
        baseline; ожидаемый фон при этом помечен отдельно."""
        repo = make_repo(tmp_path)
        write(repo, "tests/web/test_bad.py",
              "def test_bg():\n    assert False\n")
        write(repo, "tests/web/test_new.py",
              "def test_new():\n    assert 0\n")
        set_baseline(repo, [BASELINE_ENTRY])
        stage(repo, "scripts/x.py", "A = 1\n")
        r = regress(repo)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "FAIL"
        assert data["baseline"]["skipped"] != []
        assert data["failed_tests"] == [
            "tests/web/test_bad.py::test_bg", "tests/web/test_new.py::test_new"]

    def test_final_ignores_baseline(self, tmp_path):
        """TC-J54-007: regress --final игнорирует baseline — полный честный
        прогон: падающий из baseline краснит (FAIL), note в артефакте,
        baseline не меняется."""
        repo = make_repo(tmp_path)
        write(repo, "tests/web/test_bad.py",
              "def test_bg():\n    assert False\n")
        set_baseline(repo, [BASELINE_ENTRY])
        stage(repo, "scripts/x.py", "A = 1\n")
        r = regress(repo, "--final")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["verdict"] == "FAIL"
        assert data["baseline"]["ignored"] is True
        text = artifact_of(r)
        assert "baseline ИГНОРИРУЕТСЯ" in text
        assert "покраснели наравне с остальными" in text
        assert "ожидаемо-падающий" not in text

    def test_suggest_baseline_appends_without_dup(self, tmp_path):
        """TC-J54-008: --suggest-baseline дописывает упавших (не из baseline)
        в baseline-suggestions.json с заполнителем reason; повторный прогон —
        без дублей; baseline.json не меняется."""
        repo = make_repo(tmp_path)
        write(repo, "tests/web/test_bad.py",
              "def test_bg():\n    assert False\n")   # в baseline
        write(repo, "tests/web/test_new.py",
              "def test_new():\n    assert 0\n")       # неожиданное
        set_baseline(repo, [BASELINE_ENTRY])
        stage(repo, "scripts/x.py", "A = 1\n")
        r = regress(repo, "--suggest-baseline")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["suggest_baseline"]["added"] == [
            "tests/web/test_new.py::test_new"]
        sug_path = repo / flowctl.REGRESS_BASELINE_SUGGESTIONS_REL
        assert sug_path.is_file()
        sug = json.loads(sug_path.read_text(encoding="utf-8"))
        assert len(sug) == 1
        assert sug[0]["test"] == "tests/web/test_new.py::test_new"
        assert "ПМ переносит" in sug[0]["reason"]
        # baseline.json не тронут:
        assert json.loads(
            (repo / flowctl.REGRESS_BASELINE_REL).read_text(
                encoding="utf-8")) == [BASELINE_ENTRY]
        # повтор — дедуп:
        r2 = regress(repo, "--suggest-baseline")
        assert r2.returncode == 1
        sug2 = json.loads(sug_path.read_text(encoding="utf-8"))
        assert len(sug2) == 1
        # секция в артефакте:
        assert "## Suggestions для baseline" in artifact_of(r)


# ------------------------------------------------------------------ xdist

class TestXdist:
    def test_pytest_args_xdist_and_rf(self):
        """TC-J54-010 (unit): regress_pytest_args — -rf всегда; -n N при
        xdist; parse_failed_tests читает короткую сводку -rf."""
        args = flowctl.regress_pytest_args(["tests/web"])
        assert args[-3:] == ["tests/web", "-q", "-rf"]
        assert "-n" not in args
        args4 = flowctl.regress_pytest_args(["tests"], xdist=4)
        assert args4[-2:] == ["-n", "4"]
        assert flowctl.parse_failed_tests(
            "x\nFAILED tests/web/test_bad.py::test_bg - assert False\n"
            "FAILED tests/web/test_bad.py::test_bg - dup\n") == \
            ["tests/web/test_bad.py::test_bg"]

    def test_xdist_flag_warning_in_artifact(self, tmp_path, monkeypatch,
                                            capsys):
        """TC-J54-009: --xdist N → `-n N` в argv pytest (subprocess замокан —
        плагин в тест-окружении фабрики не установлен); в артефакте
        предупреждение о детерминированности; в payload xdist."""
        repo = make_repo(tmp_path)
        stage(repo, "scripts/x.py", "A = 1\n")
        captured = {}

        def fake_run(argv, **kw):
            captured["argv"] = argv
            return subprocess.CompletedProcess([], 0, "1 passed in 0.01s\n", "")

        monkeypatch.setattr(flowctl.subprocess, "run", fake_run)
        rc = flowctl.main(["regress", "--repo", str(repo),
                           "--change", "j54-demo", "--xdist", "4", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["xdist"] == 4
        argv = captured["argv"]
        assert argv[argv.index("-n") + 1] == "4"
        text = Path(data["artifact"]).read_text(encoding="utf-8")
        assert "xdist: pytest -n 4 (pytest-xdist)" in text
        assert "не должны делиться между воркерами" in text


# ------------------------------------------------- factory_init: скелеты

class TestFactoryInitSkeletons:
    def test_factory_init_creates_regress_skeletons(self, tmp_path):
        """TC-J54-011: factory_init ставит tests/smoke_cross/README.md,
        пустой манифест smoke-cross, пустой regress-domains.json и
        baseline.json = []; повторный init контент проекта не трогает."""
        repo = tmp_path / "proj"
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        write(repo, "README.md", "# r\n")
        commit_all(repo)
        subprocess.run(
            [sys.executable, str(SCRIPTS / "factory_init.py"),
             "--target", str(repo), "--name", "T", "--skip-plugin"],
            capture_output=True, text=True,
        )
        readme = repo / factory_init.SMOKE_CROSS_README_REL
        assert readme.is_file()
        assert "эшелон 2" in readme.read_text(encoding="utf-8")
        manifest = repo / factory_init.SMOKE_CROSS_MANIFEST_REL
        assert json.loads(manifest.read_text(encoding="utf-8")) == {
            "suites": []}
        domains = repo / factory_init.REGRESS_DOMAINS_REL
        assert json.loads(domains.read_text(encoding="utf-8")) == {"rules": []}
        baseline = repo / factory_init.REGRESS_BASELINE_REL
        assert json.loads(baseline.read_text(encoding="utf-8")) == []
        # скелеты работают end-to-end: smoke по пустому манифесту — WARN;
        # regress-domains-скелет не дает «error» в domain map
        r = regress(repo, "--tier", "smoke")
        assert r.returncode == 0
        assert json.loads(r.stdout)["verdict"] == "WARN"
        # идемпотентность: контент проекта не перезаписывается
        set_baseline(repo, [{"test": "t::x", "reason": "r", "added": "d"}])
        set_manifest(repo, ["tests/web"])
        subprocess.run(
            [sys.executable, str(SCRIPTS / "factory_init.py"),
             "--target", str(repo), "--name", "T", "--skip-plugin"],
            capture_output=True, text=True,
        )
        assert json.loads(
            (repo / factory_init.REGRESS_BASELINE_REL).read_text(
                encoding="utf-8")) != []
        assert json.loads(
            (repo / factory_init.SMOKE_CROSS_MANIFEST_REL).read_text(
                encoding="utf-8")) == {"suites": ["tests/web"]}

    def test_empty_domain_map_skeleton_is_not_error(self, tmp_path):
        """TC-J54-012: скелет {"rules": []} — легитимная пустая карта
        (дефолт без «error»-диагностики в исходе regress)."""
        repo = make_repo(tmp_path)
        write(repo, flowctl.REGRESS_DOMAIN_MAP_REL, '{"rules": []}')
        rules, note = flowctl.load_domain_map(repo)
        assert rules == ()
        assert "error" not in note
        assert "задана" in note


# ------------------------------------------------ контракт эшелона 1 цел

class TestDomainTierUnchanged:
    def test_domain_tier_artifact_fields(self, tmp_path):
        """TC-J54-013: regress по умолчанию — эшелон 1: прежние контракты
        (PASS, suites, diff source) + новые поля tier/duration в артефакте."""
        repo = make_repo(tmp_path)
        stage(repo, "scripts/x.py", "A = 1\n")
        r = regress(repo)
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(r.stdout)
        assert data["verdict"] == "PASS"
        assert data["tier"] == "domain"
        assert data["suites"] == ["tests"]
        assert data["duration_s"] is not None
        text = artifact_of(r)
        assert "tier: domain (эшелон 1: доменный regress)" in text
        assert "duration:" in text
        assert "diff source: git diff --cached (staged)" in text
