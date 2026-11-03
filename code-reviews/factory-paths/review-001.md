Вердикт: Вернуть
Ревьюер: code_reviewer (сабагент Claude Code)
Коммит: aef66fa

## Замечания

| # | Уровень | Файл:строка | Проблема | Сценарий отказа | Рекомендация |
|---|---|---|---|---|---|
| 1 | major | scripts/flow_check.py:14 (также scripts/check_mirrors.py:27) | `flow_check.py` раньше был автономным (AGENTS.md: «скопируй `scripts/flow_check.py` и `flow.yml`»), теперь безусловно делает `import factory_paths`. Зеркала проектов сверяет `check_mirrors.py`, у него `DEFAULT_FILES = (flow_check.py, pr_validate.py, impact_rules.json)`: `factory_paths.py` в списке нет, так что сверка не заметит, что его нет в проекте. | Проект, поставленный до J64.5 (ekotov-wiki), обновляет зеркало `flow_check.py` по сигналу `check_mirrors` или по AGENTS.md. После этого шаг CI `python3 scripts/flow_check.py .` падает с `ModuleNotFoundError: No module named 'factory_paths'`, и любой push в проект краснеет. Воспроизведено: в каталоге скопированы `flow_check.py`, `pr_validate.py` и `session_check.py` без `factory_paths.py`, запуск дал ModuleNotFoundError. `factory_init` закрывает только новую или повторную установку. | Сделать импорт в `flow_check.py` (и желательно в `pr_validate.py`) с fallback: `try: import factory_paths as fp` / `except ImportError:` локальный дефолт `~/ai-factory` с учетом `AI_FACTORY_HOME`. Либо добавить `factory_paths.py` в `DEFAULT_FILES` `check_mirrors` и исправить инструкцию в AGENTS.md о копировании. Добавить тест: `flow_check` из копии без соседнего модуля запускается. |
| 2 | major | scripts/factory_paths.py:47 (`state_dir`), plugins/flow-enforcer/enforcer.py (state dir) | Дефолт памяти движка теперь `$HERMES_HOME/state`, раньше всегда был `~/.hermes/state`. Без env результат тот же, но все скрипты, кроны и энфорсер внутри процесса Hermes теперь следуют `HERMES_HOME`. Docstring модуля сам говорит: «память движка не зависит от исполнителя». | Если Hermes на VPS экспортирует `HERMES_HOME` в каталог профиля (`~/.hermes/profiles/<p>`), процессы, которые он запускает (энфорсер, terminal-вызовы ПМ, кроны через gateway), читают state из профиля. Тогда `flow_mode.json` там нет, `get_mode()` возвращает `shadow`, и enforcing тихо снимается: DENY перестает останавливать. Кроме того, реестр резерваций и flowctl_state раздваиваются между процессами с env и без него, ZONE_CONFLICT не ловится. Сейчас защита есть только в тексте плана («сверить до мержа»), в коде ее нет. | Предпочтительно: дефолт `state_dir()` не связывать с `HERMES_HOME`, оставить `Path.home()/".hermes"/"state"` (переопределяется только через `AF_STATE_DIR`), то же в зеркале энфорсера. Альтернатива: до мержа зафиксировать артефактом вывод `python3 scripts/factory_paths.py` на VPS из шелла, из крона и из процесса Hermes, показывающий, что `HERMES_HOME` не задан или равен `~/.hermes`. |
| 3 | minor | scripts/chat_degrade_watchdog.py:18-19 | Дефолт поменялся: было `/home/openclaw/.hermes/...`, стало `~/.hermes/...`. Значение то же только при запуске от пользователя openclaw. | Крон от другого пользователя (root) читает не тот лог. | Отметить в «Внимание при выкатке» или сверить пользователя крона. |
| 4 | minor | scripts/package_runner.py:1198 | `GATE_ENV_STRIP` меняется глобально в `cmd_run` и остается измененным на весь процесс. При ManifestError значение не сбрасывается, хотя там это ни на что не влияет. | Для CLI безвредно. Тест или вызывающий код, который зовет функции раннера напрямую после `cmd_run`, получит список предыдущего манифеста. | Передавать strip-список параметром в функцию сборки env или сбрасывать его в начале `cmd_run`. |
| 5 | minor | tests/test_factory_paths.py:85 | Регэксп не ловит `expanduser('~` (одинарные кавычки), `Path("~/...")`, `os.environ["HOME"]`. Исключение для энфорсера по подстроке `_env_path(` в строке. Сейчас таких мест в коде нет (проверено grep, нашлась только строка справки в delegate_gate.py:236). | Будущая прошивка в этих формах пройдет тест. | Расширить шаблон: `expanduser\(['"]~`, `Path\(['"]~`, `environ.*['"]HOME`. |

## Проверено

- Все ~50 замен в 15 скриптах (`git diff origin/main...HEAD`). Без env каждый путь совпадает с прежним (`Path.home()/.hermes/...`, `~/ai-factory`, `~/.pi/agent`, `Path.home()/<project>`). Единственный реально другой дефолт — пункт 3. Расширение поведения: следование `HERMES_HOME` (пункт 2).
- Точечные переопределения сохранены: `FLOW_MODE_FILE`, `FLOW_ENFORCER_STATE_DIR` (приоритет выше `AF_STATE_DIR`), `FLOW_ENFORCER_REGISTRY`, `PIPELINE_FLOW_REGISTRY`.
- Импорт `factory_paths` в скриптах держится на том, что каталог скрипта попадает в `sys.path`. Это выполняется для `python3 scripts/x.py` из любого cwd и для обертки крона `CRON_WRAPPER_TEMPLATE` (subprocess на репо-скрипт). В `package_runner` сначала явно `sys.path.insert(SCRIPTS)`, поиск движка через `fp.factory_home()/scripts` работает. `factory_paths.py` есть в COPY_FILES.
- Энфорсер: зеркало `_env_path`, `projects_root` и state dir совпадает с модулем, есть тест паритета. Новой зависимости от `scripts/` нет. Прежний ленивый импорт `flow_check` из `factory_home()/scripts` транзитивно тянет `factory_paths` из того же каталога и работает.
- `gate_env_strip`: валидация (список непустых строк, иначе ManifestError), `None` дает дефолт пилота, `[]` не срезает ничего. Документация в README и docs/guides/pipeline-manifest.md соответствует коду.
- Тест прошитых путей покрывает `scripts/*.py` и `plugins/**/*.py`, исключение одно (`factory_paths.py`) плюс зеркальные строки энфорсера. Тест не слишком широкий.
- Прогон: `tests/test_factory_paths.py` и `tests/test_package_runner.py` — 113 passed.

## Не проверено

- Полный сьют (1118 passed заявлено исполнителем) не перезапускался.
- Фактическое значение `HERMES_HOME` в процессах Hermes и кронах на VPS (нет доступа).
- Репозиторий ekotov-wiki и его текущие зеркала (локально отсутствует).
- `openspec validate` и `flow_check` на ветке.

## Повторная проверка (4667dad)

Вердикт: Одобрить

Проверен дифф `git diff aef66fa..HEAD`.

| # прошлого ревью | Статус | Подтверждение |
|---|---|---|
| 1 (major) | закрыт | Импорт `factory_paths` в `flow_check.py`, `pr_validate.py` и `flow_mode.py` теперь с запасным вариантом через `except ImportError`. Запасные значения используют те же env и дефолты (`AI_FACTORY_HOME`→`~/ai-factory`, `HERMES_HOME`→`~/.hermes`, `AF_STATE_DIR`→`~/.hermes/state`), пустое значение env трактуется как отсутствие, как в модуле. Воспроизведено: в каталоге без `factory_paths.py` `flow_check.py .` дал OK, `pr_validate.fp.flowctl_state_path()` и `flow_mode.DEFAULT_MODE_FILE` указывают в `~/.hermes/state`. `os` импортирован во всех трех файлах. `check_mirrors.DEFAULT_FILES` включает `factory_paths.py`. |
| 2 (major) | закрыт | `factory_paths.state_dir()` и `enforcer.state_dir()` больше не зависят от `HERMES_HOME`: дефолт `~/.hermes/state`, переопределение только через `AF_STATE_DIR`, у энфорсера сохранен приоритет `FLOW_ENFORCER_STATE_DIR`. Docstring обновлен. |
| 3–5 (minor) | открыты | Не исправлялись, возврат не обосновывают. |

Новые замечания (minor):

| # | Уровень | Файл:строка | Проблема | Сценарий отказа | Рекомендация |
|---|---|---|---|---|---|
| 6 | minor | tests/test_factory_paths.py:176 (TC-FP-009) | Паритет запасных путей проверяется только для блока в `flow_check.py`. Копии в `pr_validate.py` и `flow_mode.py` тестом не покрыты: проверка сводится к `assert "except ImportError"`, а для `flow_mode` нет и ее. | Правка одного блока без двух других разведет дефолты копий незаметно. | Параметризовать TC-FP-009 по трем файлам или вынести блок в одну функцию-генератор. |
| 7 | minor | scripts/check_mirrors.py:27 | Проект без `factory_paths.py` теперь получает статус `missing` (exit 1) при сверке зеркал. | Ожидаемый сигнал, но ekotov-wiki будет красным в сверке до досылки модуля. | Отметить в «Внимание при выкатке»: дослать `factory_paths.py` в зеркала проектов. |

Прогон: `tests/test_factory_paths.py` и `tests/test_check_mirrors.py` — 20 passed. Полный набор тестов (1121 passed заявлено) не перезапускался.
