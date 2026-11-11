# PLAN-add-greeting: приветствие по имени

**Флоу: 1** — новая функция с change-пакетом: СА, архитектор, dev по
задачам с парным ревью.

Этапы: create_change (sa) → arch_review (architect) → dev по задачам
tasks.md + code review каждой задачи → flow_check. Развилки Заказчика:
старт пакета — decisions/2026-11-11-start-add-greeting.md. Прогоны:
unit-тесты задачи. Закрытие: пакет влит в main, ворота мержа зеленые.

```yaml
pipeline:
  package: add-greeting
  flow: 1
  stages:
    - id: create_change
      run: pi:sa
      approval_ref: 2026-11-11-start-add-greeting
      zones:
        - openspec/changes/add-greeting/proposal.md
        - openspec/changes/add-greeting/design.md
        - openspec/changes/add-greeting/tasks.md
        - openspec/changes/add-greeting/impact.md
        - openspec/changes/add-greeting/specs/**
        - sdd.md
      task: change-пакет по requirements.md
    - id: arch_review
      run: pi:architect
      zones:
        - architecture/**
        - test-model/reviews/add-greeting/review-001-architecture.md
      task: architecture review пакета
    - id: dev
      run: pi:dev
      zones: [src/**, tests/unit/**]
      per_task: true
      review: code-reviewer
      task: реализовать задачу
    - id: check
      run: gate:python3 "$REFERENCE_FACTORY/scripts/flow_check.py" .
```
