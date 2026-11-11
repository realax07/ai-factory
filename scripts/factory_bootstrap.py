#!/usr/bin/env python3
"""factory_bootstrap.py — установка AI Factory на новую машину.

Одна команда для чистой машины: проверяет окружение, развертывает каталог
состояния движка и файл режима ворот, ставит zone-guard исполнителя Pi,
обертки кронов (если оркестратор — Hermes) и прогоняет сьют фабрики как
приемку. Секреты НЕ переносит (ключи — вручную: ~/.hermes/.env,
~/.pi/agent/models.json).

Usage:
  python3 scripts/factory_bootstrap.py [--flow-mode shadow|enforcing]
                                       [--skip-cron] [--skip-pi] [--skip-tests]

Что делает:
  1. Окружение: python >= 3.10 (тот, что запустил bootstrap), git, node/npm,
     OpenSpec CLI (рекомендуемая версия — OPENSPEC_VERSION), pytest в этом
     python, исполнитель Pi (`pi`; отсутствие — предупреждение).
  2. Каталог состояния движка — factory_paths.state_dir() (AF_STATE_DIR,
     дефолт ~/.hermes/state) + session-archive/; файл режима — тот же, что
     читает flow_mode.py (FLOW_MODE_FILE или <state>/flow_mode.json).
     Нового файла режим — shadow (решения считаются, не блокируют); боевой
     enforcing — решение Заказчика (`flow_mode.py set enforcing --by
     customer`) или явный флаг --flow-mode enforcing. Существующий режим без
     флага не меняется.
  3. Pi: zone-guard из репо (skills/pm-factory/pi/zone-guard.ts) →
     <PI_AGENT_DIR>/extensions/zone-guard.ts для ручных запусков pi, если его
     там нет; отличающаяся копия не перезаписывается (WARN). Пакетный раннер
     копию не использует — берет guard из репо (J64.10). Наличие
     models.json проверяется (содержимое не читается).
  4. Кроны (политика 2026-10-23, docs/README-flow-control.md «Кроны и
     вотчдоги»): только при наличии Hermes — обертки-делегаты в
     <HERMES_HOME>/scripts (factory_init.install_crons) и таблица
     рекомендуемых кронов; системный crontab НЕ правится. Записи прежнего
     bootstrap в crontab (session_watchdog / delegate_watchdog) — WARN
     «удалить вручную».
  5. Приемка: `python -m pytest tests/ -q` фабрики (полный сьют).

Ничего НЕ делает: не трогает секреты, не пушит, не создает проектов
(проекты — factory_init.py --target), НЕ ставит плагин flow-enforcer
(плагин — про проект/конвейер: его ставит factory_init.py, здесь только
подсказка, если он отсутствует).
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

import factory_paths as fp  # noqa: E402  (J64.5: пути машины — только оттуда)
import flow_mode as fm  # noqa: E402  (файл режима — один с flow_mode.py)

FACTORY = Path(__file__).resolve().parent.parent
HERMES_HOME = fp.hermes_home()
STATE = fp.state_dir()
ARCHIVE_DIR = STATE / "session-archive"
# Эталон guard'а (J64.10): раннер берет его прямо из репо; копия в
# <PI_AGENT_DIR>/extensions — только для ручных запусков pi по README паков.
ZONE_GUARD_SRC = FACTORY / "skills" / "pm-factory" / "pi" / "zone-guard.ts"
OPENSPEC_VERSION = "1.14.0"  # README «Требования»
# Записи системного crontab, которые ставил bootstrap до политики кронов
# 2026-10-23 (*/2 session_watchdog, */5 delegate_watchdog мимо Hermes).
LEGACY_CRON_MARKERS = ("session_watchdog.py", "delegate_watchdog.py")


def step(msg: str) -> None:
    print(f"[bootstrap] {msg}")


def _run(cmd: list[str]) -> tuple[int, str]:
    """(rc, вывод); бинаря нет — (127, ''), таймаут — (124, 'timeout')."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, "timeout (60s)"
    return r.returncode, (r.stdout or r.stderr).strip()


def _first(text: str) -> str:
    return text.splitlines()[0] if text else ""


def check_env(need_pytest: bool = True) -> bool:
    """Окружение машины; False — есть обязательный MISSING."""
    ok = True
    v = sys.version_info
    print(f"  python: {sys.executable} {v.major}.{v.minor}.{v.micro}")
    if (v.major, v.minor) < (3, 10):
        print("  python < 3.10 — недостаточно")
        ok = False
    for name, cmd, required, hint in (
        ("git", ["git", "--version"], True, "установи git >= 2.40"),
        ("node", ["node", "--version"], True, "нужен для OpenSpec CLI и Pi"),
        ("npm", ["npm", "--version"], True, "нужен для OpenSpec CLI и Pi"),
        ("openspec", ["openspec", "--version"], True,
         f"npm i -g @fission-ai/openspec@{OPENSPEC_VERSION}"),
        ("pi", ["pi", "--version"], False,
         "npm i -g @earendil-works/pi-coding-agent (исполнитель ролей)"),
    ):
        rc, out = _run(cmd)
        if rc == 127:
            print(f"  {name}: {'MISSING' if required else 'WARN: нет'} — {hint}")
            ok = ok and not required
            continue
        if rc == 124:
            print(f"  {name}: {'MISSING' if required else 'WARN'} — не ответил "
                  "за 60s, работоспособность не подтверждена")
            ok = ok and not required
            continue
        line = _first(out)
        print(f"  {name}: {line}")
        if name == "openspec" and OPENSPEC_VERSION not in line:
            print(f"  openspec: WARN — рекомендуемая версия {OPENSPEC_VERSION}")
    rc, out = _run([sys.executable, "-m", "pytest", "--version"])
    if rc != 0:
        print(f"  pytest: {'MISSING' if need_pytest else 'WARN: нет'} в "
              f"{sys.executable} — {sys.executable} -m pip install pytest")
        ok = ok and not need_pytest
    else:
        print(f"  pytest: {_first(out)}")
    return ok


def state_dirs(flow_mode: str | None = None) -> str:
    """Каталог состояния + файл режима. Возврат — итоговый режим."""
    STATE.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    mode_file = fm.mode_file()
    if flow_mode:
        if mode_file.exists() and fm.get_mode() == "enforcing" and flow_mode == "shadow":
            step("режим ворот: WARN — флаг --flow-mode shadow понижает боевой "
                 "enforcing (решение Заказчика); вернуть — flow_mode.py set "
                 "enforcing --by customer")
        fm.set_mode(flow_mode, by="bootstrap-flag")
        step(f"режим ворот установлен флагом: {flow_mode} ({mode_file})")
        return flow_mode
    if not mode_file.exists():
        fm.set_mode("shadow", by="bootstrap-default")
        step(f"режим ворот: shadow (новый файл {mode_file}); боевой — "
             "flow_mode.py set enforcing --by customer")
        return "shadow"
    mode = fm.get_mode()
    step(f"режим ворот: {mode} (файл уже есть: {mode_file})")
    return mode


def install_zone_guard() -> bool:
    """zone-guard исполнителя Pi; False — не удалось поставить."""
    ext = fp.pi_agent_dir() / "extensions"
    dst = ext / "zone-guard.ts"
    if not ZONE_GUARD_SRC.is_file():
        step(f"zone-guard: эталон {ZONE_GUARD_SRC} не найден")
        return False
    if dst.is_file():
        if filecmp.cmp(ZONE_GUARD_SRC, dst, shallow=False):
            step(f"zone-guard: актуален ({dst})")
        else:
            step(f"zone-guard: WARN — {dst} отличается от репо, не перезаписан. "
                 f"Обнови: cp {ZONE_GUARD_SRC} {dst}")
    else:
        try:
            ext.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ZONE_GUARD_SRC, dst)
        except OSError as exc:
            step(f"zone-guard: НЕ установлен ({exc})")
            return False
        step(f"zone-guard: установлен {dst}")
    models = fp.pi_agent_dir() / "models.json"
    if not models.is_file():
        step(f"Pi: ключа провайдера нет — создай {models} (chmod 600, не в git)")
    return True


def legacy_crontab_entries() -> list[str]:
    """Строки системного crontab, оставленные прежним bootstrap."""
    rc, out = _run(["crontab", "-l"])
    if rc != 0:
        return []
    return [line for line in out.splitlines()
            if not line.lstrip().startswith("#")
            and any(m in line for m in LEGACY_CRON_MARKERS)]


def setup_crons() -> bool:
    """Обертки-делегаты кронов Hermes (политика 2026-10-23). Системный
    crontab не правится. False — ошибка установки оберток."""
    for line in legacy_crontab_entries():
        step("кроны: WARN — запись прежнего bootstrap в системном crontab "
             f"(удали: crontab -e): {line}")
    if not HERMES_HOME.is_dir():
        step(f"кроны: Hermes не найден ({HERMES_HOME}) — вотчдоги Hermes не "
             "ставятся (оркестратор — другой кодагент; поставишь Hermes — "
             "перезапусти bootstrap)")
        return True
    scripts = str(FACTORY / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import factory_init as fi  # noqa: E402  (одна реализация оберток)
    report = fi.install_crons(HERMES_HOME / "scripts")
    fi.print_recommended_crons()
    return not report["errors"]


def acceptance_tests() -> bool:
    step("приемка: pytest tests/ фабрики ...")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=FACTORY, capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
    print(f"  {tail}")
    return r.returncode == 0


def plugin_hint() -> None:
    """Подсказка об установке flow-enforcer (J43): bootstrap про машину,
    init про проекты — сам плагин здесь НЕ ставится."""
    dst = HERMES_HOME / "plugins" / "flow-enforcer"
    if dst.is_dir():
        step(f"плагин flow-enforcer: установлен ({dst})")
        return
    step("плагин flow-enforcer НЕ установлен (J43: pre_tool_call-энфорсер "
         "делегаций Hermes). Поставь при развертывании проекта:\n"
         "  python3 scripts/factory_init.py --target <repo> --name <name>   # ставит плагин\n"
         "  # или штатно: hermes plugins install realax07/ai-factory --ref <commit>\n"
         "  # и включи: plugins.enabled: [flow-enforcer] в ~/.hermes/config.yaml\n"
         "  # см. plugins/README.md. Оркестратор не Hermes — плагин не нужен.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--flow-mode", choices=fm.VALID_MODES, default=None,
                    help="установить режим ворот (без флага: новый файл — "
                         "shadow, существующий не меняется)")
    ap.add_argument("--skip-cron", action="store_true",
                    help="не ставить обертки кронов Hermes")
    ap.add_argument("--skip-pi", action="store_true",
                    help="не ставить zone-guard исполнителя Pi")
    ap.add_argument("--skip-tests", action="store_true",
                    help="не гонять приемочный сьют")
    args = ap.parse_args(argv)

    step("1/5 окружение")
    env_ok = check_env(need_pytest=not args.skip_tests)
    step("2/5 состояние движка и режим ворот")
    state_dirs(args.flow_mode)
    plugin_hint()
    step("3/5 исполнитель Pi")
    pi_ok = True if args.skip_pi else install_zone_guard()
    step("4/5 кроны")
    cron_ok = True if args.skip_cron else setup_crons()
    step("5/5 приемочный сьют")
    tests_ok = True if args.skip_tests else acceptance_tests()

    print()
    if env_ok and pi_ok and cron_ok and tests_ok:
        print("FACTORY-BOOTSTRAP OK: фабрика готова.")
        print("Дальше: ключи (~/.hermes/.env, ~/.pi/agent/models.json); "
              "проекты — scripts/factory_init.py --target <repo> --name <name>")
        return 0
    print("FACTORY-BOOTSTRAP ЗАВЕРШЕН С ПРЕДУПРЕЖДЕНИЯМИ — исправь MISSING выше и перезапусти.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
