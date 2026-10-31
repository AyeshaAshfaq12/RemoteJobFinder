"""update_profile: propose a new profile version; the user approves it in the review view."""

from mcp.types import CallToolResult
from pydantic import Field

from app.cv.schema import MasterProfile
from app.deps import deps
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools.schemas import Preferences
from app.profiles.service import ProfileError, propose

NAME = "update_profile"
SCOPE = "profile"
VIEW = "ui://rjf/profile-review.html"
DESCRIPTION = (
    "Propose a new version of the user's Master Profile (the complete profile, built only from "
    "facts the user gave you) and optionally their preferences. Nothing is saved until the user "
    "approves the changes in the review view or on the web app."
)


async def update_profile(
    profile: MasterProfile,
    preferences: Preferences | None = None,
    change_note: str | None = Field(default=None, max_length=300),
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        try:
            p = await propose(ctx.session, ctx.user_id, profile, preferences)
        except ProfileError as exc:
            raise ToolFail("validation_failed", str(exc)) from exc
        ctx.audit["changes"] = len(p.changes)
        review_url = f"{deps().settings.public_origin}/profile/review?version={p.version}"
        structured = {
            "version": p.version,
            "base_version": p.base_version,
            "change_note": change_note,
            "changes": p.changes,
            "proposed": {"profile": p.proposed.profile, "preferences": p.proposed.preferences},
            "current": (
                {"profile": p.active.profile, "preferences": p.active.preferences}
                if p.active
                else None
            ),
            "review_url": review_url,
        }
        return result(
            f"Proposed profile v{p.version} with {len(p.changes)} change(s). It is NOT active "
            "yet: the user must approve it in the review view. If they can't see the view, give "
            f"them this link to review and approve: {review_url}",
            structured,
        )

    return await run_tool(NAME, SCOPE, body)
