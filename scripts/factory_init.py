#!/usr/bin/env python3
"""factory_init.py — развертывание конвейера AI Factory в произвольный проект (E15).

Копирует в целевой репозиторий обязательный минимум конвейера, параметризует
под проект и прогоняет post-init ворота (flow_check на пустом проекте = OK).

Usage:
  python3 ~/ai-factory/scripts/factory_init.py --target /path/to/repo --name "My Project" [--force] [--skip-plugin]

Что устанавливается:
  scripts/flow_check.py, scripts/pr_validate.py, scripts/session_worktree.sh,
  scripts/codegraph.py, scripts/smoke_static.py, scripts/session_archive.py,
  scripts/delegate_gate.py, scripts/delegate_watchdog.py, scripts/pm_bounds_check.py,
  scripts/stand_reaper.py, scripts/watchdog_daily_digest.py,
  scripts/pm_instruction_monitor.py, scripts/session_watchdog.py,
  scripts/flow_state.py, flow_transition.py, session_check.py, gate_runner.py,
  flowctl.py, flow_mode.py, role_zone_policy.py (ядро Flow Control),
  contracts/artifact_contract.md, contracts/flow_control_contract.md,
  templates/constitution.template.md, templates/task_delegation.md, templates/pm_launch.md,
  .github/workflows/flow.yml,
  openspec/ (скелет specs/ + changes/archive/), test-model/ (checklists/new/reviews/approved/bugs),
  architecture/ (пустая, для map.md архитектора),
  docs/glossary.md — скелет глоссария проекта (J53): свободная форма,
  без машинных ворот;
  J54: эшелонированный регресс — скелеты tests/smoke_cross/README.md,
  test-model/smoke-cross/manifest.json (пустой), test-model/regress-domains.json
  (пустой) и test-model/regress/baseline.json ([]) — контент у проекта;
  J58: impact-контур — scripts/impact_rules.json (правила механической
  сверки diff→требование) и openspec/changes/_template/impact.md
  (шаблон impact-карты СА);
  tests/ (smoke TC-BOOTSTRAP-001), openspec/config.yaml (root-маркер CLI),
  skills/ — 12 скиллов конвейера (factory-flow, ролевые + J45: brainstorming,
  service-decomposition, playwright-pro),
  ПЛЮС плагин flow-enforcer (J43): копия plugins/flow-enforcer/ в
  ~/.hermes/plugins/flow-enforcer/ (машина, не проект) и — если в
  ~/.hermes/config.yaml уже есть блок plugins.enabled — добавление строки
  '- flow-enforcer' в него. Нет блока → печатается инструкция, конфиг НЕ
  правится автоматически. Отключить шаг: --skip-plugin.

Промпты ролей копируются в <target>/agents/ — фабрика самодостаточна после установки.
Каждый промпт получает шапку-версию (yaml-комментарий с sha эталона); при наличии
~/ai-factory на машине flow_check предупреждает о рассинхроне (WARNING).

Post-init ворота: flow_check <target> должен завершиться exit 0.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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

    hermes_home = Path(os.environ.get(
        "HERMES_HOME", str(Path.home() / ".hermes")))
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

COPY_FILES = [
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
    "scripts/watchdog_daily_digest.py",
    "scripts/pm_instruction_monitor.py",
    "scripts/session_watchdog.py",
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
    "scripts/flow_state.py",
    "scripts/flow_transition.py",
    "scripts/session_check.py",
    "scripts/gate_runner.py",
    "scripts/flowctl.py",
    "scripts/flow_mode.py",
    "scripts/role_zone_policy.py",
    "contracts/flow_control_contract.md",
]

# Скиллы-скелеты (копируются целиком как каталоги).
SKILL_DIRS = [
    "skills/factory-flow",
    "skills/case-review",
    "skills/code-review",
    "skills/implementation",
    "skills/openspec-authoring",
    "skills/requirements-elaboration",
    "skills/test-automation",
    "skills/test-case-design",
    # J45 (2026-10-13): расширение скиллового контура
    "skills/brainstorming",
    "skills/service-decomposition",
    "skills/playwright-pro",
    "skills/handoff",
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
    "test-model/checklists",
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
# Ставится как openspec/changes/_template/impact.md — заготовка, из которой СА
# копирует карту в свой пакет (или оформляет секцией «## Impact» в design.md).
IMPACT_TEMPLATE_REL = "openspec/changes/_template/impact.md"


def install_impact_template(target: Path, force: bool = False) -> None:
    """J58: impact.md-заготовка change-пакета (идемпотентно, без force
    существующий файл проекта НЕ перезаписывается)."""
    dst = target / IMPACT_TEMPLATE_REL
    if dst.exists() and not force:
        return
    src = FACTORY / "templates" / "impact.template.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {IMPACT_TEMPLATE_REL} создан (шаблон impact-карты СА, J58)")


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

    # 3a-4. Шаблон impact-карты СА (J58): openspec/changes/_template/impact.md
    install_impact_template(target, force=args.force)

    # 3b. tests/test_smoke.py + as-is база regression/_bootstrap (контракт 6:
    # smoke — as-is база пустого проекта, TC-BOOTSTRAP-001)
    smoke = target / "tests" / "test_smoke.py"
    if not smoke.exists() or args.force:
        smoke.write_text(
            '"""TC-BOOTSTRAP-001: smoke пустого проекта.'
            'Заменяется реальными тестами первого пакета."""\n\n\n'
            "def test_smoke():\n"
            '    assert True\n',
            encoding="utf-8",
        )
        print("  tests/test_smoke.py создан (CI pytest на пустом проекте)")
    else:
        print("  tests/test_smoke.py уже существует — не тронут")
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
