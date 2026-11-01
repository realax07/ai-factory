# Роль-паки Pi (skills/pm-factory/pi/role-packs)

Роль-паки для исполнителя [Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`):
каждый пак переносит фабричную роль (`agents/<роль>_agent.md`) на внешнюю
модель через Pi. Структура пака: `role-agents.md` (системный промпт; при сборке
копируется в корень worktree/клона как `AGENTS.md`), `settings.example.json`
(дефолты сессии; ключ — отдельно в `~/.pi/agent/models.json`, chmod 600),
`README.md` (сборка и вызов). Оркестратор — всегда Hermes/ПМ.

**Zone-guard — общий для всех паков**: `regress-runner/extensions/zone-guard.ts`,
устанавливается один раз в `~/.pi/agent/extensions/`, зоны записи на вызове —
env `PI_ZONE_WRITE="зона1:зона2"` (относительные globs от cwd) + флаг
`-e ~/.pi/agent/extensions/zone-guard.ts`. Механическая гарантия — только для
`write`/`edit` (fail-closed); bash-канал эвристический, `git push` блокируется
всем ролям. Общие подводные камни Pi — в `regress-runner/README.md`.

## Оглавление паков

| Пак | Роль (фабричный промпт) | Модель | Провайдер | Зоны записи (PI_ZONE_WRITE) |
|---|---|---|---|---|
| [`regress-runner/`](regress-runner/README.md) | regress_runner (`agents/regress_runner_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/regress/<id>/**` (+ `tests/**` по брифу) |
| [`auditor/`](auditor/README.md) | pi-auditor (ручной вызов ПМ, вне конвейера) | **kimi k3.1-pro** | kimi | read-only (auditor-readonly) |
| [`sa/`](sa/README.md) | sa (`agents/sa_agent.md`) | **glm-5.3** | zai-glm | `openspec/changes/<id>/**:sdd.md` |
| [`architect/`](architect/README.md) | architect (`agents/architect_agent.md`) | **glm-5.3** | zai-glm | `architecture/**:docs/**` (+ review-путь по брифу) |
| [`dev/`](dev/README.md) | dev (`agents/dev_agent.md`) | **glm-5.3** | zai-glm | `backend/**:frontend/**:services/**:src/**:tests/**:e2e/**` |
| [`ba/`](ba/README.md) | ba (`agents/ba_agent.md`) | **glm-5.3** | zai-glm | `requirements.md:docs/ba/**` |

Распределение моделей — регруп J59: семантический ярус (SA/архитектор/DEV/BA) —
glm-5.3, дешевые механические роли — glm-5.3-flash, большой контекст — Kimi
K3.1 (аудитор, вручную).

## Шаблон вызова

```bash
cd <worktree-или-клон> && \
PI_ZONE_WRITE='<зоны-роли>' \
pi --provider <провайдер> --model <модель> --no-session \
   -e ~/.pi/agent/extensions/zone-guard.ts \
   -p "<бриф>"
```

Плейсхолдеры (`<id>` и т.п.) вызывающий подставляет под конкретный пакет
(или правит env). Длинные задачи дробите: `-p` = «команда → результат».

## Синхронизация с фабричными промптами (анти-расползание)

Каждый `role-agents.md` — выжимка фабричного промпта `agents/<роль>_agent.md`,
в шапке несет маркер `<!-- base: agents/<роль>_agent.md@<коммит> -->`. Правило:
изменил фабричный промпт роли → обнови выжимку пака и переклей маркер. Проверка
расхождения — сравнение коммита в маркере с актуальным `git log -1 -- agents/<файл>`.
