---
name: test-automation
description: Implement approved test cases as pytest+requests and pytest+playwright suites with tracing.
---

# Автоматизация тест-кейсов

Как превратить одобренные тест-кейсы в изолированные детерминированные автотесты. Стек конвейера: Python, pytest, requests (API), playwright (web).

## Когда применять

- Кейсы появились в `test-model/approved/<change-id>/`
- Расширение существующего набора тестов новыми одобренными кейсами

Не применять для: кейсов в `test-model/new/` (не прошли ревью), правки продукта (находка дефекта → баг-репорт).

## Структура тестового проекта

```
tests/
├── api/                        # pytest + requests
│   ├── conftest.py             # фикстуры: base_url, auth, http-сессия
│   └── test_<domain>.py
├── web/                        # pytest-playwright
│   ├── conftest.py             # фикстуры: браузер, контекст, base_url
│   └── test_<domain>_ui.py
└── README.md                   # запуск, env-переменные, маркеры
```

## Процедура

1. **Проверь вход:** кейсы лежат в `approved/`, review с вердиктом «одобрить» существует. Нет — работа не начинается, это контракт 6.
2. **Каркас фикстур до тестов.** `base_url` из переменной окружения, HTTP-сессия с auth, браузерный контекст. Тесты без фикстур размножают настройку и гниют при смене окружения.
3. **1 кейс = 1 тест минимум.** В docstring — ID кейса (`TC-pages-001`) — это трассировка, по ней матрица в `tests/README.md`. Тест без ID — дефект.
4. **Маркеры:** `@pytest.mark.api` / `@pytest.mark.web` для выбора набора; `@pytest.mark.must/should/could` для приоритета MoSCoW из кейса.
5. **Ассерты = ожидаемый результат кейса.** Дословно: кейс требует «200 OK, тело содержит token (JWT)» → два ассерта: статус и валидность JWT. Ослабленный ассерт «код 2xx» — скрытая потеря проверки.
6. **Изоляция:** каждый тест создает свои данные через фикстуры (setup) и убирает (teardown). Тест, зависящий от порядка запуска или данных другого теста, — флак в CI.
7. **Детерминизм:** никаких `time.sleep`. Web — автожидания Playwright (`expect(...).to_be_visible()`), API — poll-цикл с таймаутом. Sleep «пока заработает» — отсроченный флак.
8. **Прогон и фиксация результата.** Падение? Сначала проверь код теста против кейса. Тест верен → баг-репорт в `test-model/bugs/` (кейс, ожидание, факт, окружение). Править ассерт «чтобы был зеленый» — запрещено: это маскировка дефекта продукта.

## Шаблон API-теста

```python
import pytest, requests

pytestmark = [pytest.mark.api, pytest.mark.must]

def test_login_returns_token(base_url, http_session):
    """TC-auth-001: валидный логин возвращает JWT (FR-1)"""
    resp = http_session.post(f"{base_url}/api/auth/login",
                             json={"login": "test_user_1", "password": "Corr3ct_Pass!"})
    assert resp.status_code == 200
    assert "token" in resp.json()
```

## Ошибки

- Хардкод `http://localhost:8000` в тестах — окружение только через переменные.
- Тест без docstring-ID — трассировка разорвана.
- Свежесозданный тест мимо approved-кейса — «улучшение» мимо процесса; идея → новый кейс через ПМ.
