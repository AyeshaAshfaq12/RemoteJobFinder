"""ui_get_cv_pdf_url (view-only): signed, short-lived URL for the PDF preview (M4)."""

from mcp.types import CallToolResult

from app.mcp.runtime import ToolCtx, ToolFail, run_tool

NAME = "ui_get_cv_pdf_url"
SCOPE = "cv"
VIEW = "ui://rjf/cv-studio.html"
VISIBILITY = ["app"]
DESCRIPTION = "Get a 10-minute signed URL to preview or download one of the user's CV files."


async def ui_get_cv_pdf_url(cv_id: str) -> CallToolResult:
    async def body(ctx: ToolCtx) -> CallToolResult:
        raise ToolFail("unavailable", "CV previews are not available yet.")

    return await run_tool(NAME, SCOPE, body)
