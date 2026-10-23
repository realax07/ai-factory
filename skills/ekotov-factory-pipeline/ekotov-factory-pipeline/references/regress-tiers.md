# Regress: пять эшелонов, ворота, harness (J51–J54)

## Пять эшелонов

| Эшелон | Когда | Что | Время | Кто |
|---|---|---|---|---|
| 0. Инстант | каждая итерация dev | юниты своего модуля | секунды | dev |
| 1. Доменный | закрытие задачи | `flowctl regress` по кейс-доменам куска | 1–5 мин | dev |
| 2. Cross-domain smoke | перед review и перед merge | полный контур: роутинг/авторизация/health/представитель сервиса | 2–3 мин | regress_runner / CI |
| 3. Regress-final | пакетно перед плановым деплоем (покрывает партию смерженных) | все домены + NFR на каноническом контуре | 15–25 мин | regress_runner |
| 4. Прод-приемка | после деплоя | живая приемка + смоук deploy.sh | минуты | Заказчик |

Полный regress НЕ на каждый change: на change — smoke + доменный regress своего куска; regress-final — пакетно перед плановым деплоем.

## Механика (J51.2/J51.3)

- `flowctl regress --change <C> [--final] [--tier smoke] [--xdist N] [--suggest-baseline]`
- Артефакт `test-model/regress/<C>/regress-<N>.md`; финальный — `regress-final.md` (нумерованные финальными не считаются).
- Ворота merge (change-PR): regress-final обязателен — PASS, commit-предок HEAD.
- **Freshness**: измененный после прогона продуктовый/tests-файл → STALE, перегон. Мета-файлы (code-reviews/**, test-model/regress/**, test-model/reviews/**) ИСКЛЮЧЕНЫ (BUG-023/024) — влитие ревью-мет после прогона не перегоняет.
- **Freeze tooling**: scripts/**, .github/** после прогона → STALE с нотой «freeze tooling». Зеркалить фабричные скрипты ДО regress-final.
- **Карта доменов** `test-model/regress-domains.json` (контент у проекта): prefix→domain, применяется до дефолтных; при активной карте кейс-домены не сворачиваются в tests/; битая карта — громкая ошибка, не молчаливый дефолт. Осторожно: multi-domain карта = один pytest-вызов, bare `from conftest import` роняет коллекцию (правило — хелперы через фикстуры).
- **xdist**: `--xdist N` → pytest -n N; session-фикстуры/стенды не делить между воркерами, стендозависимые — serial-маркеры. pytest-xdist ставить в тест-окружения проектов.
- **Baseline** `test-model/regress/baseline.json` ({test, reason, added}): падающий из baseline не красит вердикт («baseline: ожидаемо-падающий» в артефакте); `--final` игнорирует baseline (полный честный прогон); `--suggest-baseline` дописывает упавших в baseline-suggestions.json с дедупом — переносит ПМ вручную с причиной.
- **Freeze-ворота**: scripts/**, .github/** после commit прогона → STALE с нотой «freeze tooling»; мета-исключения приоритетны (только мета после прогона → PASS).
- **Новый тест-файл = TC-<домен>-001..NN в docstring** (правило 6): ловилось трижды (J52-016, J42-32 теста) — нумеруй при создании, не после CI.

## `flowctl release <correlation-id> [--reason]`

Явный сброс ПМ needs_attention/reserved-сессий: статус валидируется ПОД ЛОКОМ (expect_from; гонка release×run = работающий агент теряет зону), ничего не удаляет молча (worktree/реестр сохранены), audit + идемпотентный no-op, отказ exit 1 на running («статус изменился, повтори release»).

## Gate self-test harness (новые ворота обкатывай ДО merge)

Фикстура CI-имитации: git clone --depth 1 (shallow) эталонного tmp-репо с полным change-пакетом + чистый env (env -i: только python/git, без GITHUB_*/~/.hermes/openspec/локальных путей). Проверять ОБЕ оси:
- ancestry (shallow-клон: merge-base недоступен → тихий unshallow / GitHub API compare);
- fresh (коммиты с GIT_AUTHOR/COMMITTER_DATE шагом ≥60с — секундные таймстампы схлопывают сверку; кейсы: мета-коммит после regress → PASS, продуктовый после → STALE).
Верифицировать harness на пре-фиксных версиях ворот (ложный STALE до фикса = ось покрыта). Голый локальный прогон — не обкатка. Образец: tests/test_gate_harness.py в ai-factory.

## regress_runner (узкий бриф)

Ветка/коммит/затронутые сьюты — контекст релиза не нужен. Прогон, различение бага от флака изолированным перепрогоном 2×, FAIL → возврат dev'у. ПМ принимает артефакт (вердикт + provenance), не запускает сам.

## Push-политика (J42): слои L1–L4, детерминированно

- **L1** ruleset main bypass-never — никто не пушит main (стоит, GitHub гарантирует).
- **L2** flow.yml-триггер `push: branches: [main, 'pipeline/**']` — пуш сабагентской ветки проходит flow_check; без открытого PR → падающий шаг с `::error::` «открой PR».
- **L4** enforcer push_gate: в контексте делегации `git push` разрешен только в ветку из ALLOW; main/чужая/теги/удаление/--mirror/--all/составные команды → DENY. Kill-switch `FLOW_ENFORCER_PUSH=0`. Остаток: обертки-подshell не парсятся — их держит L1.
- **L3** bot-identity для аудита «кто пушил» — отдельное заводское решение (креденшал общий).
- Формулировка в AGENTS.md обеих реп: «Сабагент пушит только свою ветку pipeline/<change> и открывает PR; main и чужие зоны — запрещены».

## Контракты ролей — в промптах, не в голове ПМ (J52-w2)

Корневой вывод разбора ошибок: конфликты знаний ПМ↔сабагенты — главный источник кругов; стоячие контракты живут в системных промптах + строковые стражи-тесты.
- **dev**: репорт `test-model/bugs/BUG-NNN-*.md` с разделом Статус — часть коммита багфикса; ветка/worktree — только из ALLOW; новые тест-файлы — TC-нумерация в docstring.
- **code_reviewer**: машиночитаемый формат review-файла: заголовок `## Вердикт: approve|return`; `Reviewer-Delegation: deleg_<id>` — deleg_ вплотную к метке (REVIEWER_META_RE не матчит deleg-id через текст); несколько задач — review-mapping.json.
- **regress_runner**: freeze tooling после regress-final.
- Стражи: tests/test_j52_w2.py — строковые assertion контрактных строк в промптах (не дают исчезнуть при синке).

## Стенд-гигиена regress-контура

reset-скрипт стенда должен глушить ВСЕ сервисы контура (паттерн только по :8080 оставляет search/images/video со старой БД/SECRET_KEY → массовые 401 на токенах нового app). SECRET_KEY — единый env всего контура.
