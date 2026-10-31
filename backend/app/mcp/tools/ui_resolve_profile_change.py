"""ui_resolve_profile_change (view-only): approve or reject a proposed profile version."""

from typing import Literal

from mcp.types import CallToolResult
from pydantic import ValidationError

from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.profiles.service import ProfileError, resolve

NAME = "ui_resolve_profile_change"
SCOPE = "profile"
VIEW = "ui://rjf/profile-review.html"
VISIBILITY = ["app"]
DESCRIPTION = "Approve (fully or partly) or reject a proposed profile version from the review view."


async def ui_resolve_profile_change(
    version: int,
    decision: Literal["accept", "reject"],
    rejected_change_ids: list[str] | None = None,
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        try:
            active = await resolve(
                ctx.session, ctx.user_id, version, decision == "accept", rejected_change_ids
            )
        except (ProfileError, ValidationError) as exc:
            raise ToolFail("validation_failed", str(exc)) from exc
        ctx.audit["rejected_changes"] = len(rejected_change_ids or [])
        if active is None:
            return result(f"Profile v{version} rejected.", {"version": version, "status": "rejected"})
        return result(
            f"Profile v{version} is now active.", {"version": version, "status": "active"}
        )

    return await run_tool(NAME, SCOPE, body)
