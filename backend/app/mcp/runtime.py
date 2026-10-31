"""Shared tool plumbing: auth context, scopes, rate limits, audit log, errors, results.

Every tool body receives a ToolCtx whose session is scoped to one transaction and whose
user_id comes from the verified bearer token, never from tool input.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.deps import deps

log = structlog.get_logger()

ErrorCode = Literal[
    "quota_exceeded", "validation_failed", "not_found", "rate_limited", "forbidden",
    "no_profile", "too_long", "unavailable",
]

# Per-user limits (Build Spec section 11): (capacity, refill window seconds).
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "submit_jobs": (20, 60),
    "generate_cv": (10, 3600),
}
DEFAULT_LIMIT = (60, 60)


class ToolFail(Exception):  # noqa: N818 - reads better at call sites
    def __init__(self, code: ErrorCode, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass
class ToolCtx:
    user_id: uuid.UUID
    scopes: list[str]
    session: AsyncSession
    audit: dict[str, Any]


def result(text: str, structured: BaseModel | dict[str, Any]) -> CallToolResult:
    data = structured.model_dump(mode="json") if isinstance(structured, BaseModel) else structured
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


def error_result(fail: ToolFail) -> CallToolResult:
    payload: dict[str, Any] = {"error": {"code": fail.code, "message": fail.message}}
    if fail.details is not None:
        payload["error"]["details"] = fail.details
    return CallToolResult(
        content=[TextContent(type="text", text=f"{fail.code}: {fail.message}")],
        structured_content=payload,
        is_error=True,
    )


async def check_rate_limit(user_id: uuid.UUID, tool: str) -> bool:
    """Token bucket in Redis. Returns False when the call should be rejected."""
    capacity, window = RATE_LIMITS.get(tool, DEFAULT_LIMIT)
    bucket = tool if tool in RATE_LIMITS else "default"
    key = f"ratelimit:{user_id}:{bucket}"
    r = deps().redis
    now = time.time()
    rate = capacity / window
    data = await r.hgetall(key)  # type: ignore[misc]
    tokens = float(data.get("tokens", capacity))
    last = float(data.get("ts", now))
    tokens = min(capacity, tokens + (now - last) * rate)
    allowed = tokens >= 1
    if allowed:
        tokens -= 1
    await r.hset(key, mapping={"tokens": tokens, "ts": now})  # type: ignore[misc]
    await r.expire(key, window * 2)
    return allowed


async def run_tool(
    name: str, scope: str, body: Callable[[ToolCtx], Awaitable[CallToolResult]]
) -> CallToolResult:
    """Run a tool body with auth, scope, rate limit, one transaction, and an audit row."""
    token = get_access_token()
    user_id: uuid.UUID | None = getattr(token, "user_id", None)
    if token is None or user_id is None:
        return error_result(ToolFail("forbidden", "Sign-in is required. Reconnect the connector."))
    if scope not in token.scopes:
        return error_result(
            ToolFail(
                "forbidden",
                f"This connection lacks the '{scope}' permission. "
                "Reconnect the connector and approve it.",
            )
        )
    if not await check_rate_limit(user_id, name):
        return error_result(
            ToolFail("rate_limited", "Too many requests right now. Wait a minute and retry.")
        )
    audit: dict[str, Any] = {}
    started = time.perf_counter()
    outcome = "ok"
    try:
        async with deps().sessionmaker.begin() as session:
            res = await body(ToolCtx(user_id, list(token.scopes), session, audit))
    except ToolFail as fail:
        outcome = fail.code
        res = error_result(fail)
    ms = round((time.perf_counter() - started) * 1000)
    log.info("tool_call", tool=name, outcome=outcome, ms=ms)
    async with deps().sessionmaker.begin() as session:
        session.add(AuditLog(user_id=user_id, action=name, meta={"outcome": outcome, "ms": ms, **audit}))
    return res
