#!/usr/bin/env python3
"""factory_init.py — развертывание конвейера AI Factory в произвольный проект (E15).

Копирует в целевой репозиторий обязательный минимум конвейера, параметризует
под проект и прогоняет post-init ворота (flow_check на пустом проекте = OK).

Usage:
  python3 ~/ai-factory/scripts/factory_init.py --target /path/to/repo --name "My Project"
      [--force] [--skip-plugin] [--skip-crons]

Что устанавливается (списки — COPY_FILES, FLOW_CONTROL_FILES, SKILL_DIRS,
MKDIRS ниже; они и есть источник правды):
  - ворота и утилиты проекта: flow_check, pr_validate, pm_bounds_check,
    flow_preflight, delegate_gate, вотчдоги, codegraph, smoke_static,
    session_archive, session_worktree.sh, check_auth_timing, factory_paths
    (пути машины, J64.5), impact_rules.json (J58);
  - копии ядра Flow Control: flow_state, flow_transition, session_check,
    gate_runner, flowctl, flow_mode, role_zone_policy, flow_scope_check и их
    зависимости flow_ids (J65.3), gates_stats (J65.9) и agents/roles.json
    (реестр ролей, J65.1);
    работает экземпляр фабрики (--repo проекта), копии — для автономности;
  - контракты, шаблоны (constitution, task_delegation, pm_launch),
    .github/workflows/flow.yml, промпты ролей agents/*.md (шапка с sha
    эталона: flow_check предупреждает о рассинхроне), 12 скиллов конвейера;
  - скелеты: openspec/ (specs, changes/archive, config.yaml), шаблон
    impact-карты templates/impact.template.md (J58), test-model/ (new, reviews, approved, bugs, regress,
    smoke-cross, regress-domains.json, baseline.json), architecture/,
    docs/glossary.md (J53), tests/smoke_cross/README.md (J54),
    CONSTITUTION.md;
  - тесты (J66): smoke tests/unit/test_smoke.py (TC-BOOTSTRAP-001 + as-is
    база test-model/regression/_bootstrap) и режим раскладки
    test-model/test-layout.json — strict, если тестов вне раскладки нет,
    иначе warn; существующий файл режима не трогается никогда.

Машина, не проект (только если есть каталог Hermes — HERMES_HOME):
  - плагин flow-enforcer (J43) в <HERMES_HOME>/plugins/ + строка в
    существующем блоке plugins.enabled config.yaml (нет блока — инструкция,
    конфиг не правится); --skip-plugin — пропуск;
  - обертки-делегаты кронов в <HERMES_HOME>/scripts + таблица рекомендуемых
    кронов (политика 2026-10-23); --skip-crons — пропуск.
  Оркестратор не Hermes (каталога нет) — оба шага пропускаются с пометкой.

check_mirrors.py, package_runner.py, gen_role_docs.py, factory_lock.py — FACTORY-ONLY, в
проект не копируются.

Без --force существующие файлы не трогаются (докопируется недостающее); с
--force перезаписываются копируемые файлы, включая flow.yml, промпты,
CONSTITUTION.md и glossary — после него сверить required-checks и проектные
правки. Каталоги скиллов, уже существующие в проекте, не перекопируются.

Post-init ворота: flow_check <target> должен завершиться exit 0.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import factory_paths as fp  # noqa: E402  (J64.5: пути машины — только оттуда)
import flow_check as _fc  # noqa: E402  (J66: раскладка тестов — одна реализация)
import factory_lock as _fl  # noqa: E402  (J65.7: ворота CI по версии фабрики)

FACTORY = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "flow-enforcer"


def install_plugin(skip: bool = False) -> bool:
    """Шаг установки плагина flow-enforcer (J43): копия в
    ~/.hermes/plugins/flow-enforcer/ + 'flow-enforcer' в plugins.enabled
    ~/.hermes/config.yaml.

    yaml правится ТОЛЬКО добавлением строки в СУЩЕСТВУЮЩИЙ блок
    plugins.enabled (включая inline-список 'enabled: [a, b]'). Блока нет —
    печатаем инструкцию, конфиг НЕ правим. Возврат: True — шаг ОК/пропущен.
    """
    if skip:
        print("  плагин flow-enforcer: пропуск (--skip-plugin)")
        return True

    hermes_home = fp.hermes_home()
    if not hermes_home.is_dir():
        print(f"  плагин flow-enforcer: пропуск — Hermes не найден ({hermes_home}); "
              "оркестратор не Hermes — плагин не нужен (поставишь Hermes — "
              "перезапусти init)")
        return True
    src = FACTORY / "plugins" / PLUGIN_NAME
    dst = hermes_home / "plugins" / PLUGIN_NAME
    if not src.is_dir():
        print(f"  FACTORY-INIT WARNING: {src} не найден — плагин не установлен")
        return False
    try:
        if dst.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"  плагин flow-enforcer: обновлен {dst}")
        else:
            shutil.copytree(src, dst)
            print(f"  плагин flow-enforcer: установлен {dst}")
    except OSError as exc:
        print(f"  FACTORY-INIT WARNING: копия плагина не удалась: {exc}")
        return False

    config = hermes_home / "config.yaml"
    if not config.is_file():
        print("  plugins.enabled: конфиг ~/.hermes/config.yaml не найден — "
              "включи вручную:\n"
              "    plugins:\n"
              "      enabled:\n"
              f"        - {PLUGIN_NAME}")
        return True

    text = config.read_text(encoding="utf-8")
    if re.search(rf"^\s*-\s+{re.escape(PLUGIN_NAME)}\s*$", text, re.M):
        print(f"  plugins.enabled: '{PLUGIN_NAME}' уже включен")
        return True

    # Блок plugins.enabled: либо 'enabled:' со списком-строками ниже,
    # либо inline 'enabled: [ ... ]' под 'plugins:'.
    block = re.search(r"^plugins:\s*$", text, re.M)
    if block is None:
        print("  plugins.enabled: блока plugins: в config.yaml нет — "
              "включи вручную (автоправка не выполнялась):\n"
              "    plugins:\n"
              "      enabled:\n"
              f"        - {PLUGIN_NAME}")
        return True
    head = text[block.end():]
    enabled = re.search(r"^([ \t]+)enabled:(.*)$", head, re.M)
    if enabled is None:
        print("  plugins.enabled: ключа enabled внутри plugins: нет — "
              "включи вручную (автоправка не выполнялась):\n"
              "    plugins:\n"
              "      enabled:\n"
              f"        - {PLUGIN_NAME}")
        return True
    indent, inline = enabled.group(1), enabled.group(2).strip()
    if inline.startswith("["):
        # inline-список: добавляем элемент в скобки
        inner = inline[1:-1].strip()
        items = f"{inner}, " if inner else ""
        new_line = f"{indent}enabled: [{items}{PLUGIN_NAME}]"
        new_text = (text[:block.end()] + head[:enabled.start()]
                    + new_line + head[enabled.end():])
        config.write_text(new_text, encoding="utf-8")
        print(f"  plugins.enabled: '{PLUGIN_NAME}' добавлен (inline-список)")
        return True
    # список строками: вставляем сразу после 'enabled:'
    new_text = (text[:block.end()] + head[:enabled.end()] + "\n"
                + indent + "  " + f"- {PLUGIN_NAME}"
                + head[enabled.end():])
    config.write_text(new_text, encoding="utf-8")
    print(f"  plugins.enabled: '{PLUGIN_NAME}' добавлен в существующий блок")
    return True


# --- Кроны и вотчдоги (политика 2026-10-23) ---------------------------------
#
# Инцидент сессии 2026-10-23: кроны исполняют КОПИИ из ~/.hermes/scripts/
# (вне контроля версий), а не репо-копии фабрики — фикс из репо не доезжал
# до боевого файла, вотчдог спамил чат 5-минутным «ok». Решение: канонический
# источник — репо фабрики; в ~/.hermes/scripts живут только ТОНКИЕ
# ОБЕРТКИ-ДЕЛЕГАТЫ (exec к репо-копии), которые install_crons создает/обновляет.

# Скрипты, живущие под кроном: для каждого — обертка-делегат в ~/.hermes/scripts.
WATCHDOG_SCRIPTS = [
    "session_watchdog.py",
    "delegate_watchdog.py",
    "stand_reaper.py",
    "state_backup.py",  # J64.6: крон `state_backup.py backup` раз в сутки
]

# Упраздненные крон-джобы (решение Заказчика 2026-10-23): обертки НЕ создаются,
# оставшиеся standalone-копии — в WARN-список (удалить файл и крон).
ABOLISHED_CRON_SCRIPTS = [
    "watchdog_daily_digest.py",
    "pm_instruction_monitor.py",
]

CRON_WRAPPER_TEMPLATE = """#!/usr/bin/env python3
# factory-cron-wrapper (политика 2026-10-23): канонический источник — репо
# фабрики. Крон исполняет ЭТУ обертку; фиксы вливаются в репо через PR и
# доходят до крона без ручного копирования. Standalone-копии устарели.
import subprocess, sys
sys.exit(subprocess.run([sys.executable, {repo_script!r}] + sys.argv[1:]).returncode)
"""


def _is_delegate_wrapper(path: Path, repo_scripts: Path) -> bool:
    """Обертка-делегат = файл исполняет репо-копию (путь репо в тексте)."""
    try:
        return str(repo_scripts) in path.read_text(encoding="utf-8")
    except OSError:
        return False


def install_crons(target_scripts) -> dict:
    """Создать/обновить обертки-делегаты кронов в ~/.hermes/scripts.

    target_scripts — каталог живых скриптов кронов (обычно
    ~/.hermes/scripts, для тестов — fixture tmp HERMES_HOME/scripts).

    Вместо standalone-копий ставится тонкая обертка (exec к репо-копии
    фабрики), поэтому фикс репо доезжает до крона сразу после merge.
    Standalone-копии (файл без делегации) детектируются сверкой mtime/размера
    с репо-копией и заменяются оберткой; устаревшие — в WARN-списке.
    Упраздненные скрипты (digest, pm-instruction) НЕ оборачиваются — только
    WARN «удалить копию и крон».

    Возврат: {"installed": [...], "already": [...], "replaced": [...],
              "stale_warn": [...], "abolished_warn": [...], "errors": [...]}.
    """
    target_scripts = Path(target_scripts)
    repo_scripts = FACTORY / "scripts"
    report = {"installed": [], "already": [], "replaced": [],
              "stale_warn": [], "abolished_warn": [], "errors": []}

    def standalone_staleness(dst: Path, src: Path) -> str:
        reasons = []
        try:
            if dst.stat().st_mtime < src.stat().st_mtime:
                reasons.append(
                    f"mtime {dst.stat().st_mtime:.0f} старше репо "
                    f"{src.stat().st_mtime:.0f}")
            if dst.stat().st_size != src.stat().st_size:
                reasons.append(
                    f"размер {dst.stat().st_size} != репо {src.stat().st_size}")
        except OSError:
            pass
        return "; ".join(reasons) or "без дрейфа mtime/размера"

    for name in WATCHDOG_SCRIPTS:
        src = repo_scripts / name
        dst = target_scripts / name
        if not src.is_file():
            msg = f"{name}: репо-копия {src} не найдена"
            print(f"  FACTORY-INIT WARNING: {msg}")
            report["errors"].append(msg)
            continue
        wrapper = CRON_WRAPPER_TEMPLATE.format(repo_script=str(src))
        if dst.is_file() and _is_delegate_wrapper(dst, repo_scripts):
            if dst.read_text(encoding="utf-8") != wrapper:
                try:
                    dst.write_text(wrapper, encoding="utf-8")
                    report["installed"].append(name)
                    print(f"  {name}: обертка обновлена (репо-копия: {src})")
                except OSError as exc:
                    report["errors"].append(f"{name}: {exc}")
            else:
                report["already"].append(name)
            continue
        if dst.is_file():
            detail = standalone_staleness(dst, src)
            print(f"  FACTORY-INIT WARNING: {name}: standalone-копия устарела "
                  f"({detail}) — заменяю оберткой-делегатом")
            report["stale_warn"].append(f"{name}: {detail}")
            report["replaced"].append(name)
        target_scripts.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_text(wrapper, encoding="utf-8")
            report["installed"].append(name)
            print(f"  {name}: обертка-делегат установлена (репо-копия: {src})")
        except OSError as exc:
            report["errors"].append(f"{name}: {exc}")

    for name in ABOLISHED_CRON_SCRIPTS:
        dst = target_scripts / name
        if dst.is_file():
            msg = (f"{name}: упразднен решением Заказчика 2026-10-23 — "
                   "удалите копию и крон-джобу")
            print(f"  FACTORY-INIT WARNING: {msg}")
            report["abolished_warn"].append(msg)
    return report


def print_recommended_crons() -> None:
    """Таблица рекомендуемых кронов (политика 2026-10-23, синхронно
    с docs/README-flow-control.md и скиллом ekotov-watchdog-channel-policy).

    Принцип тишины: чисто → пустой stdout → молчание; аномалия → непустой
    stdout → доставляется в чат. Это ЕДИНСТВЕННЫЙ повод появления крона в чате.
    """
    rows = [
        ("session-watchdog", "*/5 * * * *", "origin",
         "залипшие сессии/ключи; чисто = пустой stdout = молчание"),
        ("stand-reaper-hourly", "0 * * * *", "local",
         "сироты стендов гасятся локально; в чат только если скрипт упал"),
        ("delegate-watchdog", "*/5 * * * *", "origin",
         "включается ПМ ПОСЛЕ проверки: прогнать починенную эвристику "
         "(project-less диспатчи ПМ = норма) — clean, exit 0"),
        ("state-backup", "15 3 * * *", "local",
         "state_backup.py backup (J64.6): архив state, ротация 14; чисто = "
         "молчание, отказ — exit 1 в лог; копию архива вывозить вне VPS"),
        ("watchdog-daily-digest", "—", "—",
         "НЕ СОЗДАВАТЬ: упразднен решением Заказчика 2026-10-23"),
    ]
    print("\n  Рекомендуемые кроны (политика 2026-10-23; чисто = молчание):")
    print("  | Джоба | Расписание | deliver | Поведение |")
    print("  |---|---|---|---|")
    for job, sched, deliver, behavior in rows:
        print(f"  | {job} | {sched} | {deliver} | {behavior} |")


COPY_FILES = [
    "scripts/factory_paths.py",  # J64.5: пути машины — импортируют скрипты ниже
    "scripts/flow_check.py",
    "scripts/pr_validate.py",
    "scripts/codegraph.py",
    "scripts/smoke_static.py",
    "scripts/session_archive.py",
    "scripts/session_worktree.sh",
    "scripts/delegate_gate.py",
    "scripts/delegate_watchdog.py",
    "scripts/check_auth_timing.py",
    "scripts/pm_bounds_check.py",
    "scripts/stand_reaper.py",
    "scripts/session_watchdog.py",
    "scripts/flow_preflight.py",
    "scripts/impact_rules.json",
    "templates/pm_launch.md",
    "agents/debug_agent.md",
    "contracts/artifact_contract.md",
    "templates/constitution.template.md",
    "templates/task_delegation.md",
    ".github/workflows/flow.yml",
]

# Детерминированный Flow Control (change add-deterministic-flow, J28):
# исполняемое ядро + контракт + скилл — устанавливается вместе с базой.
FLOW_CONTROL_FILES = [
    "scripts/flow_ids.py",  # J65.3: грамматика scope — импортируют движок ниже (BUG-026)
    "agents/roles.json",  # J65.1: реестр ролей — источник политики зон role_zone_policy
    "scripts/flow_state.py",
    "scripts/flow_transition.py",
    "scripts/session_check.py",
    "scripts/gate_runner.py",
    "scripts/flowctl.py",
    "scripts/gates_stats.py",  # J65.9: flowctl gates-stats (импорт flowctl, BUG-026)
    "scripts/flow_mode.py",
    "scripts/role_zone_policy.py",
    "scripts/flow_scope_check.py",
    "contracts/flow_control_contract.md",
]

# check_mirrors.py — FACTORY-ONLY: сверка зеркал проектов с эталоном фабрики
# выполняется ТОЛЬКО на машине фабрики (CI/вручную), в проект не ставится и
# в COPY_FILES/FLOW_CONTROL_FILES не входит (АУД, инцидент сессии 2026-10-23).

# Скиллы-скелеты (копируются целиком как каталоги).
SKILL_DIRS = [
    # Перегруппировка 2026-10-31: 9 плоских групп вместо категорий-источников
    "skills/flow/factory-flow",
    "skills/roles/case-review",
    "skills/roles/code-review",
    "skills/roles/implementation",
    "skills/roles/openspec-authoring",
    "skills/roles/requirements-elaboration",
    "skills/roles/test-automation",
    "skills/roles/test-case-design",
    # J45 (2026-10-13): расширение скиллового контура
    "skills/roles/brainstorming",
    "skills/roles/service-decomposition",
    "skills/roles/playwright-pro",
    "skills/pm-factory/handoff",
]

# Каталоги журналов решений и релизов (аудит-след Flow Control).
FLOW_CONTROL_MKDIRS = [
    "decisions",
    "releases",
]

MKDIRS = [
    "openspec/specs",
    "openspec/changes/archive",
    "tests",
    "tests/smoke_cross",
    "test-model/new",
    "test-model/reviews",
    "test-model/approved",
    "test-model/bugs",
    "test-model/regress",
    "test-model/smoke-cross",
    "architecture",
    "docs/ba",
]

# J53 (2026-10-18): скелет глоссария проекта — свободная форма, БЕЗ
# детерминированности (решение Заказчика: никаких flow_check-ворот,
# машинных форматов и валидации). Термины и контент — только на проекте.
GLOSSARY_REL = "docs/glossary.md"
GLOSSARY_TEMPLATE = """# Глоссарий проекта

**Правило ведения (свободная форма):** встретил новое рабочее название
(сервис, том, таблица, элемент фронта, статус) — запиши одной строкой
«термин — что это». Глоссарий читают новые агенты и Заказчик; оркестратор
объясняет термины сабагентам своими словами. Формат записей — свободный:
никаких машинных форматов и валидации, глоссарий — словарь понимания,
а не ворота.

## Сервисы

## Процессы

## Сущности данных

## Элементы фронта

## Статусы
"""


def install_glossary(target: Path, force: bool = False) -> str:
    """J53: создать docs/glossary.md — скелет глоссария проекта.

    Идемпотентно: существующий глоссарий НЕ перезаписывается (там уже
    живут термины проекта) — без force. С force скелет пересоздается.
    Возврат: "created" | "kept" | "recreated".
    """
    dst = target / GLOSSARY_REL
    if dst.exists() and not force:
        print(f"  {GLOSSARY_REL} уже существует — не тронут (термины проекта)")
        return "kept"
    existed = dst.exists()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(GLOSSARY_TEMPLATE, encoding="utf-8")
    print(f"  {GLOSSARY_REL} {'пересоздан (--force)' if existed else 'создан'}"
          " (скелет глоссария, свободная форма — без машинных ворот, J53)")
    return "recreated" if existed else "created"


# J54 (2026-10-18): скелеты эшелонированного регресса. Контент — у проекта:
# фабрика ставит только пустые заготовки; манифест smoke-контура пуст →
# `flowctl regress --tier smoke` честно дает WARN (контур не настроен),
# а не молчаливый прогон.
SMOKE_CROSS_README_REL = "tests/smoke_cross/README.md"
SMOKE_CROSS_README = """# tests/smoke_cross — cross-domain smoke (эшелон 2, J54)

Смоук полного контура: роутинг/авторизация/health/представитель сервиса.
Гоняется `flowctl regress --change C --tier smoke` ПЕРЕД code_review и
перед merge (2–3 мин). Список сьютов проекта — манифест
`test-model/smoke-cross/manifest.json` (`{"suites": ["tests/...", ...]}`);
пустой манифест → WARN и exit 0. Требования к тестам: быстрые,
стендонезависимые где возможно, детерминированные при `--xdist`
(session-фикстуры не делятся между воркерами).
"""
SMOKE_CROSS_MANIFEST_REL = "test-model/smoke-cross/manifest.json"
SMOKE_CROSS_MANIFEST = '{\n  "suites": []\n}\n'
REGRESS_DOMAINS_REL = "test-model/regress-domains.json"
REGRESS_DOMAINS_SKELETON = ('{\n  "rules": []\n}\n')
REGRESS_BASELINE_REL = "test-model/regress/baseline.json"
REGRESS_BASELINE_EMPTY = "[]\n"

# J58 (2026-10-19): шаблон impact-карты СА (обязательный артефакт change-пакета).
# Ставится как templates/impact.template.md проекта — заготовка, из которой СА
# копирует карту в свой пакет (или оформляет секцией «## Impact» в design.md).
# До 2026-11-07 — openspec/changes/_template/impact.md: каталог под changes/
# openspec CLI и flow_check принимали за change-пакет, и post-init ворота
# нового проекта краснели (validate --strict: «Change must have at least one
# delta»; flow_check: контракты 1/2).
IMPACT_TEMPLATE_REL = "templates/impact.template.md"
LEGACY_IMPACT_TEMPLATE_REL = "openspec/changes/_template/impact.md"


def install_impact_template(target: Path, force: bool = False) -> None:
    """J58: impact.md-заготовка change-пакета (идемпотентно, без force
    существующий файл проекта НЕ перезаписывается)."""
    legacy = target / LEGACY_IMPACT_TEMPLATE_REL
    if legacy.is_file():
        print(f"  FACTORY-INIT WARNING: {LEGACY_IMPACT_TEMPLATE_REL} — прежнее "
              "место шаблона ломает openspec validate --strict; удали каталог "
              f"openspec/changes/_template/ (шаблон теперь {IMPACT_TEMPLATE_REL})")
    dst = target / IMPACT_TEMPLATE_REL
    if dst.exists() and not force:
        return
    src = FACTORY / "templates" / "impact.template.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {IMPACT_TEMPLATE_REL} создан (шаблон impact-карты СА, J58)")


TEST_LAYOUT_REL = _fc.TEST_LAYOUT_REL


def misplaced_tests(target: Path) -> list[str]:
    """Нарушения раскладки и стека уровня тестов проекта (J66) — тот же
    разбор, что у flow_check (layout_findings)."""
    tests = target / "tests"
    if not tests.is_dir():
        return []
    return _fc.layout_findings(target, list(tests.rglob("test_*.py")))


def install_test_layout(target: Path) -> None:
    """J66: test-model/test-layout.json — режим проверки раскладки тестов.
    Существующий файл не трогается никогда (и с --force: смягчение
    strict → warn — решение Заказчика). Новый: strict, если тестов вне
    раскладки нет; иначе warn (проект до миграции, flow_check предупреждает)."""
    dst = target / TEST_LAYOUT_REL
    if dst.exists():
        print(f"  {TEST_LAYOUT_REL} уже существует — не тронут")
        return
    misplaced = misplaced_tests(target)
    mode = "warn" if misplaced else "strict"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text('{\n  "schema": "test-layout/1",\n  "mode": "%s"\n}\n' % mode,
                   encoding="utf-8")
    note = (f" ({len(misplaced)} нарушени(й) раскладки — мигрируй и "
            f"переключи на strict)" if misplaced else "")
    print(f"  {TEST_LAYOUT_REL} создан: mode={mode}{note}")


def install_factory_lock(target: Path, force: bool = False) -> bool:
    """J65.7: factory.lock — версия фабрики, чьи ворота гоняет CI проекта.
    Нет файла — пишется HEAD фабрики, влитый в origin/main; есть — не трогается
    (обновление ворот — осознанный PR: `factory_lock.py update`), с --force —
    обновляется до HEAD фабрики, влитого в origin/main. HEAD не в main —
    WARNING, lock не пишется (init при этом не проваливается). Возврат —
    записан/актуален ли lock."""
    try:
        current = _fl.read_lock(target)
    except _fl.LockError as exc:
        print(f"  FACTORY-INIT WARNING: {exc} — исправь или удали файл")
        return False
    if current is not None and not force:
        print(f"  {_fl.LOCK_NAME} уже есть ({current['sha'][:12]}) — не тронут; "
              "обновление: scripts/factory_lock.py update --target <проект>")
        return True
    try:
        sha = _fl.published_head()
    except _fl.LockError as exc:
        print(f"  FACTORY-INIT WARNING: {_fl.LOCK_NAME} не записан: {exc}")
        return False
    _fl.write_lock(target, sha, (current or {}).get("repo") or _fl.DEFAULT_REPO)
    print(f"  {_fl.LOCK_NAME}: {sha[:12]} — CI проекта гоняет ворота этой версии фабрики")
    return True


def install_regress_skeleton(target: Path, force: bool = False) -> None:
    """J54: скелеты эшелонированного регресса (идемпотентно, без force
    существующий контент проекта НЕ перезаписывается)."""
    files = [
        (SMOKE_CROSS_README_REL, SMOKE_CROSS_README),
        (SMOKE_CROSS_MANIFEST_REL, SMOKE_CROSS_MANIFEST),
        (REGRESS_DOMAINS_REL, REGRESS_DOMAINS_SKELETON),
        (REGRESS_BASELINE_REL, REGRESS_BASELINE_EMPTY),
    ]
    for rel, text in files:
        dst = target / rel
        if dst.exists() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        print(f"  {rel} создан (скелет эшелонированного регресса, J54)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="путь к целевому git-репозиторию")
    ap.add_argument("--name", required=True, help="имя проекта (для constitution)")
    ap.add_argument("--force", action="store_true", help="перезаписывать существующие файлы")
    ap.add_argument("--skip-plugin", action="store_true",
                    help="не устанавливать плагин flow-enforcer в ~/.hermes/plugins")
    ap.add_argument("--skip-crons", action="store_true",
                    help="не ставить/не обновлять обертки-делегаты кронов в ~/.hermes/scripts")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not (target / ".git").is_dir():
        print(f"FACTORY-INIT ERROR: {target} не git-репозиторий (init git вручную)")
        return 2

    # 1. Каталоги
    for d in MKDIRS + FLOW_CONTROL_MKDIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
    print(f"  каталоги: {len(MKDIRS) + len(FLOW_CONTROL_MKDIRS)} созданы/подтверждены")

    # 2. Файлы конвейера
    copied, skipped = 0, 0
    for rel in COPY_FILES + FLOW_CONTROL_FILES:
        src = FACTORY / rel
        dst = target / rel
        if dst.exists() and not args.force:
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"  файлы: {copied} скопировано, {skipped} уже были (--force для перезаписи)")

    # 2a. Скиллы-скелеты Flow Control (каталогами)
    skills_copied = 0
    for rel in SKILL_DIRS:
        src = FACTORY / rel
        dst = target / rel
        if dst.is_dir():
            skipped += 1
            continue
        shutil.copytree(src, dst)
        skills_copied += 1
    print(f"  скиллы: {skills_copied} скопировано ({', '.join(SKILL_DIRS)})")

    # 2b. Промпты ролей (в проект — самодостаточность установки) + README реестра
    import hashlib
    agents_copied = 0
    agents_dir = target / "agents"
    agents_dir.mkdir(exist_ok=True)
    for src in sorted((FACTORY / "agents").glob("*.md")):
        dst = agents_dir / src.name
        if dst.exists() and not args.force:
            continue
        text = src.read_text(encoding="utf-8")
        sha = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
        header = f"<!-- factory-version: {sha} -->\n\n"
        dst.write_text(header + text, encoding="utf-8")
        agents_copied += 1
    print(f"  промпты ролей: {agents_copied} в agents/ (версия = sha эталона в шапке)")

    # 3. Constitution из шаблона (если нет)
    constitution = target / "CONSTITUTION.md"
    if not constitution.exists() or args.force:
        tpl = (FACTORY / "templates/constitution.template.md").read_text(encoding="utf-8")
        constitution.write_text(tpl.replace("<ИМЯ ПРОЕКТА>", args.name), encoding="utf-8")
        print(f"  CONSTITUTION.md создан из шаблона (name={args.name})")
    else:
        print("  CONSTITUTION.md уже существует — не тронут")

    # 3a. openspec/config.yaml — root-маркер CLI (без него validate не находит проект)
    openspec_cfg = target / "openspec" / "config.yaml"
    if not openspec_cfg.exists() or args.force:
        openspec_cfg.write_text(
            "schema: spec-driven\n\ncontext: |\n"
            "  Language: ru\n"
            "  All artifacts must be written in ru.\n"
            "  Keep OpenSpec structural headings and SHALL/MUST keywords in English.\n",
            encoding="utf-8",
        )
        print("  openspec/config.yaml создан (root-маркер openspec CLI)")
    else:
        print("  openspec/config.yaml уже существует — не тронут")

    # 3a-2. docs/glossary.md — скелет глоссария проекта (J53, свободная форма)
    install_glossary(target, force=args.force)

    # 3a-3. Скелеты эшелонированного регресса (J54): tests/smoke_cross/README,
    # пустые манифест smoke и regress-domains.json, baseline.json = []
    install_regress_skeleton(target, force=args.force)

    # 3a-4. Шаблон impact-карты СА (J58): templates/impact.template.md
    install_impact_template(target, force=args.force)

    # 3b. tests/test_smoke.py + as-is база regression/_bootstrap (контракт 6:
    # smoke — as-is база пустого проекта, TC-BOOTSTRAP-001)
    # J66: smoke — unit-уровень (tests/unit/); легаси tests/test_smoke.py
    # проекта до миграции не дублируется.
    legacy_smoke = target / "tests" / "test_smoke.py"
    smoke = target / "tests" / "unit" / "test_smoke.py"
    if legacy_smoke.exists():
        print("  tests/test_smoke.py (легаси, вне раскладки J66) — не тронут")
    elif not smoke.exists() or args.force:
        smoke.parent.mkdir(parents=True, exist_ok=True)
        smoke.write_text(
            '"""TC-BOOTSTRAP-001: smoke пустого проекта.'
            'Заменяется реальными тестами первого пакета."""\n\n\n'
            "def test_smoke():\n"
            '    assert True\n',
            encoding="utf-8",
        )
        print("  tests/unit/test_smoke.py создан (CI pytest на пустом проекте)")
    else:
        print("  tests/unit/test_smoke.py уже существует — не тронут")
    boot_dir = target / "test-model" / "regression" / "_bootstrap"
    boot_dir.mkdir(parents=True, exist_ok=True)
    boot_case = boot_dir / "smoke.md"
    if not boot_case.exists() or args.force:
        boot_case.write_text(
            "# TC-BOOTSTRAP-001: smoke пустого проекта\n\n"
            "- **Источник:** bootstrap фабрики (init)\n"
            "- **Проверка:** проект инициализирован, CI pytest зелен\n"
            "- **Приоритет:** Must\n",
            encoding="utf-8",
        )
        print("  test-model/regression/_bootstrap/smoke.md создан (as-is база, контракт 6)")
    else:
        print("  regression/_bootstrap уже существует — не тронут")

    # 3c. Режим раскладки тестов (J66) — после smoke: решение strict|warn
    # учитывает фактические тесты проекта.
    install_test_layout(target)

    # 3d. factory.lock (J65.7): CI проекта гоняет ворота этой версии фабрики
    # Lock не записан — WARNING, не провал init: без lock CI проекта берет
    # свои scripts/ (как до J65.7), проект рабочий.
    install_factory_lock(target, force=args.force)

    # 4. Проверка среды
    ok = True
    for cmd in ("python3 --version", "git --version"):
        r = subprocess.run(cmd.split(), capture_output=True, text=True)
        print(f"  {cmd}: {r.stdout.strip() or r.stderr.strip()}")
    # openspec CLI может отсутствовать (CI pytest ставит только pytest) —
    # FileNotFoundError = тот же WARNING, что и ненулевой returncode (J53).
    try:
        r = subprocess.run(["openspec", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        r = None
    if r is None or r.returncode != 0:
        print("  openspec CLI: НЕ найден (npm i -g @fission-ai/openspec) — change-пакеты не валидируются")
        ok = False
    else:
        print(f"  openspec CLI: {r.stdout.strip()}")

    # 4a. Плагин flow-enforcer (J43): машина (~/.hermes/plugins), не проект
    if not install_plugin(skip=args.skip_plugin):
        ok = False

    # 4b. Кроны и вотчдоги (политика 2026-10-23): обертки-делегаты в
    # ~/.hermes/scripts + таблица рекомендуемых кронов. Канонический
    # источник — репо фабрики; standalone-копии устарели (инцидент сессии).
    if args.skip_crons:
        print("  кроны: пропуск (--skip-crons)")
    elif not fp.hermes_home().is_dir():
        print(f"  кроны: пропуск — Hermes не найден ({fp.hermes_home()}); "
              "вотчдоги Hermes не нужны (поставишь Hermes — перезапусти init)")
    else:
        hermes_scripts = fp.hermes_home() / "scripts"
        crons = install_crons(hermes_scripts)
        if crons["errors"]:
            ok = False
        print_recommended_crons()

    # 5. Post-init ворота: flow_check = OK на пустом проекте
    r = subprocess.run(["python3", str(FACTORY / "scripts/flow_check.py"), str(target)],
                       capture_output=True, text=True)
    print(f"  post-init flow_check: {r.stdout.strip()} (exit {r.returncode})")
    if r.returncode != 0:
        ok = False

    print(f"\nFACTORY-INIT {'OK' if ok else 'ЗАВЕРШЕН С ПРЕДУПРЕЖДЕНИЯМИ'}: {target}")
    print("Дальше: заполните CONSTITUTION.md принципами проекта; первый change-пакет — по контракту 2.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
