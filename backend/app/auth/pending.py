"""A pending /authorize request, carried to the consent page as an HMAC-signed blob.

Stateless: nothing is stored until the user approves. The blob expires after 10 minutes.
"""

import base64
import hashlib
import hmac
import json
import time

from pydantic import BaseModel


class PendingAuthorization(BaseModel):
    client_id: str
    client_name: str | None
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    scopes: list[str]
    code_challenge: str
    state: str | None
    resource: str | None
    expires_at: float


class InvalidPending(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_pending(pending: PendingAuthorization, secret: bytes) -> str:
    body = _b64(json.dumps(pending.model_dump(), separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_pending(token: str, secret: bytes, now: float | None = None) -> PendingAuthorization:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise InvalidPending("bad signature")
        pending = PendingAuthorization.model_validate_json(_unb64(body))
    except InvalidPending:
        raise
    except Exception as exc:
        raise InvalidPending("malformed request") from exc
    if pending.expires_at < (now if now is not None else time.time()):
        raise InvalidPending("request expired")
    return pending
