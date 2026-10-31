"""Serve the built in-chat views as ui:// resources (text/html;profile=mcp-app).

The views build writes frontend/packages/views/dist/<view>.html; we read them at startup.
Until a view is built (M5), a minimal accessible placeholder is served so tools still link.
"""

from html import escape
from pathlib import Path

from mcp.server.apps import Apps, ResourceCsp

VIEWS = ("shortlist", "job-detail", "cv-studio", "tracker", "profile-review")

TITLES = {
    "shortlist": "Today's shortlist",
    "job-detail": "Job detail",
    "cv-studio": "CV studio",
    "tracker": "Application tracker",
    "profile-review": "Profile review",
}


def uri(view: str) -> str:
    return f"ui://rjf/{view}.html"


def placeholder(view: str) -> str:
    title = escape(TITLES[view])
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'><title>{title}</title>"
        "<style>body{font:14px/1.45 system-ui,sans-serif;margin:16px;color:CanvasText;"
        "background:Canvas}</style></head><body>"
        f"<p><strong>{title}</strong></p><p>This view is not built yet. "
        "The full details are in the chat reply.</p></body></html>"
    )


def load_view_html(dist_dir: Path, view: str) -> str:
    path = dist_dir / f"{view}.html"
    return path.read_text(encoding="utf-8") if path.is_file() else placeholder(view)


def register_views(apps: Apps, dist_dir: Path, api_origin: str) -> None:
    for view in VIEWS:
        # Strict CSP: no external origins, except our own origin for PDF previews.
        csp = (
            ResourceCsp(resource_domains=[api_origin], frame_domains=[api_origin])
            if view == "cv-studio"
            else ResourceCsp()
        )
        apps.add_html_resource(
            uri(view),
            load_view_html(dist_dir, view),
            name=view,
            title=TITLES[view],
            csp=csp,
            prefers_border=False,
        )
