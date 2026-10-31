"""Web sign-in (email code) and the OAuth consent decision, called by the Next.js app."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import CsrfDep, DbDep, DepsDep, UserDep
from app.auth.pending import InvalidPending, verify_pending
from app.auth.provider import scope_descriptions
from app.db.models import AuditLog, User

router = APIRouter(tags=["auth"])

# Plain pattern check; deliverability is proven by the emailed code.
Email = Annotated[str, Field(pattern=r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$", max_length=254)]


class StartIn(BaseModel):
    email: Email


class VerifyIn(BaseModel):
    email: Email
    code: str = Field(pattern=r"^\s*\d{6}\s*$")


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    country_code: str | None
    plan: str


def _user_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, name=u.name, country_code=u.country_code, plan=u.plan)


@router.post("/auth/email/start", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CsrfDep])
async def email_start(body: StartIn, d: DepsDep) -> Response:
    code = await d.codes.issue(body.email)
    if code is None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many codes requested")
    await d.mailer.send_code(body.email, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/email/verify", dependencies=[CsrfDep])
async def email_verify(
    body: VerifyIn, request: Request, response: Response, d: DepsDep, session: DbDep
) -> UserOut:
    check = await d.codes.check(body.email, body.code)
    if not check.ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, check.reason)
    await session.execute(
        insert(User).values(email=body.email.lower()).on_conflict_do_nothing(index_elements=[User.email])
    )
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    assert user is not None
    if user.deleted_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account scheduled for deletion")
    sid = await d.sessions.create(user.id, request.headers.get("user-agent"))
    response.set_cookie(
        d.settings.session_cookie,
        sid,
        max_age=d.settings.session_ttl_days * 86400,
        httponly=True,
        secure=d.settings.env not in ("local", "test"),
        samesite="lax",
        path="/",
    )
    session.add(AuditLog(user_id=user.id, action="web_sign_in", meta={"method": "email_code"}))
    return _user_out(user)


@router.get("/auth/me")
async def me(user_id: UserDep, session: DbDep) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    return _user_out(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CsrfDep])
async def logout(request: Request, d: DepsDep) -> Response:
    sid = request.cookies.get(d.settings.session_cookie)
    if sid:
        await d.sessions.revoke(sid)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(d.settings.session_cookie, path="/")
    return resp


class ConsentInfo(BaseModel):
    client_name: str | None
    redirect_host: str
    scopes: list[dict[str, str]]


@router.get("/oauth/request")
async def oauth_request(req: str, d: DepsDep) -> ConsentInfo:
    try:
        pending = verify_pending(req, d.settings.secret_key.get_secret_value().encode())
    except InvalidPending as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ConsentInfo(
        client_name=pending.client_name,
        redirect_host=urlsplit(pending.redirect_uri).netloc,
        scopes=scope_descriptions(pending.scopes),
    )


class DecisionIn(BaseModel):
    req: str
    decision: Literal["approve", "deny"]


class DecisionOut(BaseModel):
    redirect_to: str


@router.post("/oauth/decision", dependencies=[CsrfDep])
async def oauth_decision(body: DecisionIn, user_id: UserDep, d: DepsDep, session: DbDep) -> DecisionOut:
    try:
        pending = verify_pending(body.req, d.settings.secret_key.get_secret_value().encode())
    except InvalidPending as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if body.decision == "deny":
        return DecisionOut(redirect_to=d.provider.deny_redirect(pending))
    session.add(
        AuditLog(user_id=user_id, action="oauth_consent",
                 meta={"client": pending.client_id, "scopes": len(pending.scopes)})
    )
    return DecisionOut(redirect_to=await d.provider.approve(pending, user_id))
