"""MCP server: tool + view registration, OAuth wiring, Streamable HTTP app (stateless, JSON)."""

from types import ModuleType
from urllib.parse import urlsplit

from mcp.server.apps import Apps
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app.auth.provider import SCOPES
from app.deps import Deps
from app.mcp.tools import (
    generate_cv,
    get_job,
    get_profile,
    list_applications,
    save_job_scores,
    search_jobs,
    submit_jobs,
    track_application,
    ui_dismiss_job,
    ui_get_cv_pdf_url,
    ui_resolve_profile_change,
    ui_set_application_status,
    update_company_health,
    update_profile,
)
from app.mcp.ui_resources import register_views
from app.settings import BASE_DIR

MODEL_TOOLS: tuple[ModuleType, ...] = (
    get_profile,
    update_profile,
    submit_jobs,
    search_jobs,
    save_job_scores,
    get_job,
    generate_cv,
    track_application,
    list_applications,
    update_company_health,
)
VIEW_TOOLS: tuple[ModuleType, ...] = (
    ui_set_application_status,
    ui_dismiss_job,
    ui_resolve_profile_change,
    ui_get_cv_pdf_url,
)

INSTRUCTIONS = (
    "Remote Job Finder: you crawl the web for remote jobs and do all reasoning; this server "
    "dedupes jobs, scores ghost risk from facts, compiles CVs, and tracks applications. Never "
    "invent CV content, salaries, or dates. Follow the plugin skills (daily-scan, fit-rubric, "
    "ghost-rubric, cv-writer) when available."
)

VIEWS_DIST = BASE_DIR.parent / "frontend" / "packages" / "views" / "dist"


def build_mcp(d: Deps) -> MCPServer:
    origin = d.settings.public_origin.rstrip("/")
    apps = Apps()
    register_views(apps, VIEWS_DIST, origin)
    # The SDK reads an extension's tools when MCPServer is constructed: register them first.
    for mod in MODEL_TOOLS:
        if mod.VIEW:
            apps.tool(resource_uri=mod.VIEW, name=mod.NAME, description=mod.DESCRIPTION)(
                getattr(mod, mod.NAME)
            )
    for mod in VIEW_TOOLS:
        apps.tool(
            resource_uri=mod.VIEW,
            visibility=mod.VISIBILITY,
            name=mod.NAME,
            description=mod.DESCRIPTION,
        )(getattr(mod, mod.NAME))

    mcp = MCPServer(
        name="remote-job-finder",
        title="Remote Job Finder",
        version="0.1.0",
        instructions=INSTRUCTIONS,
        website_url=origin,
        auth_server_provider=d.provider,
        auth=AuthSettings(
            issuer_url=origin,  # type: ignore[arg-type]
            resource_server_url=f"{origin}/mcp",  # type: ignore[arg-type]
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=list(SCOPES), default_scopes=list(SCOPES)
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=list(SCOPES),
            validate_token_resource=False,  # checked in the provider (resource may be absent)
        ),
        extensions=[apps],
    )
    for mod in MODEL_TOOLS:
        if not mod.VIEW:
            mcp.add_tool(getattr(mod, mod.NAME), name=mod.NAME, description=mod.DESCRIPTION)
    return mcp


def build_mcp_app(d: Deps) -> tuple[MCPServer, Starlette]:
    mcp = build_mcp(d)
    origin = d.settings.public_origin.rstrip("/")
    host = urlsplit(origin).netloc
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, "localhost:*", "127.0.0.1:*", "api:*", *d.settings.extra_allowed_hosts],
        allowed_origins=[origin, "https://claude.ai", "https://claude.com"],
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=security,
        max_request_body_size=d.settings.max_body_bytes,
    )
    return mcp, app
