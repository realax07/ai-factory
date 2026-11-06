# PLAN-roles-registry: единый реестр ролей agents/roles.json (J65.1)

**Флоу: 4** — обслуживание фабрики: источник политики зон; спеки и
контракты не меняются, политика зон ролей — та же (сверено один в один).

## Решение Заказчика (2026-11-06)

Развилка J65.1 — «перенос источника правды зон из таблицы agents/README.md
в roles.json, таблица генерируемая». Ответ Заказчика на список задач, где
эта развилка была названа: «давай делай первые два» (J64.12/J65.4 и J65.1).
Интерпретация ПМ: согласие на перенос — оглашено Заказчику до начала работ.

## Что было

- зоны ролей — словарь `ROLE_ZONE_POLICY` в `role_zone_policy.py`;
- таблица зон `agents/README.md` — отдельный текст с отпечатком на коммит
  (`POLICY_TABLE_DIGEST`) и строкой поправок в `POLICY_VERSION`;
- зоны в оглавлении роль-паков — третий текст.

Они расходились: в таблице не было строк architect, devops,
design_validator; у debug строка есть, а политики нет; зоны паков шире
политики (architect — `docs/**`, qa-automation — весь `test-model/**`; J64.11).

## Что сделано

- `agents/roles.json` (schema roles/1): по роли — id, тексты строки таблицы,
  зоны (glob, политика ворот), пак, промпт, `empty_policy`; собран
  программно из прежнего словаря и дословных строк таблицы; политика из
  реестра совпадает со старой один в один.
- `role_zone_policy.py` читает реестр; `POLICY_VERSION` = sha256 реестра;
  реестра нет или он битый — модуль не загружается (fail-closed).
- `scripts/gen_role_docs.py [--check]` — таблица зон `agents/README.md`
  (добавлены строки architect, devops, design_validator) и оглавление
  роль-паков (модель — из `settings.example.json` пака, зоны — политика).
- раннер: pi-стадия без `zones:` берет зону роли из реестра (`*` → change-id
  пакета); явные `zones:` по-прежнему только сужают.
- `factory_init`: `agents/roles.json` в `FLOW_CONTROL_FILES` (копия
  role_zone_policy в проекте читает реестр рядом).

## Вне объема

- зоны debug/auditor — развилка Заказчика J64.11 (политики нет, как было);
- примеры `PI_ZONE_WRITE` в README отдельных паков (J64.11) — источник
  правды теперь оглавление паков;
- `ZONE_POLICY_MISMATCH` по зоне своей роли — J65.2.

## Внимание при выкатке

- `POLICY_VERSION` меняется: резервация, сделанная до мержа, на finish
  получит `ZONE_POLICY_MISMATCH` — мержить без активных сессий на VPS
  (J65.2 снимет это ограничение).
- проекты: копия `role_zone_policy.py` без `agents/roles.json` не
  загрузится — синхронизация через `factory_init --force` (сверить
  `flow.yml`).

## Манифест

```yaml
pipeline:
  package: roles-registry
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**]
      task: J65.1 реестр ролей, генератор таблиц, раннер без zones
      gate: python3 -m pytest tests/ -q
    - id: docs
      run: hermes:pm    # agents/roles.json, agents/README.md, docs — вне зоны dev
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      verdict:
        file: code-reviews/roles-registry/review-001.md
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый, `gen_role_docs --check` OK, ревью «approve», CI
зеленый; резолюция J65.1 (и закрытие части J64.11) в бэклоге.

## Исполнение

Внешний агент (Claude Code); ревью — независимый сабагент.
