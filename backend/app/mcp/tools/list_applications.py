"""list_applications: the tracker board with follow-ups due."""

from mcp.types import CallToolResult

from app.mcp.runtime import ToolCtx, result, run_tool
from app.mcp.tools._tracker import board
from app.mcp.tools.schemas import ApplicationStatus

NAME = "list_applications"
SCOPE = "tracker"
VIEW = "ui://rjf/tracker.html"
DESCRIPTION = (
    "Show the user's application tracker, grouped by status, with follow-ups that are due. "
    "Call it for /tracker, 'where do I stand', or to remind the user about follow-ups."
)


async def list_applications(status: list[ApplicationStatus] | None = None) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        b = await board(ctx.session, ctx.user_id, list(status) if status else None)
        ctx.audit["cards"] = len(b["cards"])
        counts = ", ".join(f"{k} {v}" for k, v in b["counts"].items() if v)
        due = [c for c in b["cards"] if c["follow_up_due"]]
        text = f"{len(b['cards'])} application(s): {counts or 'none yet'}."
        if due:
            text += f" {len(due)} follow-up(s) due: " + "; ".join(
                f"{c['title']} at {c['company']}" for c in due
            )
        return result(text, b)

    return await run_tool(NAME, SCOPE, body)
