# FastAPI microservices: catalog and orders

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## PostgreSQL setup

Create two databases in PostgreSQL:

- `catalog_db`
- `order_db`

Set environment variables before running services:

```bash
set CATALOG_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/catalog_db
set ORDER_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/order_db
set CATALOG_DB_SCHEMA=catalog
set ORDER_DB_SCHEMA=orders
```

Initialize schema and create missing tables from application scripts:

```bash
python -m catalog_service.init_db
python -m order_service.init_db
```

## Run services

Catalog service (port 8000):

```bash
uvicorn catalog_service.main:app --host 0.0.0.0 --port 8000 --reload
```

Order service (port 8001):

```bash
set CATALOG_SERVICE_URL=http://127.0.0.1:8000
uvicorn order_service.main:app --host 0.0.0.0 --port 8001 --reload
```

## Postman endpoint mapping

Catalog service:

- `GET /catalog`
- `GET /catalog/{id}`
- `POST /catalog`
- `PUT /catalog/{id}`
- `DELETE /catalog/{id}`

Order service:

- `GET /order/{number}`
- `POST /order`
- `PUT /order/{id}`
- `DELETE /order/{id}`
