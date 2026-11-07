# SDD: test-zones (J66)

Реализация — PLAN-test-zones.md («Состав изменений»). Ключевые решения:

- Проверка раскладки — `flow_check.layout_findings` (единственная
  реализация; factory_init ее импортирует). Уровень файла — первый каталог
  под `tests/`; импорты — разбор `ast` (Import/ImportFrom, importorskip,
  import_module); SyntaxError — находка.
- Режим — `test-model/test-layout.json` `{"mode": "warn"|"strict"}`; файла
  нет — warn; битый — FLOW-ERROR; файл — PROTECTED_PATHS.
- Зоны — `agents/roles.json` (источник политики J65.1).
- Этап qa_automation во Флоу 2–5 — `STAGE_TABLE` сразу после первого этапа
  с тем же check-ом входа; `SEQUENCE_PREREQS` энфорсера — производная.
- `tests/conftest.py` фабрики — в корне `tests/` (сессионные хуки pytest
  вызываются только у conftest, загруженных до сбора).
