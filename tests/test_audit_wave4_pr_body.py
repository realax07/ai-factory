# -*- coding: utf-8 -*-
"""АУД-4 хвост (волна 4): pr_body-требования в DENY-воротах check_impact_rules.

IR-05 (Н20): дифф Dockerfile → в теле PR «docker build» (верификация сборкой,
не маунтом). IR-06 (Н25): докачка контент-ассетов → URL+sha256 в теле PR.
Тело PR читается из env PR_BODY либо fetch_pr_info (GITHUB_EVENT_PATH);
без PR-контекста — SKIP. Триггер IR-06 уточняется content_when по патчу диффа.

Трассировка (rule 6):
  TC-AUD-201  IR-05: Dockerfile-дифф, тело БЕЗ «docker build» — DENY
  TC-AUD-202  IR-05: тело С «docker build» — PASS
  TC-AUD-203  нет PR-контекста (ни PR_BODY, ни GITHUB_EVENT_PATH) — SKIP
  TC-AUD-204  IR-06: патч Dockerfile с ffmpeg-URL, тело без sha — DENY
  TC-AUD-205  IR-06: тело с sha256 — PASS
  TC-AUD-206  IR-06 precision: Dockerfile без докачки ассетов — правило молчит
  TC-AUD-207  тело из GITHUB_EVENT_PATH (CI-событие) — проверяется
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import pr_validate  # noqa: E402

DOCKERFILE = "services/api/Dockerfile"


def rules_file(repo: Path, rule_id: str) -> None:
    """Фабричный impact_rules.json, суженный до одного правила (изоляция)."""
    factory = json.loads(
        (FACTORY / "scripts" / "impact_rules.json").read_text(encoding="utf-8"))
    rule = next(r for r in factory["rules"] if r["id"] == rule_id)
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "impact_rules.json").write_text(
        json.dumps({"version": factory["version"], "rules": [rule]},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")


def make_repo(tmp_path: Path, rule_id: str, dockerfile_body: str) -> Path:
    """Git-репо: main (база) + ветка HEAD с Dockerfile (патч читаем)."""
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    rules_file(repo, rule_id)
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True, text=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feature/dockerfile")
    p = repo / DOCKERFILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dockerfile_body, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "dockerfile")
    return repo


@pytest.fixture(autouse=True)
def clean_pr_context(monkeypatch):
    """Ни PR_BODY, ни GITHUB_EVENT_PATH — вне теста контекста нет (SKIP)."""
    monkeypatch.delenv("PR_BODY", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)


# TC-AUD-201: IR-05 — Dockerfile-дифф без «docker build» в теле = DENY
def test_ir05_dockerfile_without_docker_build_denied(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    rules_file(repo, "IR-05")
    monkeypatch.setenv("PR_BODY", "обновил докерфайл, стенд-маунт зелен")
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert len(errs) == 1 and "IR-05" in errs[0] and "docker build" in errs[0]


# TC-AUD-202: IR-05 — тело с «docker build» = PASS
def test_ir05_with_docker_build_passes(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    rules_file(repo, "IR-05")
    monkeypatch.setenv("PR_BODY", "верификация: docker build -t api . — ok")
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert errs == []


# TC-AUD-203: нет PR-контекста — SKIP (требование молчит)
def test_no_pr_context_skips(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    rules_file(repo, "IR-05")
    assert pr_validate._pr_body_text() is None
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert errs == []


# TC-AUD-204: IR-06 — ffmpeg-URL в патче, тело без sha = DENY
def test_ir06_ffmpeg_without_sha_denied(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, "IR-06",
                     "FROM debian\nRUN curl -L https://johnvansickle.com/ffmpeg/"
                     "releases/ffmpeg-amd64-static.tar.xz -o /tmp/f.tar.xz\n")
    monkeypatch.setenv("PR_BODY", "докачал ffmpeg, проверено на стене")
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert len(errs) == 1 and "IR-06" in errs[0] and "sha256" in errs[0]


# TC-AUD-205: IR-06 — тело с sha256 = PASS
def test_ir06_with_sha_passes(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, "IR-06",
                     "FROM debian\nRUN curl -L https://johnvansickle.com/ffmpeg/"
                     "releases/ffmpeg-amd64-static.tar.xz -o /tmp/f.tar.xz\n")
    monkeypatch.setenv(
        "PR_BODY",
        "ассеты: https://johnvansickle.com/ffmpeg/releases/ffmpeg-amd64-static"
        ".tar.xz sha256 abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        "0123456789")
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert errs == []


# TC-AUD-206: IR-06 precision — Dockerfile без докачки ассетов: правило молчит
def test_ir06_plain_dockerfile_silent(tmp_path):
    repo = make_repo(tmp_path, "IR-06", "FROM debian:bookworm\nCMD [\"api\"]\n")
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert errs == []


# TC-AUD-207: тело из GITHUB_EVENT_PATH (CI-событие pull_request)
def test_pr_body_from_github_event(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir(exist_ok=True)  # conftest J41 может уже создать proj/
    rules_file(repo, "IR-05")
    event = tmp_path / "event.json"
    event.write_text(json.dumps(
        {"pull_request": {"title": "[chore] docker",
                          "body": "проверка сборкой: docker build ."}}),
        encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    errs = pr_validate.check_impact_rules(repo, [("A", DOCKERFILE)])
    assert errs == []
