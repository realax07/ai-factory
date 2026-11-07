# Ролевой пак Pi: qa-case-reviewer (ревьюер тест-кейсов)

Пак роли `qa_case_reviewer` (`agents/qa_case_reviewer_agent.md`) для
исполнителя [Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`), модель
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
манифест (glob-форма):       test-model/reviews/**:test-model/approved/**
env PI_ZONE_WRITE (префикс): test-model/reviews:test-model/approved
```
<!-- roles:pack-zone:end -->

Обе строки — одна зона политики (у масок внутри пути — `code-reviews/<id>/review-*.md`, `test-model/bugs/*` — префикс guard'а шире зоны: точную границу держит сверка диффа `session_check` на finish): runner нормализует glob-хвосты зон манифеста в префикс-форму guard'а (`normalize_zone`, J61 — guard матчит зоны префиксом, не glob'ом). В env `PI_ZONE_WRITE` — префикс-форма (то, что прокидывает runner); в манифесте пакета (`stage.zones`) — glob-форма, как в гайде docs/guides/pipeline-manifest.md.

Review-файлы, **append-only партиии**: итерации нумеруются сквозно по пакету
(`test-model/reviews/<change-id>/review-NNN.md`), история не удаляется.
При вердикте «Одобрить» ревьюер переносит файлы партии в
`test-model/approved/<change-id>/` — зона `test-model/approved/**` входит в
зону политики (блок «Зона записи» выше). Кейсы в `new/` ревьюер не
правит; `git push` блокируется. **Вердикт — заголовком**
`## Вердикт: Одобрить` / `## Вердикт: Вернуть` — вердикт-ворота раннера читают последний заголовок `## Вердикт:` (approve/Одобрить → проход; return/Вернуть/«Не одобрить» → STOP «ЖДУ ПМ: возврат ревью»; нет заголовка → STOP).

## Сборка на хосте

```bash
# 1. Ролевая инструкция → корень worktree
cp skills/pm-factory/pi/role-packs/qa-case-reviewer/role-agents.md /tmp/wt-<change>/AGENTS.md

# 2. Settings → агент-директория (ключ zai — отдельно в ~/.pi/agent/models.json, chmod 600)
cp skills/pm-factory/pi/role-packs/qa-case-reviewer/settings.example.json ~/.pi/agent/settings.json
```

## Запуск (print-режим, ревью партии из брифа ПМ)

```bash
cd /tmp/wt-<change> && \
PI_ZONE_WRITE='test-model/reviews:test-model/approved' \
pi --provider zai-glm --model glm-5.3-flash --no-session \
   -e ~/.pi/agent/extensions/zone-guard.ts \
   -p "<бриф: change C123, партия: список файлов test-model/new/C123/TC-*.md. Ревью файл-за-файлом, review-файл test-model/reviews/C123/review-NNN.md с заголовком `## Вердикт: Одобрить|Вернуть`; при «Одобрить» — перенос партии в test-model/approved/C123/>"
```

- Одна партия = одна сессия; ревью — файл за файлом, append в процессе.
- Подводные камни Pi (project trust, sessionDir, jiti) — общий список в
  `../regress-runner/README.md` («Подводные камни»).
- Изоляция параллельных прогонов — worktree
  (`scripts/session_worktree.sh create`) + запись в
  `~/.hermes/state/active_sessions.json`, как у всех паков.
