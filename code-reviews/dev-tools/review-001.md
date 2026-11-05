Вердикт: Вернуть

# Ревью J65.12 dev-tools — review-001

- Ревьюемый коммит: `60a42f273eab3fc33fbbbd10ee8de59c33d1b4df` (ветка `chore/dev-tools`)
- Файлы: `scripts/ci_local.py`, `scripts/factory_paths.py`, `README.md`, `tests/test_j65_dev_tools.py`, `PLAN-dev-tools.md`
- Арбитр: PLAN-dev-tools.md (Флоу 4), backlog J65.12 («обе команды описаны в README и работают на Mac и VPS»), `.github/workflows/flow.yml`
- Ревьюер: независимый сабагент code_reviewer; автором диффа не является.

## Замечания

| # | Серьезность | Место | Суть |
|---|---|---|---|
| 1 | major | scripts/ci_local.py:47-48, 78, 79-82, 87 | git-шаги подготовки наследуют `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` из окружения → `fetch --depth 1` идет в ИСХОДНЫЙ репозиторий и делает его shallow |
| 2 | major | scripts/factory_paths.py:140 | `compare` ключует значения по `label` — снимки с одинаковой меткой схлопываются, расхождение не видно (ложный OK) |
| 3 | minor | scripts/factory_paths.py:140, 160 | битый/неполный JSON: traceback c rc 1 (тот же код, что «расхождение»); `{}` против `{}` → OK; один снимок → OK |
| 4 | minor | scripts/ci_local.py:78, 87 | коды выхода: сбой `git init` → traceback rc 1 вместо 2; rc `checkout FETCH_HEAD` не проверяется |
| 5 | minor | scripts/ci_local.py:42, 92; README.md:70-79 | паритет с CI неполный и не задокументирован: Python не 3.12, user-site/пакеты машины видны, PR в CI гоняется на merge-коммите |
| 6 | minor | scripts/ci_local.py:9 | докстринг: «`git clone --depth 1`», реализация — `init` + `fetch` по SHA; «воспроизводит job test-flow-control», а flow_check — шаг job `flow` |
| 7 | minor | tests/test_j65_dev_tools.py:109, 54 | fixture-коммиты зависят от глобального git-конфига (gpgsign/hooks); `len(diffs) == 3` хрупко |
| 8 | minor | tests/test_j65_dev_tools.py | нет тестов на замечания 1-3 и на ветку `--out <файл>` / `~` |

### 1 (major). GIT_* из окружения — ci_local портит исходный репозиторий

`_git()` и `git init` запускаются с полным `os.environ`. Если `GIT_DIR` экспортирован, а git экспортирует его в хуки (естественный сценарий: «ci_local в pre-push»), то `git init <clone>` повторно инициализирует исходный репозиторий, `git -C <clone> fetch --depth 1 ... <sha>` пишет в **исходный** `.git` файл `shallow`, а прогон идет по пустому клону.

Воспроизведено (scratch-репозиторий из 3 коммитов):

```
GIT_DIR=$S/r/.git python3 scripts/ci_local.py --repo $S/r
→ ci_local: FAIL — pytest (rc=1), flow_check (rc=2)   # пустой клон
git -C $S/r rev-parse --is-shallow-repository → true; rev-list --count HEAD → 1
$S/r/.git/shallow существует
```

История исходного репозитория обрезана до одного видимого коммита, вывод при этом выглядит как обычный красный прогон. Для пользователя это молчаливая порча данных, а для ворот ancestry-класса (BUG-022/023/024) это прямой яд: shallow-состояние локального клона меняет поведение `pr_validate`.

Рекомендация: собрать для git-подготовки env без `GIT_*` (как минимум `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CEILING_DIRECTORIES`, `GIT_CONFIG*`) и передавать его в `subprocess.run(..., env=...)` в `_git` и `git init`. Можно проще: убрать все ключи с префиксом `GIT_`. Нужен тест: прогон с `GIT_DIR` исходного репо, после него исходный репо не shallow, а прогон PASS.

### 2 (major). compare: одинаковые метки дают ложный OK

`values = {s.get("label", "?"): ...}`: при совпадении меток остается значение последнего снимка, и `set(values.values())` содержит один элемент.

```
AF_STATE_DIR=/x factory_paths.py --doctor shell --out a.json
AF_STATE_DIR=/y factory_paths.py --doctor shell --out b.json
factory_paths.py --compare a.json b.json
→ OK — пути совпадают во всех контекстах (shell, shell)   # state_dir /x ≠ /y
```

Реальные сценарии: снимок `shell` с Mac и снимок `shell` с VPS (приемка J65.12 — «Mac и VPS»), повторный снимок после правки env, снимки без `label` (`?`). Инструмент существует, чтобы находить расхождения, и сообщает OK там, где оно есть.

Рекомендация: сравнивать список значений по индексу снимка, а метку для вывода брать как `label` или имя файла с суффиксом при повторе. Минимум — отказ (rc 2) при дублирующихся метках. Тест: два снимка с одной меткой и разными путями → rc 1.

### 3 (minor). compare: битый/неполный вход

- Невалидный JSON дает `JSONDecodeError`, JSON-список дает `AttributeError` (проверено). Оба выходят с rc 1, тем же кодом, что и «РАСХОЖДЕНИЕ». Скрипт, проверяющий только код выхода, их не различит.
- Снимки без `paths` (`{}` против `{}`) дают «OK — пути совпадают (?, ?)», то есть ложный OK.
- Один снимок дает OK. Сверять там нечего, это должно быть ошибкой использования.

Рекомендация: валидировать вход (dict, есть `paths` с ключами `describe()`), ошибки входа печатать в stderr с rc 2, требовать не меньше двух снимков.

### 4 (minor). ci_local: коды выхода подготовки

Докстринг обещает «2 — ошибка подготовки». `subprocess.run(["git","init",...], check=True)` (стр. 78) при сбое бросает `CalledProcessError`: traceback, rc 1, то есть «красный шаг». rc у `checkout -q FETCH_HEAD` (стр. 87) не проверяется: при сбое тесты идут по пустому дереву и падают как «pytest rc=5». Рекомендация: проверять rc обоих шагов и возвращать 2 с сообщением.

### 5 (minor). Паритет с CI: что отличается и не названо

Сверка с `flow.yml`:

- Python: `sys.executable` (на машине ПМ 3.14), в CI `setup-python` 3.12. Стоит печатать версию и предупреждать, если она не 3.12.
- Пакеты: в CI есть только `pytest` поверх чистого setup-python. Локально `PYTHONUSERBASE` сохраняется (стр. 42), и user-site разработчика остается виден. Класс «нет модуля в CI» (ретро E16: bcrypt/playwright) инструмент не ловит. Сохранять user-site ради pytest оправданно (BUG-025), но это стоит назвать в README как ограничение. Опция: `--venv`, чистый venv только с pytest.
- Коммит: для `pull_request` actions/checkout берет merge-коммит `refs/pull/N/merge`, ci_local берет HEAD ветки. Конфликтующее с main поведение не воспроизводится. Это тоже ограничение для README.
- HOME: в CI `/home/runner`, он не пустой. Пустой HOME строже CI. Это допустимо, но формулировку «как в CI» стоит уточнить словами «строже CI».
- В клоне нет remote `origin` и ветки (detached HEAD). В CI origin есть. Полный сьют на фабрике зеленый (данные ПМ), то есть сейчас это не мешает, но стоит упомянуть.
- TMPDIR сохраняется: на macOS это `/var/folders/...` (симлинк `/private/var`). Расхождение `resolve()` возможно, но и на машине вне ci_local оно то же. Замечаний нет.

### 6 (minor). Неточности в описании

`ci_local.py:9` пишет «`git clone --depth 1`», хотя реализация (и комментарий на стр. 75-77) использует `init` + `fetch` по SHA. Docstring и README говорят «воспроизводит/повторяет job test-flow-control», но `flow_check` — шаг job `flow`. README в остальном точен: оговорка про `openspec validate` есть. Рекомендация: «pytest как job test-flow-control + flow_check как в job flow».

### 7 (minor). Хрупкость тестов

- `_fixture_repo` (стр. 109) коммитит с глобальным конфигом разработчика. `commit.gpgsign=true` или глобальный `core.hooksPath` уронят TC-005/006 вне ci_local. Рекомендация: `-c commit.gpgsign=false -c core.hooksPath=/dev/null` или `GIT_CONFIG_GLOBAL=/dev/null` в env фикстуры.
- `assert len(diffs) == 3` (стр. 54) жестко завязан на число производных от `state_dir` путей в `describe()`. Новый производный путь уронит тест без дефекта. Лучше сравнить множество ключей `{"state_dir","registry","flowctl_state"}`.
- TC-005 проверяет shallow, пустой HOME и отсутствие грязной правки, но не то, что клон стоит именно на HEAD (а не на первом коммите). Например, можно сверить `git rev-parse HEAD` в пробе с SHA, переданным через файл в коммите.

### 8 (minor). Покрытие

Нет тестов на замечания 1 и 2 (нужны как регресс при доработке), на ветку `--out <файл>` без слеша, на существующий каталог без слеша и на `~` в `--out`.

## Проверено

- Тесты (точечно, свежий прогон): `HOME=.../scratchpad/vps-home python3.14 -m pytest tests/test_j65_dev_tools.py tests/test_factory_paths.py tests/test_check_mirrors.py -q -p no:cacheprovider` дал **28 passed**.
- factory_paths как копируемый модуль: новые импорты (`argparse`, `json`, `getpass`, `sys`) локальны в функциях, побочных эффектов при импорте нет, только stdlib. `Path.is_relative_to` есть с 3.9, требование ≥3.10 соблюдено. Функции путей и `describe()` не изменены. Вывод без аргументов прежний (TC-FP проверяет его subprocess-ом, тест зеленый). Ключ `factory_paths.py` в `factory_init` COPY_FILES не тронут, TC-FP-009/010 и test_check_mirrors зеленые.
- Прошитых путей машины в новом коде нет (TC-FP-004 зеленый).
- `--compare` на битом и неполном JSON, с дублем меток, на одном снимке; `--out` в несуществующий вложенный путь дает FileNotFoundError traceback (ожидаемо, но без дружелюбного сообщения). Факты — в замечаниях 2 и 3.
- ci_local с экспортированным `GIT_DIR`: воспроизведена порча исходного репо (замечание 1).
- Сверка ci_local с flow.yml по шагам: env, Python, пакеты, checkout (замечание 5). Fetch по SHA через `uploadpack.allowAnySHA1InWant` корректен для worktree и detached HEAD (`rev-parse HEAD` worktree плюс file://-URL). Submodules и LFS в репозитории фабрики отсутствуют (`.gitmodules` и `.gitattributes` нет), поэтому их неподдержка сейчас не дефект. Очистка `rmtree` в `finally` корректна, `--keep` работает по коду.
- README: команды и пути (`~/ai-factory` совпадает с дефолтом `factory_home()`, `--out ~/af-doctor/` со слешем дает каталог, glob в `--compare`) корректны.
- Трассировка: TC-J65-DT-001..006 есть в docstring и в каждом тесте. План с `Флоу: 4` и манифестом есть, состав диффа соответствует плану.

## Не проверено

- Полный сьют и ci_local на самой фабрике: не повторялись по указанию ПМ (данные ПМ: 1135 passed, 2 skipped, flow_check OK; мутации ловятся).
- Работа на VPS (Linux, системный git и Python) и из реального крона/процесса Hermes.
- Поведение при `commit.gpgsign=true` в глобальном конфиге: выведено из кода, не воспроизводилось.
- Прогон ci_local из реального git-хука, кроме имитации через `GIT_DIR`.

## Примечание о формате

Первая строка в форме `Вердикт: Вернуть` — по требованию ПМ и манифесту плана (`contains: "Вердикт: Одобрить"`). Роль-промпт code_reviewer требует машиночитаемый заголовок `## Вердикт: approve|return` и мету `Reviewer-Delegation:`. Если ворота pr_validate/J10 парсят этот формат, ПМ стоит согласовать.

## Исправления по возврату (ПМ)

- **Major 1** `ci_local`: git-шаги идут с `git_env()` — без `GIT_*` и без глобального/системного git-конфига (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`). TC-J65-DT-007: прогон с `GIT_DIR`/`GIT_WORK_TREE` исходного репо — источник не shallow, история цела; мутация (вернуть GIT_*) — тест красный.
- **Major 2** `compare`: снимки именуются по метке и имени файла, совпадающие метки — с номером (`shell#1`/`shell#2`). TC-J65-DT-008: shell/Mac против shell/VPS — расхождение видно; мутация (без различения) — тест красный.
- №3 `--compare`: битый JSON, не-объект, без `paths`, неполный снимок, отсутствующий файл, один снимок — exit 2 с причиной (TC-J65-DT-009).
- №4 `ci_local`: init/fetch/checkout — каждый с проверкой rc → exit 2 (TC-J65-DT-011 — не git-репозиторий).
- №5–6: отличия от CI перечислены в docstring и README; формулировка — «условия CI для pytest (test-flow-control) и flow_check (шаг job flow)», docstring описывает init+fetch.
- №7: fixture-коммиты с `commit.gpgsign=false` и `core.hooksPath=/dev/null`; проверка состава diff — по ключам, не по числу; TC-005 проверяет, что клон на HEAD (коммит «two»).
- №8: `--out <файл>` и путь с `~` — TC-J65-DT-010.
