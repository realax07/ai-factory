# Сценарий shadow-сверки 4.2 (add-deterministic-flow)

Цель: сравнить решения flow_transition с фактически принятыми решениями ПМ на
истории Р6 (ekotov-wiki). Режим shadow — только наблюдение, файлы не меняются.

## Точки сверки (реальные решения ПМ/роли за Р6, с коммитами)

| № | Решение (факт) | action/role/flow | Ожидание от машины |
|---|---|---|---|
| S1 | Старт change add-r6-task-form-ux после утверждения ТЗ (0eedae4^) | create_change / sa / 1 | ALLOW при наличии решения Заказчика в approval_ref; без него DENY/HUMAN_APPROVAL_REQUIRED |
| S2 | dev 2.1+2.2 (комбобокс) после 1.1 (60946f6) | dev_task / dev / 1, task 2.1 | ALLOW (spec + sdd + arch review зафиксированы), или честный список недостающих фактов |
| S3 | fix 2.1/2.2 по ревью (60eaa94) | dev_task / dev / 1 (возврат) | ALLOW как доработка после RETURN, evidence: review-файл |
| S4 | accept_review волны 2 (6a6cbb4, fix review-001) | accept_review / code_reviewer / 1 | UNKNOWN/STALE_EVIDENCE (compat) — provenance до поставки 05 |
| S5 | QA-контур 5.1 (fc41b90: impact+чеклист+кейсы+автотесты одним контуром) | qa_case_author / qa / 1 | ALLOW только после approved кейсов… (порядок QA), иначе INVALID_GATE |
| S6 | Релиз 5.2+5.3 (1c9eb4d: бамп static_v + регресс) | release / pm / 1 | DENY/HUMAN_APPROVAL_REQUIRED без зафиксированного решения; gates: полный регресс |
| S7 | Архивация (f925a57, контракт 7) | archive / sa / 1 | ALLOW при слитых дельтах; INVALID_GATE если дельты не слиты |
| S8 | Деплой (4908fe3) | deploy/rollback / pm / 1 | EXTERNAL_ENFORCEMENT_UNKNOWN + полномочия |

## Метод

Для каждой точки: собрать snapshot на соответствующем коммите (git checkout в
detached HEAD на КОПИИ репо — не на живом ekotov-wiki; или --repo на копию),
выполнить check с --json, зафиксировать decision; сравнить с колонкой «Ожидание»
и с фактом (что реально было сделано). Расхождения классифицировать:
ложный запрет (машина DENY, ПМ сделал и это было правильно), ложное разрешение,
честный UNKNOWN (правило текстовое).

Результат — таблица в этом файле (ниже, append) + вывод в отчет 4.4.

## Результаты (заполняется при прогоне)

TBD
