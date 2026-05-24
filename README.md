# FastAPI микросервисы: catalog, orders, auth и API Gateway

## Архитектура

```
        ┌─────────────────────────┐
        │ Frontend (Vite, :5173)  │
        └──────────┬──────────────┘
                   │  HTTP (с JWT в Authorization)
                   ▼
        ┌─────────────────────────┐
        │ API Gateway (:8080)     │
        └─┬─────────┬───────────┬─┘
          │         │           │
   /auth/*│ /catalog/*  │ /order/*
          ▼         ▼           ▼
   ┌──────────┐ ┌─────────┐ ┌─────────┐
   │ Auth     │ │ Catalog │ │ Order   │
   │ (:8002)  │ │ (:8000) │ │ (:8001) │
   └──────────┘ └─────────┘ └─────────┘
```

- **Auth Service** выпускает JWT-токены при регистрации/логине.
- **Catalog** и **Order** проверяют JWT для эндпоинтов изменения данных.
- Все три сервиса используют **общий `JWT_SECRET`**, поэтому сервис каталога и заказов могут локально валидировать токен без обращения к auth.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка PostgreSQL

Создайте три БД в PostgreSQL:

- `catalog_db`
- `order_db`
- `auth_db`

Переменные окружения перед запуском (общий `JWT_SECRET` обязателен для всех 3 сервисов):

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
```

Инициализация схем и таблиц:

```bash
python -m catalog_service.init_db
python -m order_service.init_db
python -m auth_service.init_db
```

## Запуск сервисов

Каждый сервис нужно запускать в **отдельном терминале** (с экспортированными переменными окружения).

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

API Gateway (порт 8080):

```bash
set AUTH_SERVICE_URL=http://127.0.0.1:8002
set CATALOG_SERVICE_URL=http://127.0.0.1:8000
set ORDER_SERVICE_URL=http://127.0.0.1:8001
uvicorn api_gateway.main:app --host 0.0.0.0 --port 8080 --reload
```

После этого фронтенд (ДЗ3) должен ходить только в **API Gateway** (`http://127.0.0.1:8080`).

## Эндпоинты

### Auth Service (через `/auth` в gateway)

- `POST /auth/register` — регистрация, возвращает JWT
- `POST /auth/login` — логин, возвращает JWT
- `GET  /auth/me` — данные текущего пользователя (требует Bearer токен)
- `GET  /auth/verify` — проверка валидности токена

### Catalog Service (через `/catalog` в gateway)

- `GET    /catalog` — публично
- `GET    /catalog/{id}` — публично
- `GET    /catalog/feature-3-values` — публично
- `POST   /catalog` — **требует JWT**
- `PUT    /catalog/{id}` — **требует JWT**
- `DELETE /catalog/{id}` — **требует JWT**

### Order Service (через `/order` в gateway)

- `GET    /order/{number}` — публично
- `POST   /order` — публично (оформление заказа из корзины)
- `PUT    /order/{id}` — **требует JWT**
- `DELETE /order/{id}` — **требует JWT**

Для защищённых эндпоинтов передавайте заголовок:

```
Authorization: Bearer <access_token>
```
