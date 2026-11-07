# Ролевой пак Pi: code-reviewer (код-ревьюер)

Пак роли `code_reviewer` (`agents/code_reviewer_agent.md`) для исполнителя
[Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`), модель
**glm-5.3-flash** (механический ярус, J59/J62). Оркестратор — всегда
Hermes/ПМ.

## Состав

| Файл | Назначение |
|---|---|
| `role-agents.md` | Ролевая инструкция (выжимка фабричного промпта). При сборке — в корень worktree как `AGENTS.md` (или `AGENTS.pi.md`, если проектный уже есть). |
| `settings.example.json` | Дефолты сессии: `zai-glm`/`glm-5.3-flash`, tools `read/bash/edit/write`, zone-guard. |

zone-guard НЕ входит в пак: используется установленный
`~/.pi/agent/extensions/zone-guard.ts` (общий для всех паков). Зоны — env
`PI_ZONE_WRITE` при вызове.

## Зона записи (PI_ZONE_WRITE)

<!-- roles:pack-zone:start -->
<!-- генерируется scripts/gen_role_docs.py из agents/roles.json — руками не править -->
```
манифест (glob-форма):       code-reviews/<id>/review-*.md
env PI_ZONE_WRITE (префикс): code-reviews/<id>
```
<!-- roles:pack-zone:end -->

Обе строки — одна зона политики (у масок внутри пути — `code-reviews/<id>/review-*.md`, `test-model/bugs/*` — префикс guard'а шире зоны: точную границу держит сверка диффа `session_check` на finish): runner нормализует glob-хвосты зон манифеста в префикс-форму guard'а (`normalize_zone`, J61 — guard матчит зоны префиксом, не glob'ом). В env `PI_ZONE_WRITE` — префикс-форма (то, что прокидывает runner); в манифесте пакета (`stage.zones`) — glob-форма, как в гайде docs/guides/pipeline-manifest.md.

Только review-файлы (`code-reviews/<change-id>/review-*.md`). Код,
tasks.md, спеки, тесты — вне зон, zone-guard отклоняет запись (`{block: true}`),
`git push` блокируется всем ролям.

**Вердикт — заголовком** `## Вердикт: Одобрить` (или `## Вердикт: Вернуть`):
вердикт-ворота раннера читают последний заголовок `## Вердикт:` (approve/Одобрить → проход; return/Вернуть/«Не одобрить» → STOP «ЖДУ ПМ: возврат ревью»; нет заголовка → STOP) — единый парсер `flow_check.parse_verdict` (J65.4).
Строка `Commit: <sha>` в файле сверяется с проверявшимся коммитом (STALE).
После вердикта раннер сам пишет аудит-запись provenance в
`<план>.runner-reports/`. Прозаический вердикт «по памяти» = задача НЕ
покрыта воротами.

## Сборка на хосте

```bash
# 1. Ролевая инструкция → корень worktree
cp skills/pm-factory/pi/role-packs/code-reviewer/role-agents.md /tmp/wt-<change>/AGENTS.md

# 2. Settings → агент-директория (ключ zai — отдельно в ~/.pi/agent/models.json, chmod 600)
cp skills/pm-factory/pi/role-packs/code-reviewer/settings.example.json ~/.pi/agent/settings.json
```

## Запуск (print-режим, разовое ревью из брифа ПМ)

```bash
cd /tmp/wt-<change> && \
PI_ZONE_WRITE='code-reviews/C123' \
pi --provider zai-glm --model glm-5.3-flash --no-session \
   -e ~/.pi/agent/extensions/zone-guard.ts \
   -p "<бриф: задача N tasks.md change C123, дифф/файлы, пути спеки/sdd, отчет dev. Review-файл: code-reviews/C123/review-<задача>-001.md с заголовком `## Вердикт: Одобрить|Вернуть` и строкой `Commit: <sha>`>"
```

- Одна задача = одно ревью; SELF_REVIEW запрещен (чужой дифф только).
- Подводные камни Pi (project trust, sessionDir, jiti) — общий список в
  `../regress-runner/README.md` («Подводные камни»).
- Изоляция параллельных прогонов — worktree
  (`scripts/session_worktree.sh create`) + запись в
  `~/.hermes/state/active_sessions.json`, как у всех паков.
