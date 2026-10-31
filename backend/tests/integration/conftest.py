"""Postgres 16 + Redis 7 via testcontainers; Postgres migrated with Alembic once per session."""

import asyncio
import base64
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.deps import Deps, build_deps, set_deps
from app.main import create_app
from app.security import crypto
from app.settings import BASE_DIR, Settings, get_settings

TABLES = (
    "audit_log, applications, cvs, job_scores, ghost_signals, job_postings_history, "
    "job_sightings, jobs, companies, profiles, oauth_tokens, oauth_authorization_codes, "
    "oauth_clients, users"
)
ORIGIN = "http://localhost:3000"
TEST_KEY = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture(scope="session")
def pg_urls() -> Iterator[tuple[str, str]]:
    with PostgresContainer("postgres:16", driver=None) as pg:
        host, port = pg.get_container_host_ip(), pg.get_exposed_port(5432)
        auth = f"{pg.username}:{pg.password}@{host}:{port}/{pg.dbname}"
        sync_url = f"postgresql+psycopg://{auth}"
        cfg = Config(str(BASE_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        cfg.set_main_option("sqlalchemy.url", sync_url)
        command.upgrade(cfg, "head")
        yield sync_url, f"postgresql+asyncpg://{auth}"


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture
async def session(pg_urls: tuple[str, str]) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(pg_urls[1])
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def deps_(pg_urls: tuple[str, str], redis_url: str) -> AsyncIterator[Deps]:
    settings = Settings(
        env="test",
        public_origin=ORIGIN,
        database_url=pg_urls[1],
        database_url_sync=pg_urls[0],
        redis_url=redis_url,
        secret_key=SecretStr("test-secret"),
        profile_keys=SecretStr(f"1:{TEST_KEY}"),
    )
    engine = create_async_engine(pg_urls[1])
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    redis = Redis.from_url(redis_url, decode_responses=True)
    await redis.flushdb()
    crypto.keyring.cache_clear()
    os.environ["RJF_PROFILE_KEYS"] = f"1:{TEST_KEY}"
    get_settings.cache_clear()
    d = build_deps(settings, async_sessionmaker(engine, expire_on_commit=False), redis)
    set_deps(d)
    yield d
    await redis.aclose()
    await engine.dispose()


@pytest.fixture
async def client(deps_: Deps) -> AsyncIterator[AsyncClient]:
    app = create_app(deps_)
    started, stop = asyncio.Event(), asyncio.Event()

    async def run_lifespan() -> None:
        # Enter and exit the lifespan in one task (anyio cancel scopes require it).
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    task = asyncio.create_task(run_lifespan())
    await started.wait()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as c:
            yield c
    finally:
        stop.set()
        await task
