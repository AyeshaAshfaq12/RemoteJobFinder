"""Alembic env: runs migrations with the sync psycopg URL from settings."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.settings import get_settings

config = context.config


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url_sync, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url_sync
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
