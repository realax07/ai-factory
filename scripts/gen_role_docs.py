#!/usr/bin/env python3
"""gen_role_docs.py — таблицы ролей из реестра agents/roles.json (J65.1).

Генерирует два блока между маркерами `<!-- roles:<имя>:start -->` /
`<!-- roles:<имя>:end -->`:

- `zones` в agents/README.md — таблица зон записи (агент, режим, зона, push);
- `packs` в skills/pm-factory/pi/role-packs/README.md — оглавление роль-паков:
  роль, модель и провайдер (из `settings.example.json` пака — источник
  модели; поля `model`/`provider` реестра переопределяют, если модель
  задается флагами CLI), зоны записи (из реестра — та же политика, что у
  ворот).

Правка зон и описаний ролей — только в agents/roles.json; таблицы руками не
правятся. Тест сверяет закоммиченное с сгенерированным (`--check`).

Usage:
  python3 scripts/gen_role_docs.py            # перегенерировать блоки
  python3 scripts/gen_role_docs.py --check    # exit 1, если блоки устарели
"""
from __future__ import annotations

import argparse
import json
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
    for name, path in TARGETS.items():
        cur = path.read_text(encoding="utf-8")
        new = apply(cur, name, RENDER[name](roles))
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
