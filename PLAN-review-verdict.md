# PLAN-review-verdict: машиночитаемый вердикт ревью + авто-provenance (J65.4 / J64.12)

**Флоу: 4** — обслуживание фабрики: ворота вердикта ревью; спеки и контракты
не меняются. Задача Заказчика 2026-11-06: «давай делай первые два» (J64.12/J65.4
и J65.1 из предложенного списка).

## Что было не так (найдено разбором кода и 316 реальных review-файлов)

1. Раннер проверял вердикт подстрокой `contains: "Одобрить"` где угодно в
   файле: проходили «Не одобрить», шаблон «Одобрить / Вернуть», файл с
   «Вернуть» сверху и «Одобрить» ниже.
2. Единый парсер J10 `flow_check.parse_verdict` (им пользуются pr_validate и
   gate_runner) не знал «Вернуть» — паки Pi пишут именно так — и считал
   «Не одобрить» одобрением.
3. `pm_bounds_check` держал свою копию семантики парсера, расходившуюся с
   flow_check.
4. Provenance ревью стадии Pi не писался; J10 в pr_validate/flow_check требовал
   `Reviewer-Delegation` из реестра Hermes, которого у стадии Pi нет.

## Решение

Новый формат и новый модуль не вводятся: единый парсер уже есть — J10
`flow_check.parse_verdict`. Он исправляется и становится единственным:

- вердикт — заголовок `## Вердикт: approve|return` (Одобрить/Вернуть);
  решает **последний** заголовок файла; «Вернуть»/«returned» — return;
  «Не одобрить» и заголовок с обоими словами — return; проза без `##` —
  не вердикт. Проверено на 316 review-файлах фабрики и трех проектов:
  вердикт не изменился ни у одного;
- `flow_check.review_commit` — строка `Commit: <sha>`;
- раннер: `verdict: {file}` читается этим парсером; `contains` устарел
  (игнорируется с WARNING); `Commit:` ≠ проверявшийся коммит → STOP STALE;
  после approve/return стадии Pi раннер пишет provenance-sidecar
  (`gate_runner.write_review_provenance`: reviewed = HEAD до ревью, digest
  диффа от начала пакета, ревьюер — делегация стадии, автор — последней
  pi-стадии другой роли) и коммитит его в ветку пакета;
- `flow_check.review_sidecar_problem`: валидный sidecar (ревьюер ≠ автор,
  ревьюер не dev-делегация, вердикт sidecar = вердикт файла) подтверждает
  независимость вместо `Reviewer-Delegation` — в J10 (`approved_review_tasks`)
  и в SELF_REVIEW-проверке pr_validate;
- `pm_bounds_check.review_approve_date` — через `flow_check.parse_verdict`.

Отклонение от текста ТЗ J65.4 («блок `## Ревью N` + `verdict:`/`commit:`,
новый `scripts/review_verdict.py`»): цель ТЗ — один парсер для всех ворот;
он уже существовал, четвертый формат увеличил бы число источников правды.

## Внимание при выкатке

- `flow_check.py`, `pr_validate.py`, `pm_bounds_check.py` копируются в проекты:
  `check_mirrors` покажет расхождение до синхронизации (`factory_init --force`
  — затем сверить `flow.yml`, см. README).
- Манифесты проектов с `contains:` продолжают работать (ключ игнорируется с
  WARNING); review-файлы с вердиктом прозой (без `##`) теперь STOP — так и
  задумано.

## Тесты

`tests/test_j65_review_verdict.py` — TC-J65-VRD-001..010; адаптированы
`[test-adapted]` TC-PR-032 и TC-PR-034 (`test_package_runner.py`), песочница
раннера отдает `base_sha` как настоящий `gate_new`.

## Манифест

```yaml
pipeline:
  package: review-verdict
  flow: 4
  stages:
    - id: impl
      run: pi:dev
      zones: [scripts/**, tests/**]
      inputs: [backlog/J65-ТЗ-единый-источник-правды-2026-11-03.md]
      task: J65.4 единый парсер вердикта, provenance раннера, sidecar в J10
      gate: python3 -m pytest tests/ -q
    - id: docs
      run: hermes:pm    # паки, гайд, README, AGENTS — вне зоны dev
    - id: flow
      run: gate:python3 scripts/flow_check.py .
    - id: code_review
      run: pi:code-reviewer
      zones: [code-reviews/review-verdict/review-001.md]
      verdict:
        file: code-reviews/review-verdict/review-001.md
    - id: merge
      run: hermes:pm
```

## Критерий закрытия

Полный сьют зеленый (ci_local), мутации ловятся, ревью «Одобрить», CI
зеленый; резолюция J65.4 и J64.12 в бэклоге.

## Исполнение

Внешний агент (Claude Code); ревью — независимый сабагент.
