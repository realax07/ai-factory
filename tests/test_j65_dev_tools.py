# -*- coding: utf-8 -*-
"""J65.12: инструменты отладки — ci_local.py и factory_paths --doctor.

ci_local воспроизводит job test-flow-control CI: shallow-клон коммита HEAD,
пустой HOME, без GITHUB_*/HERMES_HOME. factory_paths --doctor/--compare
заменяет ручную сверку путей из шелла, крона и Hermes перед мержем.

Трассировка:
  TC-J65-DT-001  doctor: снимок несет label, env и пути текущего контекста
  TC-J65-DT-002  compare: одинаковые снимки → OK (rc 0), разошедшийся путь
                 → перечень с метками контекстов (rc 1)
  TC-J65-DT-003  --doctor --out <каталог> пишет factory-paths-<label>.json
  TC-J65-DT-004  ci_env: только PATH/LANG/…/PYTHONUSERBASE + пустой HOME;
                 GITHUB_EVENT_PATH, HERMES_HOME, AF_STATE_DIR не протекают
  TC-J65-DT-005  ci_local на fixture-репо: прогон видит shallow-клон, пустой
                 HOME и только закоммиченное (грязная правка не попадает)
  TC-J65-DT-006  ci_local: красный тест в коммите → rc 1
  TC-J65-DT-007  ci_local из git-хука (GIT_DIR/GIT_WORK_TREE в env) не трогает
                 исходный репозиторий: он не становится shallow, история цела
  TC-J65-DT-008  compare: снимки с одинаковой меткой (shell Mac / shell VPS)
                 не схлопываются — расхождение видно
  TC-J65-DT-009  --compare: битый JSON, не-снимок, неполный снимок, один
                 снимок → rc 2 с причиной (не traceback, не ложный OK)
  TC-J65-DT-010  --doctor --out <файл> и путь с ~
  TC-J65-DT-011  ci_local: не git-репозиторий → rc 2
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY / "scripts"))

import ci_local  # noqa: E402
import factory_paths as fp  # noqa: E402


def test_doctor_snapshot(monkeypatch, tmp_path):
    """TC-J65-DT-001"""
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    snap = fp.doctor("shell")
    assert snap["label"] == "shell"
    assert snap["paths"]["state_dir"] == str(tmp_path / "state")
    assert snap["env"]["AF_STATE_DIR"] == str(tmp_path / "state")
    assert snap["checks"]["state_dir_exists"] is True
    assert snap["checks"]["registry_exists"] is False


def test_compare(monkeypatch, tmp_path, capsys):
    """TC-J65-DT-002"""
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "a"))
    shell = fp.doctor("shell")
    cron_same = fp.doctor("cron")
    assert fp.compare([shell, cron_same]) == []
    monkeypatch.setenv("AF_STATE_DIR", str(tmp_path / "b"))
    hermes = fp.doctor("hermes")
    diffs = fp.compare([shell, cron_same, hermes])
    assert {d.split(":")[0] for d in diffs} >= {"state_dir", "registry",
                                               "flowctl_state"}
    assert not any(d.startswith(("factory_home:", "hermes_home:"))
                   for d in diffs)
    assert any(d.startswith("state_dir:") and "hermes=" in d
               and str(tmp_path / "b") in d for d in diffs)

    files = []
    for s in (shell, hermes):
        f = tmp_path / f"{s['label']}.json"
        f.write_text(json.dumps(s), encoding="utf-8")
        files.append(str(f))
    assert fp.main(["--compare", files[0], files[0]]) == 0
    assert fp.main(["--compare", *files]) == 1
    assert "РАСХОЖДЕНИЕ" in capsys.readouterr().out


def test_doctor_out_dir(tmp_path):
    """TC-J65-DT-003"""
    out = tmp_path / "doctor"
    assert fp.main(["--doctor", "cron", "--out", f"{out}/"]) == 0
    snap = json.loads((out / "factory-paths-cron.json").read_text("utf-8"))
    assert snap["label"] == "cron"


def test_ci_env_strips_machine_env(monkeypatch, tmp_path):
    """TC-J65-DT-004"""
    for k in ("GITHUB_EVENT_PATH", "HERMES_HOME", "AF_STATE_DIR"):
        monkeypatch.setenv(k, "/leak")
    monkeypatch.setenv("PYTHONUSERBASE", "/real/userbase")
    env = ci_local.ci_env(tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["PYTHONUSERBASE"] == "/real/userbase"
    assert not {"GITHUB_EVENT_PATH", "HERMES_HOME", "AF_STATE_DIR"} & set(env)
    assert set(env) <= set(ci_local._KEEP_ENV) | {"HOME"}


PROBE = '''
import os, subprocess
from pathlib import Path

def test_probe():
    """TC-PROBE-001"""
    assert not any(Path.home().iterdir()), "HOME не пустой"
    assert "GITHUB_EVENT_PATH" not in os.environ
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True).stdout.strip()
    assert shallow == "true"
    subject = subprocess.run(["git", "log", "-1", "--format=%s"],
                             capture_output=True, text=True).stdout.strip()
    assert subject == "two", "клон не на HEAD"
'''


def _fixture_repo(root: Path, probe: str = PROBE) -> Path:
    repo = root / "proj-ci"
    (repo / "tests").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "flow_check.py").write_text(
        "print('flow_check: OK')\n", encoding="utf-8")
    (repo / "tests" / "test_probe.py").write_text(probe, encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
           "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "one"], check=True)
    (repo / "NOTE").write_text("2\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "two"], check=True)
    return repo


def test_ci_local_runs_committed_shallow(tmp_path):
    """TC-J65-DT-005"""
    repo = _fixture_repo(tmp_path)
    # незакоммиченный красный тест в прогон не попадает
    (repo / "tests" / "test_dirty.py").write_text(
        "def test_dirty():\n    assert False\n", encoding="utf-8")
    assert ci_local.main(["--repo", str(repo)]) == 0


def test_ci_local_red_commit(tmp_path):
    """TC-J65-DT-006"""
    repo = _fixture_repo(tmp_path, probe="def test_red():\n    assert False\n")
    assert ci_local.main(["--repo", str(repo)]) == 1


def test_ci_local_ignores_git_hook_env(monkeypatch, tmp_path):
    """TC-J65-DT-007: GIT_DIR из окружения хука не уводит fetch в исходный
    .git (раньше: источник становился shallow, видно 1 коммит из 2)."""
    repo = _fixture_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    assert ci_local.main(["--repo", str(repo)]) == 0
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    assert not (repo / ".git" / "shallow").exists()
    count = subprocess.run(["git", "-C", str(repo), "rev-list", "--count",
                            "HEAD"], capture_output=True, text=True)
    assert count.stdout.strip() == "2"


def test_compare_same_label_not_collapsed(monkeypatch, tmp_path, capsys):
    """TC-J65-DT-008"""
    monkeypatch.setenv("AF_STATE_DIR", "/x")
    mac = fp.doctor("shell")
    monkeypatch.setenv("AF_STATE_DIR", "/y")
    vps = fp.doctor("shell")
    diffs = fp.compare([mac, vps])
    assert any(d.startswith("state_dir:") and "shell#1=/x" in d
               and "shell#2=/y" in d for d in diffs)
    a, b = tmp_path / "mac.json", tmp_path / "vps.json"
    a.write_text(json.dumps(mac), encoding="utf-8")
    b.write_text(json.dumps(vps), encoding="utf-8")
    assert fp.main(["--compare", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert "shell (mac.json)=/x" in out and "shell (vps.json)=/y" in out


def test_compare_bad_input(tmp_path, capsys):
    """TC-J65-DT-009"""
    good = tmp_path / "good.json"
    good.write_text(json.dumps(fp.doctor("shell")), encoding="utf-8")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    listed = tmp_path / "list.json"
    listed.write_text("[]", encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"label": "x", "paths": {"state_dir": "/s"}}),
                       encoding="utf-8")
    for bad in (broken, listed, empty, partial, tmp_path / "missing.json"):
        assert fp.main(["--compare", str(good), str(bad)]) == 2, bad
    assert fp.main(["--compare", str(good)]) == 2
    assert "Traceback" not in capsys.readouterr().out


def test_doctor_out_file_and_tilde(monkeypatch, tmp_path):
    """TC-J65-DT-010"""
    target = tmp_path / "snap.json"
    assert fp.main(["--doctor", "hermes", "--out", str(target)]) == 0
    assert json.loads(target.read_text("utf-8"))["label"] == "hermes"
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    (tmp_path / "h").mkdir()
    assert fp.main(["--doctor", "cron", "--out", "~/c.json"]) == 0
    assert (tmp_path / "h" / "c.json").is_file()


def test_ci_local_not_git(tmp_path):
    """TC-J65-DT-011"""
    assert ci_local.main(["--repo", str(tmp_path)]) == 2
