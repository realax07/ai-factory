# PLAN-chore: Живой пилот J51 (критерий закрытия)

**Флоу: 4**. Два параллельных dev-агента, два выделенных worktree
(flowctl prepare --create-worktree), каждый: ветка → артефакт в
test-model/regress/chore/ → `flowctl regress --change chore` → regress-артефакт.
Критерий: ноль гонок, оба артефакта валидны, нумерация цела.
Источник: backlog/J51 (критерий закрытия), MAP J51.
