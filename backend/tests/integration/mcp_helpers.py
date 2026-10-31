"""Drive the real OAuth flow and JSON-RPC calls against the ASGI app."""

import base64
import hashlib
import itertools
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from httpx import AsyncClient

from app.deps import Deps

ORIGIN = "http://localhost:3000"
REDIRECT = "http://localhost:6274/callback"
_ids = itertools.count(1)


@dataclass
class Tokens:
    access: str
    refresh: str
    client_id: str


async def sign_in(client: AsyncClient, d: Deps, email: str) -> None:
    sent: dict[str, str] = {}

    async def capture(to: str, code: str) -> None:
        sent[to] = code

    d.mailer.send_code = capture  # type: ignore[method-assign]
    headers = {"origin": ORIGIN}
    r = await client.post("/api/auth/email/start", json={"email": email}, headers=headers)
    assert r.status_code == 204, r.text
    r = await client.post(
        "/api/auth/email/verify", json={"email": email, "code": sent[email]}, headers=headers
    )
    assert r.status_code == 200, r.text


async def oauth_login(
    client: AsyncClient, d: Deps, email: str, scopes: str = "jobs profile cv tracker"
) -> Tokens:
    client.cookies.clear()
    reg = await client.post(
        "/register",
        json={
            "redirect_uris": [REDIRECT],
            "client_name": "Claude",
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]

    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    auth = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": scopes,
            "resource": f"{ORIGIN}/mcp",
        },
    )
    assert auth.status_code == 302, auth.text
    consent = urlsplit(auth.headers["location"])
    assert consent.path == "/consent"
    req = parse_qs(consent.query)["req"][0]

    await sign_in(client, d, email)
    info = await client.get("/api/oauth/request", params={"req": req})
    assert info.status_code == 200, info.text
    dec = await client.post(
        "/api/oauth/decision",
        json={"req": req, "decision": "approve"},
        headers={"origin": ORIGIN},
    )
    assert dec.status_code == 200, dec.text
    back = urlsplit(dec.json()["redirect_to"])
    q = parse_qs(back.query)
    assert q["state"] == ["xyz"]

    tok = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": q["code"][0],
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": f"{ORIGIN}/mcp",
        },
    )
    assert tok.status_code == 200, tok.text
    body = tok.json()
    client.cookies.clear()
    return Tokens(body["access_token"], body["refresh_token"], client_id)


async def rpc(
    client: AsyncClient, token: str | None, method: str, params: dict[str, Any] | None = None
) -> Any:
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "mcp-protocol-version": "2025-11-25",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}},
        headers=headers,
    )


async def call(client: AsyncClient, token: str, tool: str, args: dict[str, Any] | None = None) -> Any:
    r = await rpc(client, token, "tools/call", {"name": tool, "arguments": args or {}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "result" in body, body
    return body["result"]
