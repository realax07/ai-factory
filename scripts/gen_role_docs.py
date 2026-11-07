#!/usr/bin/env python3
"""gen_role_docs.py — таблицы ролей из реестра agents/roles.json (J65.1).

Генерирует блоки между маркерами `<!-- roles:<имя>:start -->` /
`<!-- roles:<имя>:end -->`:

- `zones` в agents/README.md — таблица зон записи (агент, режим, зона, push);
- `packs` в skills/pm-factory/pi/role-packs/README.md — оглавление роль-паков:
  роль, модель и провайдер (из `settings.example.json` пака — источник
  модели; поля `model`/`provider` реестра переопределяют, если модель
  задается флагами CLI), зоны записи (из реестра — та же политика, что у
  ворот);
- `pack-zone` в README каждого пака с политикой зон — блок «Зона записи»
  (glob-форма для манифеста и префикс-форма для env PI_ZONE_WRITE,
  нормализация раннера) и примеры `PI_ZONE_WRITE='…'` в тексте README
  (`<id>` → C123). У debug и auditor политики нет — их README не трогаются.

Правка зон и описаний ролей — только в agents/roles.json; таблицы руками не
правятся. Тест сверяет закоммиченное с сгенерированным (`--check`).

Usage:
  python3 scripts/gen_role_docs.py            # перегенерировать блоки
  python3 scripts/gen_role_docs.py --check    # exit 1, если блоки устарели
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
ROLES = FACTORY / "agents" / "roles.json"
PACKS = FACTORY / "skills" / "pm-factory" / "pi" / "role-packs"
TARGETS = {
    "zones": FACTORY / "agents" / "README.md",
    "packs": PACKS / "README.md",
}


def _roles() -> list[dict]:
    return json.loads(ROLES.read_text(encoding="utf-8"))["roles"]


def _cell(text: str) -> str:
    """'|' в ячейке GFM-таблицы (и внутри `code`) рвет колонки — экранируем."""
    return str(text).replace("|", "\\|")


def render_zones(roles: list[dict]) -> str:
    lines = ["| Агент | Режим | Зона записи (только она) | Push |",
             "|---|---|---|---|"]
    for r in roles:
        if r.get("in_table"):
            lines.append(f"| {_cell(r['title'])} | {_cell(r['mode'])} "
                         f"| {_cell(r['zone_text'])} | {_cell(r['push'])} |")
    return "\n".join(lines)


def _pack_settings(pack: str) -> tuple[str, str]:
    path = PACKS / pack / "settings.example.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "?", "?"
    return (str(data.get("defaultProvider") or "?"),
            str(data.get("defaultModel") or "?"))


def render_packs(roles: list[dict]) -> str:
    lines = ["| Пак | Роль (фабричный промпт) | Модель | Провайдер | "
             "Зоны записи (политика ворот) |",
             "|---|---|---|---|---|"]
    for r in roles:
        pack = r.get("pack")
        if not pack:
            continue
        provider, model = _pack_settings(pack)
        # переопределение реестра: модель задается флагами CLI (аудитор)
        provider = r.get("provider") or provider
        model = r.get("model") or model
        role = r["id"] + (f" (`{r['prompt']}`)" if r.get("prompt")
                          else f" — {r['title']}")
        zones = ", ".join(f"`{_cell(z)}`" for z in r.get("zones") or ()) or "только чтение"
        note = f" ({_cell(r['pack_note'])})" if r.get("pack_note") else ""
        lines.append(f"| [`{pack}/`]({pack}/README.md) | {role} | **{model}** "
                     f"| {provider} | {zones}{note} |")
    return "\n".join(lines)


RENDER = {"zones": render_zones, "packs": render_packs}

# Блок зоны в README каждого пака (J65.1/J64.11, обновление README
# 2026-11-07): та же политика реестра в двух формах — glob для манифеста и
# префикс для env PI_ZONE_WRITE (нормализация раннера normalize_zone).
# Пример запуска в README (`PI_ZONE_WRITE='…'`) — та же префикс-форма,
# плейсхолдер <id> → C123 (имя change-пакета в примерах паков).
PACK_ZONE = "pack-zone"
EXAMPLE_ID = "C123"
# Плейсхолдер change-id в зонах реестра (= role_zone_policy.CHANGE_ID; паритет
# держит тест TC-J65-PZ-003).
CHANGE_ID_PLACEHOLDER = "<id>"
# Только одинарные кавычки: пример-шаблон в двойных кавычках
# (`PI_ZONE_WRITE="зона1:зона2"` в README regress-runner) не трогается.
_EXAMPLE_ENV_RE = re.compile(r"PI_ZONE_WRITE='[^'\n]*'")
_runner = None


def _normalize_zone(zone: str) -> str:
    """Нормализация раннера (одна реализация); package_runner грузится один раз."""
    global _runner
    if _runner is None:
        scripts = str(FACTORY / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import package_runner  # noqa: E402
        _runner = package_runner
    return _runner.normalize_zone(zone)


def pack_zone_forms(role: dict) -> tuple[str, str]:
    zones = list(role.get("zones") or ())
    prefixes: list[str] = []
    for z in zones:
        p = _normalize_zone(z)
        if p not in prefixes:
            prefixes.append(p)
    return ":".join(zones), ":".join(prefixes)


def render_pack_zone(role: dict) -> str:
    glob_form, prefix_form = pack_zone_forms(role)
    return ("```\n"
            f"манифест (glob-форма):       {glob_form}\n"
            f"env PI_ZONE_WRITE (префикс): {prefix_form}\n"
            "```")


def apply_pack_example(text: str, role: dict) -> str:
    """Каждый пример `PI_ZONE_WRITE='…'` в README пака → префикс-форма
    политики. Суженный вручную пример будет перезаписан: сужение задается
    в манифесте (`zones:`) или env при вызове, не в README."""
    _, prefix_form = pack_zone_forms(role)
    value = prefix_form.replace(CHANGE_ID_PLACEHOLDER, EXAMPLE_ID)
    return _EXAMPLE_ENV_RE.sub(f"PI_ZONE_WRITE='{value}'", text)


def pack_targets(roles: list[dict]) -> list[tuple[Path, dict]]:
    """README паков с политикой зон (у debug/auditor политики нет — их
    README не генерируется, развилка J64.11). README пака с политикой
    обязан существовать — его отсутствие поднимается в main как ошибка."""
    return [(PACKS / r["pack"] / "README.md", r) for r in roles
            if r.get("pack") and r.get("zones")]


def apply(text: str, name: str, block: str) -> str:
    start, end = f"<!-- roles:{name}:start -->", f"<!-- roles:{name}:end -->"
    i, j = text.find(start), text.find(end)
    if i < 0 or j < i:
        raise ValueError(f"маркеры {start} / {end} не найдены")
    return (text[:i] + start + "\n<!-- генерируется scripts/gen_role_docs.py "
            "из agents/roles.json — руками не править -->\n" + block + "\n"
            + text[j:])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="не писать, exit 1 при расхождении")
    args = ap.parse_args(argv)
    roles = _roles()
    stale = []
    jobs = [(path, lambda t, n=name: apply(t, n, RENDER[n](roles)))
            for name, path in TARGETS.items()]
    jobs += [(path, lambda t, r=role: apply_pack_example(
                 apply(t, PACK_ZONE, render_pack_zone(r)), r))
             for path, role in pack_targets(roles)]
    for path, render in jobs:
        rel = path.relative_to(FACTORY)
        try:
            cur = path.read_text(encoding="utf-8")
            new = render(cur)
        except OSError as exc:
            print(f"gen_role_docs: {rel}: не читается ({exc})", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"gen_role_docs: {rel}: {exc}", file=sys.stderr)
            return 2
        if new != cur:
            stale.append(str(path.relative_to(FACTORY)))
            if not args.check:
                path.write_text(new, encoding="utf-8")
    if args.check and stale:
        print("gen_role_docs: таблицы устарели относительно agents/roles.json: "
              + ", ".join(stale) + " — запусти python3 scripts/gen_role_docs.py",
              file=sys.stderr)
        return 1
    print("gen_role_docs: " + ("обновлено: " + ", ".join(stale) if stale
                               else "таблицы актуальны"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
