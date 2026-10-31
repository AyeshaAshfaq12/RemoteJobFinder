"""Process-wide dependencies, built once at startup and replaceable in tests."""

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.provider import PostgresOAuthProvider
from app.auth.web import EmailCodes, Mailer, Sessions
from app.db.session import get_sessionmaker
from app.settings import Settings, get_settings


@dataclass
class Deps:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    provider: PostgresOAuthProvider
    codes: EmailCodes
    sessions: Sessions
    mailer: Mailer


_deps: Deps | None = None


def build_deps(
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    redis: Redis | None = None,
) -> Deps:
    s = settings or get_settings()
    sm = sessionmaker or get_sessionmaker()
    r = redis or Redis.from_url(s.redis_url, decode_responses=True)
    return Deps(
        settings=s,
        sessionmaker=sm,
        redis=r,
        provider=PostgresOAuthProvider(sm, s.public_origin, s.secret_key.get_secret_value().encode()),
        codes=EmailCodes(r),
        sessions=Sessions(r, s.session_ttl_days),
        mailer=Mailer(s),
    )


def set_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def deps() -> Deps:
    global _deps
    if _deps is None:
        _deps = build_deps()
    return _deps
