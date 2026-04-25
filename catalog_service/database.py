import os
import re

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "CATALOG_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/catalog_db",
)
DB_SCHEMA = os.getenv("CATALOG_DB_SCHEMA", "catalog")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base(metadata=MetaData(schema=DB_SCHEMA))

_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema_name(schema: str) -> str:
    if not _SCHEMA_NAME_RE.fullmatch(schema):
        raise ValueError(f"Invalid PostgreSQL schema name: {schema!r}")
    return schema


def init_db() -> None:
    from . import models  # noqa: F401

    schema = _validate_schema_name(DB_SCHEMA)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(bind=engine)
