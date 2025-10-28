# NetBox Server Setup (SQLite + fakeredis)

Этот проект был портирован с PostgreSQL и Redis на in-memory SQLite и fakeredis для упрощения локальной разработки и тестирования.

## Быстрый старт

### Автоматический запуск

```bash
chmod +x start_server.sh
./start_server.sh
```

### Ручной запуск

Если вы хотите выполнить шаги вручную:

```bash
# 1. Активировать виртуальное окружение
source .venv/bin/activate

# 2. Применить миграции базы данных
python manage.py migrate --noinput

# 3. Собрать статические файлы
python manage.py collectstatic --noinput

# 4. Создать суперпользователя (опционально, если еще не создан)
python manage.py createsuperuser --noinput --username admin --email admin@example.com
# Установить пароль
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); u = User.objects.get(username='admin'); u.set_password('admin'); u.save()"

# 5. Запустить сервер
python manage.py runserver 0.0.0.0:8000
```

## Доступ к серверу

- **URL**: http://127.0.0.1:8000/
- **Логин**: `admin`
- **Пароль**: `admin`

## API

### Получение токена

```bash
python manage.py shell -c "from users.models import Token; from django.contrib.auth import get_user_model; User = get_user_model(); u = User.objects.get(username='admin'); t, created = Token.objects.get_or_create(user=u); print(t.key)"
```

### Примеры использования API

```bash
# Получить токен (замените YOUR_TOKEN на реальный токен)
TOKEN="your_token_here"

# Получить список всех API endpoints
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/

# Получить статус сервера
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/status/

# Получить список сайтов
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/dcim/sites/

# Создать новый сайт
curl -X POST -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Test Site", "slug": "test-site"}' \
  http://127.0.0.1:8000/api/dcim/sites/

# Получить список устройств
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/dcim/devices/

# Получить список IP адресов
curl -H "Authorization: Token $TOKEN" http://127.0.0.1:8000/api/ipam/ip-addresses/
```

## Конфигурация

### Основные файлы конфигурации

- **`netbox/configuration.py`** - основная конфигурация для сервера
- **`netbox/configuration_testing.py`** - конфигурация для тестов
- **`netbox/settings.py`** - настройки Django

### База данных

Проект использует SQLite с файлом базы данных `netbox.db` в корне проекта.

Для тестов используется in-memory база данных (`:memory:`), которая автоматически выбирается при запуске `python manage.py test`.

### Redis

Проект использует `fakeredis` - in-memory реализацию Redis, которая не требует запуска отдельного сервера Redis.

## Тестирование

```bash
# Запустить все тесты
source .venv/bin/activate && python manage.py test

# Запустить конкретный тест
source .venv/bin/activate && python manage.py test utilities.tests.test_filters

# Запустить тесты параллельно
source .venv/bin/activate && python manage.py test --parallel
```

## Известные проблемы

### TypeError при POST запросах через API

При создании объектов через API может возникать ошибка `TypeError` после успешного создания объекта. Это не критично - объект создается корректно, ошибка возникает при формировании ответа. Это известная проблема совместимости SQLite с NetBox.

### Ограничения SQLite

NetBox изначально разработан для PostgreSQL, поэтому некоторые функции могут работать не полностью корректно с SQLite:

- Некоторые сложные запросы могут работать медленнее
- Полнотекстовый поиск ограничен
- Некоторые специфичные для PostgreSQL функции недоступны

Эта конфигурация предназначена для локальной разработки и тестирования, **не для production использования**.

## Очистка

Для полной очистки и перезапуска:

```bash
# Удалить базу данных
rm -f netbox.db

# Запустить скрипт заново
./start_server.sh
```

## Структура проекта

```
netbox/
├── netbox/
│   ├── configuration.py          # Конфигурация сервера
│   ├── configuration_testing.py  # Конфигурация тестов
│   └── settings.py               # Настройки Django
├── utilities/
│   ├── fakeredis_shim.py        # Shim для fakeredis
│   └── sqlite_collations.py     # SQLite collations для совместимости
├── manage.py                     # Django management script
├── start_server.sh              # Скрипт запуска сервера
└── netbox.db                    # База данных SQLite (создается автоматически)
```
