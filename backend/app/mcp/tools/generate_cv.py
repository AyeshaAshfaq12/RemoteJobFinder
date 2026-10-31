"""generate_cv: validate + render + compile a tailored CV and kit (CV engine lands in M4)."""

from typing import Any, Literal

from mcp.types import CallToolResult

from app.mcp.runtime import ToolCtx, ToolFail, run_tool

NAME = "generate_cv"
SCOPE = "cv"
VIEW = "ui://rjf/cv-studio.html"
DESCRIPTION = (
    "Build a tailored CV PDF and application kit for one job from CvContent that points at "
    "Master Profile bullet ids; the server rejects anything not backed by the profile. Call it "
    "after get_job and get_profile, following the cv-writer rules."
)


async def generate_cv(
    job_id: str,
    content: dict[str, Any],
    kit: dict[str, Any],
    template: Literal["classic", "modern", "compact"] = "classic",
) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        raise ToolFail(
            "unavailable",
            "CV building is not available yet. Tell the user it is coming soon; meanwhile you "
            "can draft the content in chat.",
        )

    return await run_tool(NAME, SCOPE, body)
