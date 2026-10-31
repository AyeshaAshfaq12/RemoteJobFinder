"""FastAPI app: REST for the web app under /api, MCP + OAuth (SDK auth server) mounted at root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.deps import Deps, deps
from app.mcp.server import build_mcp_app


def create_app(d: Deps | None = None) -> FastAPI:
    d = d or deps()
    _, mcp_app = build_mcp_app(d)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(
        title="Remote Job Finder", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.deps = d

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api")
    app.include_router(profile_router, prefix="/api")
    # /mcp, /authorize, /token, /register, /revoke, /.well-known/* (MCP SDK + our provider)
    app.mount("/", mcp_app)
    return app


app = create_app()
