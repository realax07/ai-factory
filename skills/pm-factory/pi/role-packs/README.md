# Роль-паки Pi (skills/pm-factory/pi/role-packs)

Роль-паки для исполнителя [Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`):
каждый пак переносит фабричную роль (`agents/<роль>_agent.md`) на внешнюю
модель через Pi. Структура пака: `role-agents.md` (системный промпт; при сборке
копируется в корень worktree/клона как `AGENTS.md`), `settings.example.json`
(дефолты сессии; ключ — отдельно в `~/.pi/agent/models.json`, chmod 600),
`README.md` (сборка и вызов). Оркестратор — всегда Hermes/ПМ.

**Zone-guard — общий для всех паков**: `regress-runner/extensions/zone-guard.ts`,
устанавливается один раз в `~/.pi/agent/extensions/`, зоны записи на вызове —
env `PI_ZONE_WRITE="зона1:зона2"` (префиксы путей от cwd) + флаг
`-e ~/.pi/agent/extensions/zone-guard.ts`. Механическая гарантия — только для
`write`/`edit` (fail-closed); bash-канал эвристический, `git push` блокируется
всем ролям. Общие подводные камни Pi — в `regress-runner/README.md`.

## Оглавление паков

<!-- roles:packs:start -->
<!-- генерируется scripts/gen_role_docs.py из agents/roles.json — руками не править -->
| Пак | Роль (фабричный промпт) | Модель | Провайдер | Зоны записи (политика ворот) |
|---|---|---|---|---|
| [`ba/`](ba/README.md) | ba (`agents/ba_agent.md`) | **glm-5.3** | zai-glm | `requirements.md`, `docs/ba/*` |
| [`sa/`](sa/README.md) | sa (`agents/sa_agent.md`) | **glm-5.3** | zai-glm | `openspec/changes/<id>/proposal.md`, `openspec/changes/<id>/requirements.md`, `openspec/changes/<id>/research.md`, `openspec/changes/<id>/specs/**`, `openspec/changes/<id>/design.md`, `openspec/changes/<id>/tasks.md`, `openspec/changes/<id>/impact.md`, `sdd.md` |
| [`dev/`](dev/README.md) | dev (`agents/dev_agent.md`) | **glm-5.3** | zai-glm | `openspec/changes/<id>/tasks.md`, `backend/**`, `frontend/**`, `services/**`, `scripts/**`, `contracts/**`, `deploy/**`, `src/**`, `tests/unit/**`, `test-model/bugs/*`, `feature/*`, `plugins/**` |
| [`code-reviewer/`](code-reviewer/README.md) | code_reviewer (`agents/code_reviewer_agent.md`) | **glm-5.3-flash** | zai-glm | `code-reviews/<id>/review-*.md` (вердикт — заголовком `## Вердикт: approve\|return` (J65.4)) |
| [`qa-case-author/`](qa-case-author/README.md) | qa_case_author (`agents/qa_case_author_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/new/<id>/**` |
| [`qa-case-reviewer/`](qa-case-reviewer/README.md) | qa_case_reviewer (`agents/qa_case_reviewer_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/reviews/**`, `test-model/approved/**` (append-only партии) |
| [`qa-automation/`](qa-automation/README.md) | qa_automation (`agents/qa_automation_agent.md`) | **glm-5.3-flash** | zai-glm | `tests/api/**`, `tests/web/**`, `tests/integration/**`, `tests/smoke_cross/**`, `tests/archive/**`, `tests/conftest.py`, `tests/README.md`, `tests/__init__.py`, `tests/fixtures/**`, `test-model/bugs/*`, `pytest.ini` |
| [`qa-impact-analyst/`](qa-impact-analyst/README.md) | qa_impact_analyst (`agents/qa_impact_analyst_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/impact/*.md` |
| [`ui-designer/`](ui-designer/README.md) | ui_designer (`agents/ui_designer_agent.md`) | **glm-5.3-flash** | zai-glm | `design/**` |
| [`debug/`](debug/README.md) | debug (`agents/debug_agent.md`) | **glm-5.3-flash** | zai-glm | `docs/project-pitfalls.md` (диагностика без правки продукта; вердикт СРЕДА/КОД/ТЕСТ; запись — только база граблей (J64.11, решение Заказчика 2026-11-10)) |
| [`regress-runner/`](regress-runner/README.md) | regress_runner (`agents/regress_runner_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/regress/<id>/**` (артефакты прогонов пишет flowctl regress) |
| [`architect/`](architect/README.md) | architect (`agents/architect_agent.md`) | **glm-5.3** | zai-glm | `architecture/**`, `test-model/reviews/<id>/review-*-architecture.md` |
| [`devops/`](devops/README.md) | devops (`agents/devops_agent.md`) | **glm-5.3-flash** | zai-glm | `deploy/**`, `ops/**`, `.github/workflows/**` (боевой деплой — только по утверждению ПМ, hermes-стоп) |
| [`design-validator/`](design-validator/README.md) | design_validator (`agents/design_validator_agent.md`) | **glm-5.3-flash** | zai-glm | `test-model/reviews/<id>/review-*-design.md` |
| [`auditor/`](auditor/README.md) | auditor — Аудитор (pi-auditor, вне конвейера) | **kimi k3.1-pro** | kimi | только чтение (read-only guard, ручной вызов ПМ; модель — флагами CLI поверх settings.example.json) |
<!-- roles:packs:end -->

Распределение моделей — регруп J59 + досборка flash-паков J62: семантический
ярус (SA/архитектор/DEV/BA) — glm-5.3, дешевые механические роли (QA-квартет,
ревьюеры, дизайнер, диагностика, devops) — glm-5.3-flash, большой контекст —
Kimi K3.1 (аудитор, вручную: `settings.example.json` единый, kimi/ro-guard —
переопределение флагами CLI при вызове).

Зоны в таблице — политика ворот из `agents/roles.json` (J65.1): зона стадии
манифеста может ее только сужать, без `zones:` раннер берет ее целиком
(плейсхолдер `<id>` — change-id пакета). Блок «Зона записи» и пример
`PI_ZONE_WRITE='…'` в README каждого пака тоже генерируются из реестра
(`gen_role_docs.py`, `--check` в тестах): README паков синхронны с политикой;
пример с суженной зоной в README генератор перезапишет политикой — сужение
задается в манифесте (`zones:`) или env при вызове, не в README. Промпты паков
`role-agents.md` сверяются с политикой тестом (J64.11); у auditor политики зон
нет (только чтение) — его README не генерируется. Env `PI_ZONE_WRITE` задается в
префикс-форме (без glob-хвостов `/**`) — runner нормализует зоны манифеста
перед прокидкой (`normalize_zone`, J61); в README каждого пака показаны
обе формы (у масок внутри пути префикс guard'а шире зоны — точную границу
держит сверка диффа на finish). Структура `settings.example.json` — единая
во всех паках (J62): `zai-glm` + `glm-5.3` (sa/architect/dev/ba) или
`glm-5.3-flash` (остальные), thinking `off`, tools `read/bash/edit/write`
(у debug — `read/bash`), `sessionDir` роли, zone-guard, quietStartup,
compaction, retry.

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
