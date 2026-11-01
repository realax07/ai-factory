# Манифест pipeline в планах (слой 1 диспетчера пакетов)

Раннер v0: `python3 scripts/package_runner.py <PLAN-файл>` (слой 2).
Секция `pipeline:` объявляется в YAML-блоке PLAN-<id>.md — план остается
единым артефактом ПМ, раннер лишь исполняет объявленное.

## Пример

````markdown
# PLAN-my-package: …

**Флоу: 4**. …

```yaml
pipeline:
  package: my-package
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [backend/**, tests/**]
      inputs: [openspec/changes/my-package/spec.md]
      task: реализовать FR-1..FR-3 по спеке, тесты обязательны
    - id: check
      run: gate:python3 scripts/flow_check.py
    - id: review-plan
      run: hermes:pm
```
````

## Правила

- `run:` — ровно один из трех видов:
  - `pi:<роль>` — Pi роль-пак `skills/pm-factory/pi/role-packs/<роль>/`.
    Раннер создает worktree (`scripts/session_worktree.sh`), кладет
    `role-agents.md` пака в корень worktree как `AGENTS.md`, задает
    `PI_ZONE_WRITE` из `zones` и вызывает
    `pi --no-session -e ~/.pi/agent/extensions/zone-guard.ts -p <бриф>`.
    Для pi-шага `zones` **обязателен**. Провайдер/модель берутся из
    `settings.example.json` пака (дефолт `zai-glm`/`glm-5.3`); ключ pi берет
    сам из `~/.pi/agent/models.json` — раннер секретов не касается.
  - `gate:<команда>` — shell-команда в worktree; ненулевой exit → STOP
    (exit 2, диагностика; воротные отказы НЕ ретраятся).
  - `hermes:<роль>` — **стоп-точка ПМ**: раннер печатает
    `ЖДУ ПМ: stage <id>, роль <роль>` + состояние и выходит с кодом 0.
    Дальше — ручной диспатч ПМ (делегация, приемка, push); повторный запуск
    раннера после ПМ-действий докатывает пакет: hermes-шаг помечен в state
    статусом `waited` и пропускается (раннер факт ПМ-работы не проверяет —
    запускай повтор, когда ПМ-шаг реально сделан).
- Последовательность v0 — строгая, без параллелей; `depends[]`
  игнорируется с WARNING, если нарушает порядок.
- `gate` (опциональное поле pi-шага) — команда-проверка в worktree после
  успешного pi; ненулевой exit → STOP.
- Таймаут вызова: env `PIPELINE_TIMEOUT` (сек), дефолт 1800; таймаут и
  ненулевой exit pi/gate → STOP: exit 2, хвост stdout/stderr ≤30 строк.
- Состояние: `<план>.runner-state.json` рядом с планом; после каждого stage
  — строка в секцию «## Журнал раннера» плана.
