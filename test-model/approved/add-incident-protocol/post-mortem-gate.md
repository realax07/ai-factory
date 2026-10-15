# Домен: post-mortem и ворота архивации (FR-3)

- **Change:** add-incident-protocol
- **Источники:** requirements.md FR-3 + NFR-2 + spec.md «Requirement: Post-mortem для S1/S2 и ворота архивации» (сценарии: Архивация S1 без post-mortem блокируется; Архивация S2 с post-mortem проходит; Post-mortem append-only)

## Классы эквивалентности — таблица решений «severity × файл × полнота»

| # | severity | post-mortem в test-model/incidents/ | Секции | Ожидание | Кейс |
|---|---|---|---|---|---|
| 1 | S1 | отсутствует | — | DENY MISSING_INPUT, exit 1 | TC-PMG-001 |
| 2 | S2 | есть | все 3 | ALLOW, exit 0 | TC-PMG-002 |
| 3 | S3 | отсутствует | — | нет нарушения (протокол не применяется) | TC-PMG-003 |
| 4 | нет префикса | отсутствует | — | DENY MISSING_INPUT (неклассифицирован) | TC-PMG-004 |
| 5 | S1 | есть | не все | DENY INVALID_GATE | TC-PMG-005 |
| 6 | S1 | файл чужого инцидента | — | DENY MISSING_INPUT (не найден) | TC-PMG-006 |
| 7 | S2 | есть (существующий) | все 3 | файл неизменяем (append-only) | TC-PMG-007 |

Границы: граница «файл есть/нет» — TC-PMG-001↔002; граница корреляции по подстроке incident_ref в имени файла (D4) — TC-PMG-006 (чужое имя = класс «не совпало»); граница полноты секций — TC-PMG-005 (класс «не все 3»).

Негативные классы: TC-PMG-001, TC-PMG-004, TC-PMG-005, TC-PMG-006 — у каждого ожидаемая ошибка задана (код Finding + exit-код).

Состояния: append-only хранилище — TC-PMG-007 (существующая запись + добавление новой).

Комбинации: покрыты таблицей решений выше (7 правил, схлопывания не потребовались).

## API-матрицы

- auth-матрица (7 строк): N/A (протокол — CLI-ворота flow_transition, не HTTP-эндпоинт; контроль ролей — существующая STAGE_TABLE, вне среза change).
- input-validation матрица (11 строк): N/A (единственный строковый вход — incident_ref; пустое значение покрыто кодом (пустой incident_ref = отсутствие входа), типы/null/инъекции неприменимы к полю маркера; границы префикса — домен delegation-marker, TC-DEC-003).

---

## TC-PMG-001 — архивация S1 без post-mortem блокируется

- **Источник:** FR-3 + Scenario «Архивация S1 без post-mortem блокируется» + NFR-1 (Must)
- **Тип:** негатив

**Данные:** Флоу 3-задача, маркер `incident_ref=S1-prod-down`; каталог test-model/incidents/ пуст.

**Шаги:**
1. Вызвать flow_transition, действие archive_change (check_archive_flow3, Флоу 3).

**Ожидаемый результат:** Finding MISSING_INPUT «post-mortem инцидента S1-prod-down … не найден в test-model/incidents/», статус DENY, exit-код CLI 1; архивация не проходит.

## TC-PMG-002 — архивация S2 с полным post-mortem проходит

- **Источник:** FR-3 + Scenario «Архивация S2 с post-mortem проходит» (Must)
- **Тип:** позитив

**Данные:** Флоу 3-задача, маркер `incident_ref=S2-cart-500`; файл test-model/incidents/2026-10-15-S2-cart-500.md содержит заголовки «## Таймлайн» (с timestamps initial response 12:00:00→12:14:00), «## Root cause», «## Action items».

**Шаги:**
1. Вызвать flow_transition, действие archive_change (Флоу 3).

**Ожидаемый результат:** Finding по воротам post-mortem отсутствует (все 3 секции найдены); архивация не блокируется post-mortem-воротами (ALLOW по воротам, exit 0 при отсутствии иных блокирующих находок).

## TC-PMG-003 — S3 без post-mortem: ворота не применяются

- **Источник:** FR-1 (S3: протокол НЕ применяется) + FR-3 («Для S3 post-mortem не требуется») (Must)
- **Тип:** позитив (класс «S3 × файл отсутствует»)

**Данные:** Флоу 3-задача, маркер `incident_ref=S3-footer-typos`; test-model/incidents/ не содержит файла этого инцидента.

**Шаги:**
1. Вызвать flow_transition, действие archive_change (Флоу 3).

**Ожидаемый результат:** Finding по post-mortem отсутствует (S3: протокол не применяется); архивация post-mortem-воротами не блокируется.

## TC-PMG-004 — неклассифицированный incident_ref архивацию не разрешает

- **Источник:** FR-3 + FR-4 + Scenario «Инцидент без severity в маркере» + NFR-1 (Must)
- **Тип:** негатив (состояние: классификация отсутствует)

**Данные:** Флоу 3-задача, маркер `incident_ref=prod-down` (без префикса S1-/S2-/S3-); test-model/incidents/ пуст.

**Шаги:**
1. Вызвать flow_transition, действие archive_change (Флоу 3).

**Ожидаемый результат:** Finding MISSING_INPUT «инцидент неклассифицирован: incident_ref без severity-префикса S1-/S2-/S3-», статус DENY, exit 1; архивация не проходит (неклассифицированный ≠ ALLOW по NFR-1).

## TC-PMG-005 — файл без обязательных секций

- **Источник:** FR-3 (состав post-mortem: таймлайн, root cause, action items) + design D4 (Must)
- **Тип:** негатив (граница полноты)

**Данные:** Флоу 3-задача, маркер `incident_ref=S1-login-500`; файл test-model/incidents/2026-10-15-S1-login-500.md содержит только «## Root cause» — секции «Таймлайн» и «Action items» отсутствуют.

**Шаги:**
1. Вызвать flow_transition, действие archive_change (Флоу 3).

**Ожидаемый результат:** Finding INVALID_GATE с перечнем недостающих секций («таймлайн, action items»), статус DENY, exit 1; архивация не проходит.

## TC-PMG-006 — корреляция по имени файла: чужой post-mortem не засчитывается

- **Источник:** FR-3 + design D4 (именование `<YYYY-MM-DD>-<incident_ref>.md`, матч по подстроке incident_ref, NFR-1) (Must)
- **Тип:** негатив (граница корреляции)

**Данные:** Флоу 3-задача, маркер `incident_ref=S1-prod-down`; в test-model/incidents/ лежит только файл другого инцидента 2026-10-15-S2-cart-409.md.

**Шаги:**
1. Вызвать flow_transition, действие archive_change (Флоу 3).

**Ожидаемый результат:** подстрока «S1-prod-down» в именах файлов не встречается → Finding MISSING_INPUT «post-mortem … не найден», DENY, exit 1; чужой файл не открывает ворота.

## TC-PMG-007 — append-only: существующие записи не изменяются

- **Источник:** FR-3 + Scenario «Post-mortem append-only» + NFR-2 (Must)
- **Тип:** состояние/инвариант

**Данные:** в test-model/incidents/ существует 2026-10-15-S2-cart-500.md; известен его sha256 до работы.

**Шаги:**
1. `sha256sum test-model/incidents/2026-10-15-S2-cart-500.md` → сохранить.
2. Любой агент добавляет post-mortem нового инцидента (например 2026-10-15-S1-prod-down.md) и работает с каталогом.
3. `sha256sum` существующего файла; `git status test-model/incidents/`.

**Ожидаемый результат:** sha256 существующего файла не изменился, файл существует (ни удаления, ни перезаписи); изменения в каталоге — только добавление новых файлов (git status: новый untracked/add файл, modified/deleted для существующих отсутствуют).
