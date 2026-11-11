# -*- coding: utf-8 -*-
"""J65.10: эталонный межагентный прогон с заглушкой исполнителя.

Фиктивный проект `tests/fixtures/reference-run/project/` проходит Флоу 1
через пакетный раннер целиком: create_change (sa) → arch_review (architect)
→ dev по задачам tasks.md с парным code review (J64.13) → gate flow_check →
merge ветки пакета в main → ворота мержа. Раннер запускается подпроцессом
(`package_runner.py run`), flowctl/session_check/gate_runner — настоящие во
временном state; подменен только исполнитель: `bin/pi` фикстуры в PATH
копирует выходы стадии (`outputs/<stage-id>/`).

Проверяет склейку ворот, вердикта и provenance на каждом PR (CI
test-flow-control): поломка любого звена — красный эталон, а не сюрприз
на боевом пакете.

Трассировка:
  TC-J65-REF-001  полный прогон: все стадии done, резервации closed, чекбоксы
                  задач закрыл раннер после approve, вердикты со штампом
                  Reviewer-Delegation; после merge в main — flow_check
                  зеленый, pr_validate отказывает ровно на QA-контуре
                  (его в сценарии нет), unit-тесты проекта проходят
  TC-J65-REF-002  ревью задачи вернуло return — STOP, чекбокс открыт,
                  следующая задача не начата
  TC-J65-REF-003  агент записал файл вне зоны стадии — STOP OUT_OF_ZONE,
                  коммита стадии нет
  TC-J65-REF-004  заглушка: бриф без `stage <id>` и неизвестная стадия —
                  ненулевой exit (сценарий не проходит молча); повторная
                  итерация ревью дописывает файл (append-only), подмена
                  вердикта — только в файлах этой стадии

Найдено эталоном (без прогона на настоящих воротах не видно):
  TC-J65-REF-005  pm_bounds_check --sessions: повтор пары project/owner_pm —
                  только среди живых записей (раннер: owner_pm один на все
                  стадии; закрытая стадия валила finish следующей dev-стадии)
  TC-J65-REF-006  сужение зон: одинаковый glob-сегмент покрывает сам себя —
                  зона ревьюера per_task `code-reviews/<pkg>/review-*.md`
                  проходит prepare (J64.13), расширение по-прежнему отказ
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[2]
FIXTURE = FACTORY / "tests" / "fixtures" / "reference-run"
PKG = "add-greeting"
PLAN = f"PLAN-{PKG}.md"
DECISION = "2026-11-11-start-add-greeting"
# Артефакты QA-контура Флоу 1 (qa_case_author → qa_case_reviewer →
# qa_automation → regress-final): в сценарии J65.10 их нет — pr_validate
# обязан отказать ровно на них (QA-стадии в эталоне — кандидат J65.10b).
QA_CONTOUR = {f"test-model/approved/{PKG}/",
              f"test-model/regress/{PKG}/regress-final.md", "tests/"}


GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=GIT_ENV).stdout.strip()


def make_project(tmp_path: Path) -> Path:
    """Копия project/ в git-репо + decision-record старта пакета (SHA плана)."""
    repo = tmp_path / "greeter"
    shutil.copytree(FIXTURE / "project", repo)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   env=GIT_ENV)
    _git(repo, "config", "user.email", "ref@test")
    _git(repo, "config", "user.name", "ref")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init greeter")
    sha = _git(repo, "rev-parse", "HEAD")
    dec = repo / "decisions" / f"{DECISION}.md"
    dec.parent.mkdir()
    dec.write_text(
        "# Решение: старт add-greeting\n\n```decision-record\n" + json.dumps({
            "schema_version": "decision-record/1",
            "decision_id": DECISION, "date": "2026-11-11",
            "scope": {"project": "greeter", "change_id": PKG, "phase": 1},
            "action": "create_change", "commit": sha,
            "source": "эталонный прогон J65.10"},
            ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "decision start add-greeting")
    return repo


def runner_env(tmp_path: Path, **extra: str) -> dict:
    st = tmp_path / "flow-state"
    st.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update({
        "PATH": f"{FIXTURE / 'bin'}{os.pathsep}{env.get('PATH', '')}",
        "PIPELINE_FLOW_REGISTRY": str(st / "active_sessions.json"),
        "PIPELINE_FLOW_STATE": str(st / "flowctl_state.json"),
        "FLOW_MODE_FILE": str(st / "flow_mode.json"),
        "AF_STATE_DIR": str(st),
        # OpenSpec CLI в тестовой среде нет — гейт openspec_validate этапа
        # create_change заглушен (как в test_package_runner m13)
        "PIPELINE_OPENSPEC_CMD": "true",
        "REFERENCE_FACTORY": str(FACTORY),
        # глобальный/системный git config машины (gpgsign, hooks) — мимо
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    })
    env.update(extra)
    return env


def run_runner(repo: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(FACTORY / "scripts" / "package_runner.py"),
                           str(repo / PLAN)], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=600)


def runner_state(repo: Path) -> dict:
    sys.path.insert(0, str(FACTORY / "scripts"))
    import package_runner as pr
    return json.loads(pr.state_path_for(repo / PLAN).read_text(encoding="utf-8"))


def registry(env: dict) -> list[tuple[str, str]]:
    data = json.loads(Path(env["PIPELINE_FLOW_REGISTRY"]).read_text(encoding="utf-8"))
    return [(s["role"], s["status"]) for s in data.get("sessions", [])]


def worktree_of(repo: Path) -> Path:
    (wt,) = (repo.parent / f"{repo.name}-worktrees").iterdir()
    return wt


def test_reference_run_flow1_end_to_end(tmp_path):
    """TC-J65-REF-001."""
    repo = make_project(tmp_path)
    env = runner_env(tmp_path)
    proc = run_runner(repo, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    state = runner_state(repo)
    stages = state["stages"]
    assert state["expanded"]["dev"] == ["1.1", "1.2"]
    assert {k: v["status"] for k, v in stages.items()} == {
        "create_change": "done", "arch_review": "done", "dev": "expanded",
        "dev-1.1": "done", "dev-1.1-review": "done",
        "dev-1.2": "done", "dev-1.2-review": "done", "check": "done"}
    assert registry(env) == [("sa", "closed"), ("architect", "closed"),
                             ("dev", "closed"), ("code_reviewer", "closed"),
                             ("dev", "closed"), ("code_reviewer", "closed")]

    wt = worktree_of(repo)
    tasks = (wt / "openspec/changes" / PKG / "tasks.md").read_text(encoding="utf-8")
    assert "- [x] 1.1" in tasks and "- [x] 1.2" in tasks
    for tid in ("1.1", "1.2"):
        review = (wt / f"code-reviews/{PKG}/review-{tid}-001.md").read_text(
            encoding="utf-8")
        assert "Reviewer-Delegation: deleg-" in review   # штамп раннера J65.4b

    # main до мержа пакета не видел; merge ветки пакета — как PR
    assert not (repo / "openspec" / "changes" / PKG).exists()
    branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "merge", "--no-ff", "-q", "-m", f"[pipeline] Merge {PKG}", branch)

    fc = subprocess.run([sys.executable, str(FACTORY / "scripts" / "flow_check.py"),
                         str(repo)], capture_output=True, text=True, env=env)
    assert fc.returncode == 0, fc.stdout + fc.stderr
    # pr_validate change-пакета: со стороны СА/dev/ревью дефектов нет — отказ
    # ровно на QA-контуре (контракт 6, J51.3), которого в сценарии J65.10 нет
    pv = subprocess.run([sys.executable, str(FACTORY / "scripts" / "pr_validate.py"),
                         str(repo), "--id", PKG, "--type", "change"],
                        capture_output=True, text=True, env=env)
    missing = {line.strip()[2:].split(":", 1)[0]
               for line in pv.stdout.splitlines() if line.startswith("  - ")}
    assert pv.returncode == 1 and missing == QA_CONTOUR, pv.stdout + pv.stderr
    unit = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p",
                           "no:cacheprovider", "tests/unit"], cwd=repo,
                          capture_output=True, text=True, env=env)
    assert unit.returncode == 0 and "3 passed" in unit.stdout, unit.stdout


def test_reference_run_review_return_stops(tmp_path):
    """TC-J65-REF-002."""
    repo = make_project(tmp_path)
    env = runner_env(tmp_path, REFERENCE_STUB_VERDICT="dev-1.1-review:return")
    proc = run_runner(repo, env)
    assert proc.returncode != 0
    assert "return" in proc.stderr
    stages = runner_state(repo)["stages"]
    assert stages["dev-1.1"]["status"] == "done"
    assert stages["dev-1.1-review"]["status"] != "done"
    assert "dev-1.2" not in stages or stages["dev-1.2"]["status"] != "done"
    tasks = (worktree_of(repo) / "openspec/changes" / PKG / "tasks.md").read_text(
        encoding="utf-8")
    assert "- [ ] 1.1" in tasks


def test_reference_run_out_of_zone_stops(tmp_path):
    """TC-J65-REF-003: агент пишет docs/notes.md — вне зоны любой стадии
    пакета. Падает первая же стадия, create_change (sa): STOP OUT_OF_ZONE,
    коммита стадии нет."""
    repo = make_project(tmp_path)
    env = runner_env(tmp_path, REFERENCE_STUB_EXTRA="docs/notes.md")
    head = _git(repo, "rev-parse", "HEAD")
    proc = run_runner(repo, env)
    assert proc.returncode != 0
    assert "OUT_OF_ZONE" in proc.stderr and "docs/notes.md" in proc.stderr
    assert _git(worktree_of(repo), "rev-parse", "HEAD") == head
    assert runner_state(repo)["stages"]["create_change"]["status"] != "done"


@pytest.mark.parametrize("brief,code", [("без заголовка стадии", 2),
                                        ("# Пакет x (Флоу 1), stage nope", 3)])
def test_stub_refuses_unknown_stage(tmp_path, brief, code):
    """TC-J65-REF-004."""
    cwd = tmp_path / "wt"
    cwd.mkdir()
    r = subprocess.run([str(FIXTURE / "bin" / "pi"), "--no-session", "-p", brief],
                       cwd=cwd, capture_output=True, text=True)
    assert r.returncode == code and not any(cwd.iterdir())


def test_pm_bounds_duplicate_pair_only_live(tmp_path):
    """TC-J65-REF-005."""
    sys.path.insert(0, str(FACTORY / "scripts"))
    import pm_bounds_check as pb
    import session_check as sc
    assert not set(pb.FINISHED_STATUSES) & set(sc.ZONE_HOLDING)

    def problems(*statuses):
        reg = tmp_path / "reg.json"
        reg.write_text(json.dumps({"sessions": [
            dict({"delegation_id": f"deleg-{i}", "role": "dev", "project": "greeter",
                  "owner_pm": "package_runner", "repo": "/r"},
                 **({"status": st} if st else {}))
            for i, st in enumerate(statuses)]}), encoding="utf-8")
        return [p for p in pb.check_sessions(reg) if "повторяется" in p]

    assert problems("closed", "released", "running") == []
    assert problems("closed", "running", "finished")          # две живые — повтор
    assert problems(None, "running")                           # формат J2 без status — живая
    assert problems("", "running") and problems("weird", "running")   # fail-closed


def test_same_glob_segment_covers_itself():
    """TC-J65-REF-006."""
    sys.path.insert(0, str(FACTORY / "scripts"))
    import role_zone_policy as rzp
    ok = rzp.narrow_zones("code_reviewer", [f"code-reviews/{PKG}/review-*.md"])
    assert ok["violations"] == [] and ok["zones"] == [f"code-reviews/{PKG}/review-*.md"]
    assert rzp.narrow_zones("sa", [f"openspec/changes/{PKG}/specs/**"])["violations"] == []
    # шире политики — отказ, включая короткие префиксы (ревью J65.10 review-001)
    for role, wider in (("code_reviewer", f"code-reviews/{PKG}/**"),
                        ("code_reviewer", f"code-reviews/{PKG}/*.md"),
                        ("code_reviewer", "code-reviews/**/review-*.md"),
                        ("code_reviewer", "code-reviews/*"),
                        ("code_reviewer", f"code-reviews/{PKG}/*"),
                        ("sa", "openspec/changes/*")):
        assert rzp.narrow_zones(role, [wider])["violations"] == [wider], (role, wider)


def test_pattern_subset_never_widens():
    """TC-J65-REF-006: свойство «сужение не расширяет» перебором — для всех
    пар паттернов из алфавита сегментов: _pattern_lang_subset(sub, sup) ⇒
    каждый путь, который матчит sub, матчит и sup. Оракул — семантика зон
    (`*` — один сегмент, `**` — любое число, включая ноль; паттерн без
    glob — каталог со вложенными), а не session_check.glob_matches: у той
    glob перед `**` сравнивается как литерал префикса (`*/**` — ровно два
    сегмента; кандидат в бэклог J65.10)."""
    import fnmatch
    import itertools
    sys.path.insert(0, str(FACTORY / "scripts"))
    import role_zone_policy as rzp

    def zone_match(pat: str, path: str) -> bool:
        ps, us = pat.split("/"), path.split("/")
        if rzp._concrete(pat):
            return path == pat or path.startswith(pat + "/")

        def m(i: int, j: int) -> bool:
            if i == len(ps):
                return j == len(us)
            if ps[i] == "**":
                return any(m(i + 1, k) for k in range(j, len(us) + 1))
            return j < len(us) and fnmatch.fnmatchcase(us[j], ps[i]) and m(i + 1, j + 1)
        return m(0, 0)

    pat_segs = ["a", "x1", "*", "x*", "?1", "[ab]", "**"]
    path_segs = ["a", "b", "x1", "x2", "y1"]
    pats = ["/".join(p) for n in (1, 2, 3)
            for p in itertools.product(pat_segs, repeat=n)]
    paths = ["/".join(p) for n in (1, 2, 3, 4)
             for p in itertools.product(path_segs, repeat=n)]
    lang = {p: frozenset(x for x in paths if zone_match(p, x)) for p in pats}
    # sub — только glob-паттерны: так зовет _allowed_superset (конкретный
    # путь сверяется через glob_matches, не здесь)
    globs = [p for p in pats if not rzp._concrete(p)]
    widened = [(a, b) for a in globs for b in pats
               if rzp._pattern_lang_subset(a, b) and not lang[a] <= lang[b]]
    assert widened == [], widened[:10]
    # и не вырождено в «всегда отказ»: типичные сужения проходят
    for sub, sup in (("a/x*", "a/x*"), ("a/**", "**"), ("a/b/**", "a/**"),
                     ("x1/*", "x*/*"), ("a/*", "*/*")):
        assert rzp._pattern_lang_subset(sub, sup), (sub, sup)


def test_stub_review_iteration_appends_and_override_scoped(tmp_path):
    """TC-J65-REF-004: повтор ревью-стадии дописывает файл вердикта (решает
    последний заголовок); REFERENCE_STUB_VERDICT не трогает ревью других задач."""
    sys.path.insert(0, str(FACTORY / "scripts"))
    import flow_check
    cwd = tmp_path / "wt"
    cwd.mkdir()
    stub = str(FIXTURE / "bin" / "pi")
    brief = "# Пакет add-greeting (Флоу 1), stage dev-{t}-review"
    env = dict(os.environ, REFERENCE_STUB_VERDICT="dev-1.2-review:return")
    for t in ("1.1", "1.2", "1.2"):
        assert subprocess.run([stub, "-p", brief.format(t=t)], cwd=cwd, env=env,
                              capture_output=True).returncode == 0
    r11 = (cwd / f"code-reviews/{PKG}/review-1.1-001.md").read_text(encoding="utf-8")
    r12 = (cwd / f"code-reviews/{PKG}/review-1.2-001.md").read_text(encoding="utf-8")
    assert flow_check.parse_verdict(r11) == "approve"
    assert r12.count("## Вердикт:") == 2 and flow_check.parse_verdict(r12) == "return"
