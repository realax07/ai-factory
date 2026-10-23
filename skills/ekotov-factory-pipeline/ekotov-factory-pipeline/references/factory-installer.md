# Установщики фабрики: factory_init.py и factory_bootstrap.py

## factory_init.py — отставание от состава фабрики

Новый скрипт или скилл в фабрике = правка factory_init.py в ТОМ ЖЕ PR: добавить в COPY_FILES (скрипты, контракты, шаблоны) или SKILL_DIRS (скиллы-каталоги). Установщик, отставший от состава фабрики, разворачивает неполный конвейер — это всплывает не сразу, а на следующей машине или проекте.

Дубли в COPY_FILES безвредны, но засоряют (код graph был задвоен — чистить при случае). Скиллы добавляются КАТАЛОГАМИ в SKILL_DIRS, не файлами.

Верификация после правки: прогон на tmp-репо —

```
git init /tmp/factory-init-test && cd /tmp/factory-init-test
python3 ~/ai-factory/scripts/factory_init.py --target /tmp/factory-init-test --name Test
# ожидание: FACTORY-INIT OK, post-init flow_check exit 0
```

Заголовок docstring «Что устанавливается» правится вместе со списками — это документация установщика.

## Пустой проект обязан рождаться ЗЕЛЕНЫМ в CI

Верификация на tmp-репо прогоном flow_check — недостаточно: flow_check не видит CI-слоя. После инициализации НОВОГО репо пуши main и дожди реальный прогон flow.yml до доклада «готово» (на child_bot оба джоба упали на пустом проекте при локально-зеленом flow_check). Минимальный набор для зелени, включенный в factory_init:

- `openspec/config.yaml` (schema: spec-driven + context Language: ru) — root-маркер openspec CLI; без него `validate --all --strict` падает «No OpenSpec root found»;
- `tests/test_smoke.py` с TC-трассировкой в docstring (`TC-BOOTSTRAP-001: …`) — без TC-ref flow_check краснеет «тесты без TC-трассировки» (rule 6);
- `test-model/regression/_bootstrap/smoke.md` — as-is база под контракт 6 (тесты без approved-кейсов без нее = FLOW-ERROR).

Правь установку и шаблон ОДНИМ коммитом: MKDIRS без файла, файл без каталога, или правка в упавшем ранее скрипте-патче (assert-abort откатывает весь батч) — каждый вариант ловится только реальным прогоном factory_init после правки.

## Права на НОВЫЙ репо: проверь viewerPermission до обещаний пула

Машинная git-учетка может иметь write на старые репо Заказчика и только READ на новый (реальный кейс: реальный блок push после полного локального init). До старта работ: `gh repo view <owner>/<repo> --json viewerPermission --jq .viewerPermission` — не WRITE → попроси Заказчика добавить машинный аккаунт в collaborators ДО init, иначе готовый init висит непушенным. Push: свежеклонированный репо по умолчанию https-remote — переводи на SSH (`git remote set-url origin git@github.com:...git`), https-пуш без credential-helper падает «could not read Username».

## factory_bootstrap.py — машина, не проект

Ставит окружение МАШИНЫ: state-каталоги, flow_mode.json (дефолт shadow — enforcing явным решением), крон вотчдога, приемочный тест pytest фабрики. Секреты не переносит. factory_init (проект) и factory_bootstrap (машина) дополняют друг друга — правки установщика одного уровня не должны терять другой.

## Расширение под плагины (J43, при реализации)

factory_init добавляет установку/апгрейд плагина flow-enforcer (источник — каталог plugins/ в фабрике) и правку plugins.enabled в config.yaml целевой машины. Детали — references/plan-release-gates.md.
