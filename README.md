# FastAPI микросервисы: catalog, orders, auth, admin и API Gateway

## Архитектура

```
        ┌─────────────────────────┐
        │ Frontend (Vite, :5173)  │
        └──────────┬──────────────┘
                   │  HTTP (с JWT в Authorization)
                   ▼
        ┌─────────────────────────┐
        │ API Gateway (:8080)     │
        └─┬───────┬───────┬─────┬─┘
          │       │       │     │
   /auth/*│ /catalog/* │ /order/* │ /admin/*
          ▼       ▼       ▼     ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────┐
   │ Auth   │ │Catalog │ │ Order  │ │ Admin   │
   │ :8002  │ │ :8000  │ │ :8001  │ │ :8003   │
   └────────┘ └───┬────┘ └───┬────┘ └────┬────┘
                 │           │           │
                 │  Kafka    │  Kafka    │
                 ▼           ▼           │
              catalog.commands  ◄────────┘
              order.commands    ◄────────┘
              admin.replies     ─────────► admin
```

- **Auth Service** выпускает JWT-токены при регистрации/логине.
- **Catalog** и **Order** проверяют JWT для эндпоинтов изменения данных.
- **Admin Service** — отдельный сервис администрирования. Все его эндпоинты
  требуют JWT (выпущенный auth_service). Любая команда из admin_service
  доставляется в catalog_service / order_service **только через Kafka**
  (request-reply поверх kafka-топиков).
- Все сервисы используют **общий `JWT_SECRET`**, поэтому каждый умеет локально
  валидировать токен без обращения к auth.
- Фронтенд обращается **только в API Gateway** (`http://127.0.0.1:8080`).

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Kafka

Admin Service обменивается командами/ответами с catalog/order через Kafka.
Поднимите Kafka локально (через Docker):

```bash
docker run -d --name zookeeper -p 2181:2181 wurstmeister/zookeeper:latest
docker run -d --name kafka -p 9092:9092 \
  -e KAFKA_ZOOKEEPER_CONNECT=host.docker.internal:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://127.0.0.1:9092 \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092 \
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true \
  wurstmeister/kafka:latest
```

Или используйте любой подходящий kafka-стэк (Bitnami, Confluent, Redpanda и т.д.).
По умолчанию сервисы ходят в `KAFKA_BOOTSTRAP_SERVERS=localhost:9092`.

Используемые топики (создаются автоматически при `KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`):

- `catalog.commands` — команды admin → catalog_service
- `order.commands`   — команды admin → order_service
- `admin.replies`    — ответы catalog/order → admin

## Настройка PostgreSQL

Создайте три БД в PostgreSQL:

- `catalog_db`
- `order_db`
- `auth_db`

Переменные окружения перед запуском (общий `JWT_SECRET` обязателен):

```bash
set JWT_SECRET=super-secret-change-me
set JWT_ALGORITHM=HS256
set JWT_EXPIRES_MINUTES=60

set CATALOG_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/catalog_db
set ORDER_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/order_db
set AUTH_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/auth_db

set CATALOG_DB_SCHEMA=catalog
set ORDER_DB_SCHEMA=orders
set AUTH_DB_SCHEMA=auth

set KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

Инициализация схем и таблиц:

```bash
python -m catalog_service.init_db
python -m order_service.init_db
python -m auth_service.init_db
```

## Запуск сервисов

Каждый сервис нужно запускать в **отдельном терминале** (с экспортированными
переменными окружения).

Catalog service (порт 8000):

```bash
uvicorn catalog_service.main:app --host 0.0.0.0 --port 8000 --reload
```

Order service (порт 8001):

```bash
set CATALOG_SERVICE_URL=http://127.0.0.1:8000
uvicorn order_service.main:app --host 0.0.0.0 --port 8001 --reload
```

Auth service (порт 8002):

```bash
uvicorn auth_service.main:app --host 0.0.0.0 --port 8002 --reload
```

Admin service (порт 8003):

```bash
uvicorn admin_service.main:app --host 0.0.0.0 --port 8003 --reload
```

API Gateway (порт 8080):

```bash
set AUTH_SERVICE_URL=http://127.0.0.1:8002
set CATALOG_SERVICE_URL=http://127.0.0.1:8000
set ORDER_SERVICE_URL=http://127.0.0.1:8001
set ADMIN_SERVICE_URL=http://127.0.0.1:8003
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8080 --reload
```

После этого фронтенд (ДЗ3) должен ходить только в **API Gateway**
(`http://127.0.0.1:8080`).

## Эндпоинты

### Auth Service (через `/auth` в gateway)

- `POST /auth/register` — регистрация, возвращает JWT
- `POST /auth/login` — логин, возвращает JWT
- `GET  /auth/me` — данные текущего пользователя (требует Bearer токен)
- `GET  /auth/verify` — проверка валидности токена

### Catalog Service (через `/catalog` в gateway) — публичное чтение

- `GET    /catalog` — список товаров
- `GET    /catalog/{id}` — товар по id
- `GET    /catalog/feature-3-values` — значения фильтра

Прямые `POST /catalog`, `PUT /catalog/{id}`, `DELETE /catalog/{id}` оставлены
для обратной совместимости, но **админка фронтенда** работает через admin_service.

### Order Service (через `/order` в gateway) — публичные операции с заказом

- `GET  /order/{number}` — посмотреть заказ по номеру (публично)
- `POST /order` — оформить заказ из корзины (публично)

### Admin Service (через `/admin` в gateway) — **требует JWT для всех эндпоинтов**

- `POST   /admin/catalog`           — создать товар (Kafka → catalog_service)
- `PUT    /admin/catalog/{id}`      — обновить товар (Kafka → catalog_service)
- `DELETE /admin/catalog/{id}`      — удалить товар (Kafka → catalog_service)
- `GET    /admin/order`             — список заказов (Kafka → order_service)
- `PUT    /admin/order/{id}`        — обновить заказ (Kafka → order_service)
- `DELETE /admin/order/{id}`        — удалить заказ (Kafka → order_service)

Для защищённых эндпоинтов передавайте заголовок:

```
Authorization: Bearer <access_token>
```

## Как работает Kafka request-reply

1. Клиент шлёт `POST /admin/catalog` в gateway → admin_service.
2. Admin_service генерирует `correlation_id`, формирует конверт
   `{correlation_id, reply_topic: "admin.replies", operation, payload}`
   и продюсит его в `catalog.commands`.
3. Consumer внутри catalog_service читает сообщение из `catalog.commands`,
   выполняет операцию в БД и продюсит ответ в `admin.replies`
   с тем же `correlation_id`.
4. Admin_service параллельно консьюмит `admin.replies`, сопоставляет ответ по
   `correlation_id` с ожидающим запросом и возвращает результат клиенту.
5. Аналогично работает связка `order.commands` ↔ `admin.replies` для заказов.
