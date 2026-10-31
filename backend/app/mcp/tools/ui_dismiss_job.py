"""ui_dismiss_job (view-only): hide a job from the shortlist, or undo that."""

from mcp.types import CallToolResult
from sqlalchemy import update

from app.db.models import JobScore
from app.mcp.runtime import ToolCtx, ToolFail, result, run_tool
from app.mcp.tools._shared import parse_id

NAME = "ui_dismiss_job"
SCOPE = "jobs"
VIEW = "ui://rjf/shortlist.html"
VISIBILITY = ["app"]
DESCRIPTION = "Hide a job from the user's shortlist (dismissed=true) or restore it (false)."


async def ui_dismiss_job(job_id: str, dismissed: bool = True) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        jid = parse_id(job_id)
        res = await ctx.session.execute(
            update(JobScore)
            .where(JobScore.user_id == ctx.user_id, JobScore.job_id == jid)
            .values(dismissed=dismissed)
            .returning(JobScore.job_id)
        )
        if res.first() is None:
            raise ToolFail("not_found", "That job is not among your scored jobs.")
        return result(
            "Job hidden." if dismissed else "Job restored.",
            {"job_id": job_id, "dismissed": dismissed},
        )

    return await run_tool(NAME, SCOPE, body)
