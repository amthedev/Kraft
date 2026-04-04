import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """
    Determina a URL de conexão sync (psycopg2) para as migrations.

    Prioridade:
    1. DATABASE_URL da variável de ambiente (converte asyncpg → psycopg2)
    2. sqlalchemy.url do alembic.ini
    """
    raw = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")
    return (
        raw
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+asyncpg:", "postgresql+psycopg2:")
        .replace("?ssl=require", "?sslmode=require")
        .replace("&ssl=require", "&sslmode=require")
    )


def _connect_args() -> dict:
    """
    Retorna connect_args extras para psycopg2 quando certificados SSL estão configurados.
    Configure via variáveis de ambiente:
        DB_SSL_CERT   → caminho do client.crt
        DB_SSL_KEY    → caminho do client.key
        DB_SSL_CA     → caminho do ca.crt  (opcional, para verify-full)
    """
    cert = os.environ.get("DB_SSL_CERT", "")
    key = os.environ.get("DB_SSL_KEY", "")
    ca = os.environ.get("DB_SSL_CA", "")
    if not (cert and key):
        return {}
    args: dict = {"sslcert": cert, "sslkey": key, "sslmode": "verify-full" if ca else "require"}
    if ca:
        args["sslrootcert"] = ca
    return args


def run_migrations_offline() -> None:
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    sync_url = _get_sync_url()
    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
        connect_args=_connect_args(),
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
