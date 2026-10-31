"""FastAPI dependencies for the web REST API: services, session user, CSRF checks."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Deps


def get_deps(request: Request) -> Deps:
    d: Deps = request.app.state.deps
    return d


DepsDep = Annotated[Deps, Depends(get_deps)]


async def db(d: DepsDep) -> AsyncIterator[AsyncSession]:
    async with d.sessionmaker.begin() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(db)]


async def current_user_id(request: Request, d: DepsDep) -> uuid.UUID:
    sess = await d.sessions.get(request.cookies.get(d.settings.session_cookie))
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    return sess.user_id


UserDep = Annotated[uuid.UUID, Depends(current_user_id)]


def same_origin(request: Request, d: DepsDep) -> None:
    """CSRF guard for state-changing requests: JSON body and our own Origin only."""
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") != d.settings.public_origin.rstrip("/"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cross-origin request refused")
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JSON required")


CsrfDep = Depends(same_origin)
