"""track_application: create or update one application in the tracker."""

from mcp.types import CallToolResult
from pydantic import Field

from app.mcp.runtime import ToolCtx, result, run_tool
from app.mcp.tools._shared import parse_id
from app.mcp.tools._tracker import card, upsert_application
from app.mcp.tools.schemas import ApplicationStatus

NAME = "track_application"
SCOPE = "tracker"
VIEW = None
DESCRIPTION = (
    "Create or update the user's application for a job: saved, applying, applied, "
    "interviewing, offer, rejected, withdrawn, or ghosted. Marking it applied schedules a "
    "follow-up in 7 days. Call it when the user says they applied or their status changed."
)


async def track_application(
    job_id: str,
    status: ApplicationStatus,
    notes: str | None = Field(default=None, max_length=2000),
    cv_id: str | None = None,
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        app = await upsert_application(
            ctx.session,
            ctx.user_id,
            parse_id(job_id),
            status,
            notes,
            parse_id(cv_id, "CV") if cv_id else None,
        )
        c = await card(ctx.session, ctx.user_id, app)
        ctx.audit["status"] = status
        follow = f" Follow up on {c['follow_up_at']}." if c["follow_up_at"] else ""
        return result(f"{c['title']} at {c['company']}: now '{status}'.{follow}", c)

    return await run_tool(NAME, SCOPE, body)
