# PLAN-zone-policy-pipeline-paths: владельцы путей пайплайна в политике зон (J64.18)

**Флоу: 4** — обслуживание: правка политики зон ролей (`role_zone_policy.py`
+ таблица `agents/README.md`), спеки не меняются.

## Цель

`plugins/**`, `.github/workflows/**`, `pytest.ini` не принадлежали ни одной
роли — pi-стадия с такими путями получала ZONE_OUTSIDE_POLICY (ворота J63).
Решение Заказчика 2026-11-03 (дословно): «Агентская фабрика не столько нужна
для разработки фабрики, сколько дальнейших проектов… workflows это зона
техническая. А вот питест ини это связано с автотестами. Сейчас автотесты
пишет отдельный сабагент»; владелец workflows — devops.

## Состав изменений

- `ROLE_ZONE_POLICY`: dev += `plugins/**` (код фабрики; в проектах каталога
  нет); devops += `.github/workflows/**`; qa_automation += `pytest.ini`.
- `POLICY_VERSION` — поправка J64.18 (резервации до/после различимы:
  сессия, начатая до правки, на finish получит ZONE_POLICY_MISMATCH —
  мержить без активных сессий).
- `agents/README.md`: строки dev / автоматизатор / devops.
- Тест: каждый путь — ровно у своей роли.
- Найдено по ходу: энфорсер клал в сообщение ПМ хвост сырого JSON (2000
  символов); ключи отсортированы, причины отказа (`decision`) — в начале
  JSON и при удлинении `policy_version` уходили за обрез. Исправлено:
  `decision_summary` — коды и детали отказа первыми, затем хвост.

## Манифест

```yaml
pipeline:
  package: zone-policy-pipeline-paths
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**, plugins/**]
      task: J64.18 — владельцы путей пайплайна в ROLE_ZONE_POLICY + тест; коды отказа первыми в сообщении энфорсера
    - id: docs
      run: hermes:pm    # agents/README.md — защищенная зона, правка ПМ
    - id: check
      run: gate:python3 -m pytest tests/ -q
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/zone-policy-pipeline-paths/review-001.md]
      verdict:
        file: code-reviews/zone-policy-pipeline-paths/review-001.md
        contains: "Вердикт: Одобрить"
    - id: merge
      run: hermes:pm
```

Исполнение: pi на машине исполнителя нет — стадии исполняет внешний агент
(Claude Code), ревью — независимый сабагент.

## Критерий закрытия

Стадия pi:dev / pi:devops / pi:qa-automation с этими путями проходит ворота
своей ролью и только ею; сьют зеленый.
