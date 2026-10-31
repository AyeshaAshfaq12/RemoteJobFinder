"""ui_set_application_status (view-only): move a tracker card to another column."""

from mcp.types import CallToolResult
from sqlalchemy import select

from app.db.models import Application
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools._shared import parse_id
from app.mcp.tools._tracker import card, upsert_application
from app.mcp.tools.schemas import ApplicationStatus

NAME = "ui_set_application_status"
SCOPE = "tracker"
VIEW = "ui://rjf/tracker.html"
VISIBILITY = ["app"]
DESCRIPTION = "Move one of the user's applications to a new status from the tracker board."


async def ui_set_application_status(
    application_id: str, status: ApplicationStatus
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        app = await ctx.session.scalar(
            select(Application).where(
                Application.id == parse_id(application_id, "application"),
                Application.user_id == ctx.user_id,
            )
        )
        if app is None:
            raise ToolFail("not_found", f"No application with id '{application_id}'.")
        app = await upsert_application(ctx.session, ctx.user_id, app.job_id, status)
        return result(f"Moved to '{status}'.", await card(ctx.session, ctx.user_id, app))

    return await run_tool(NAME, SCOPE, body)
