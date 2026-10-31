import pytest
from httpx import AsyncClient

from app.deps import Deps
from tests.integration.mcp_helpers import ORIGIN, call, oauth_login, rpc

pytestmark = pytest.mark.integration

MODEL_TOOLS = {
    "get_profile", "update_profile", "submit_jobs", "search_jobs", "save_job_scores", "get_job",
    "generate_cv", "track_application", "list_applications", "update_company_health",
}
VIEW_TOOLS = {
    "ui_set_application_status", "ui_dismiss_job", "ui_resolve_profile_change",
    "ui_get_cv_pdf_url",
}


async def test_metadata_endpoints(client: AsyncClient) -> None:
    prm = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert prm.status_code == 200, prm.text
    assert prm.json()["resource"] == f"{ORIGIN}/mcp"
    asm = await client.get("/.well-known/oauth-authorization-server")
    assert asm.status_code == 200
    meta = asm.json()
    assert meta["issuer"].rstrip("/") == ORIGIN
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert set(meta["scopes_supported"]) == {"jobs", "profile", "cv", "tracker"}
    assert meta["registration_endpoint"].endswith("/register")


async def test_mcp_requires_bearer(client: AsyncClient) -> None:
    r = await rpc(client, None, "tools/list")
    assert r.status_code == 401
    assert "resource_metadata" in r.headers["www-authenticate"]


async def test_login_and_list_tools(client: AsyncClient, deps_: Deps) -> None:
    t = await oauth_login(client, deps_, "a@example.com")
    r = await rpc(client, t.access, "tools/list")
    assert r.status_code == 200, r.text
    tools = {tool["name"]: tool for tool in r.json()["result"]["tools"]}
    assert MODEL_TOOLS <= set(tools)
    for name in MODEL_TOOLS | (VIEW_TOOLS & set(tools)):
        schema = tools[name]["inputSchema"]
        assert schema["type"] == "object", name
        assert 1 <= tools[name]["description"].count(".") <= 4, name
    assert tools["save_job_scores"]["_meta"]["ui"]["resourceUri"] == "ui://rjf/shortlist.html"

    res = await call(client, t.access, "get_profile")
    assert res["structuredContent"]["profile_version"] is None
