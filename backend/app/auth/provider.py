"""Postgres-backed OAuth 2.1 provider for the MCP SDK auth server (decided 2026-10-29).

Authorization code + PKCE (S256, enforced by the SDK) + Dynamic Client Registration.
Access tokens: opaque, 1 hour, stored hashed. Refresh tokens: 30 days, rotated on every use;
presenting a rotated refresh token again revokes the whole token family.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import OAuthAuthorizationCode, OAuthClient, OAuthToken as TokenRow
from app.auth.pending import PendingAuthorization, sign_pending
from app.auth.tokens import hash_token, new_token

ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600
CODE_TTL = 300

SCOPES = ("jobs", "profile", "cv", "tracker")
SCOPE_LABELS = {
    "jobs": "Find jobs for you, check them, and save your scores",
    "profile": "Read and propose changes to your Master Profile",
    "cv": "Build tailored CVs and application kits",
    "tracker": "Track your applications and follow-ups",
}


class UserAccessToken(AccessToken):
    user_id: uuid.UUID


class UserAuthorizationCode(AuthorizationCode):
    user_id: uuid.UUID


class UserRefreshToken(RefreshToken):
    user_id: uuid.UUID
    family_id: uuid.UUID
    row_id: uuid.UUID


class PostgresOAuthProvider:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        public_origin: str,
        secret: bytes,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._sm = sessionmaker
        self._origin = public_origin.rstrip("/")
        self._secret = secret
        self._now = clock

    # --- clients (RFC 7591) ---------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._sm() as s:
            row = await s.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id))
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row.client_metadata)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        assert client_info.client_id is not None
        data = client_info.model_dump(mode="json", exclude_none=True)
        async with self._sm.begin() as s:
            s.add(
                OAuthClient(
                    client_id=client_info.client_id,
                    client_secret_hash=hash_token(client_info.client_secret)
                    if client_info.client_secret
                    else None,
                    client_id_issued_at=client_info.client_id_issued_at or int(self._now()),
                    client_secret_expires_at=client_info.client_secret_expires_at,
                    client_metadata=data,
                )
            )

    # --- authorize: hand off to the web consent page ---------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        assert client.client_id is not None
        pending = PendingAuthorization(
            client_id=client.client_id,
            client_name=client.client_name,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=params.scopes or list(SCOPES),
            code_challenge=params.code_challenge,
            state=params.state,
            resource=params.resource,
            expires_at=self._now() + 600,
        )
        token = sign_pending(pending, self._secret)
        return f"{self._origin}/consent?req={token}"

    async def approve(self, pending: PendingAuthorization, user_id: uuid.UUID) -> str:
        """Called by the consent page after sign-in. Returns the client redirect URL."""
        code = new_token()
        async with self._sm.begin() as s:
            s.add(
                OAuthAuthorizationCode(
                    code_hash=hash_token(code),
                    user_id=user_id,
                    client_id=pending.client_id,
                    redirect_uri=pending.redirect_uri,
                    redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
                    scope=" ".join(pending.scopes),
                    code_challenge=pending.code_challenge,
                    resource=pending.resource,
                    expires_at=self._now() + CODE_TTL,
                )
            )
        return construct_redirect_uri(
            pending.redirect_uri, code=code, state=pending.state, iss=self._origin
        )

    def deny_redirect(self, pending: PendingAuthorization) -> str:
        return construct_redirect_uri(
            pending.redirect_uri,
            error="access_denied",
            error_description="The user declined access",
            state=pending.state,
        )

    # --- authorization code --------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> UserAuthorizationCode | None:
        async with self._sm() as s:
            row = await s.get(OAuthAuthorizationCode, hash_token(authorization_code))
        if row is None or row.client_id != client.client_id or row.expires_at < self._now():
            return None
        return UserAuthorizationCode(
            code=authorization_code,
            scopes=row.scope.split(),
            expires_at=row.expires_at,
            client_id=row.client_id,
            code_challenge=row.code_challenge,
            redirect_uri=row.redirect_uri,  # type: ignore[arg-type]
            redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
            resource=row.resource,
            subject=str(row.user_id),
            user_id=row.user_id,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: UserAuthorizationCode
    ) -> OAuthToken:
        async with self._sm.begin() as s:
            deleted = await s.execute(
                delete(OAuthAuthorizationCode)
                .where(OAuthAuthorizationCode.code_hash == hash_token(authorization_code.code))
                .returning(OAuthAuthorizationCode.code_hash)
            )
            if deleted.first() is None:  # already used
                raise TokenError(error="invalid_grant", error_description="code already used")
            return await self._issue(
                s,
                user_id=authorization_code.user_id,
                client_id=authorization_code.client_id,
                scopes=authorization_code.scopes,
                resource=authorization_code.resource,
                family_id=uuid.uuid4(),
            )

    # --- refresh tokens ------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> UserRefreshToken | None:
        now = int(self._now())
        async with self._sm.begin() as s:
            row = await s.scalar(
                select(TokenRow).where(TokenRow.refresh_token_hash == hash_token(refresh_token))
            )
            if row is None or row.client_id != client.client_id:
                return None
            if row.refresh_token_revoked_at is not None:
                # Reuse of a rotated (or revoked) refresh token: revoke the whole family.
                await self._revoke_family(s, row.family_id, now)
                return None
            if row.refresh_expires_at is not None and row.refresh_expires_at < now:
                return None
            return UserRefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=row.scope.split(),
                expires_at=row.refresh_expires_at,
                resource=row.resource,
                subject=str(row.user_id),
                user_id=row.user_id,
                family_id=row.family_id,
                row_id=row.id,
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: UserRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        now = int(self._now())
        async with self._sm.begin() as s:
            rotated = await s.execute(
                update(TokenRow)
                .where(TokenRow.id == refresh_token.row_id, TokenRow.refresh_token_revoked_at.is_(None))
                .values(refresh_token_revoked_at=now, access_token_revoked_at=now)
                .returning(TokenRow.id)
            )
            if rotated.first() is not None:
                return await self._issue(
                    s,
                    user_id=refresh_token.user_id,
                    client_id=refresh_token.client_id,
                    scopes=scopes or refresh_token.scopes,
                    resource=refresh_token.resource,
                    family_id=refresh_token.family_id,
                )
        # Lost a race with another refresh: treat as reuse. Own transaction so the revoke sticks.
        async with self._sm.begin() as s:
            await self._revoke_family(s, refresh_token.family_id, now)
        raise TokenError(error="invalid_grant", error_description="refresh token reused")

    # --- access tokens -------------------------------------------------------------------

    async def load_access_token(self, token: str) -> UserAccessToken | None:
        now = int(self._now())
        async with self._sm() as s:
            row = await s.scalar(
                select(TokenRow).where(TokenRow.access_token_hash == hash_token(token))
            )
        if row is None or row.access_token_revoked_at is not None or row.access_expires_at < now:
            return None
        # A token bound to a resource (RFC 8707) must be bound to this server's /mcp URL.
        if row.resource is not None and row.resource.rstrip("/") != f"{self._origin}/mcp":
            return None
        return UserAccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scope.split(),
            expires_at=row.access_expires_at,
            resource=row.resource,
            subject=str(row.user_id),
            user_id=row.user_id,
        )

    async def revoke_token(self, token: UserAccessToken | UserRefreshToken) -> None:
        now = int(self._now())
        column = (
            TokenRow.refresh_token_hash
            if isinstance(token, UserRefreshToken)
            else TokenRow.access_token_hash
        )
        async with self._sm.begin() as s:
            await s.execute(
                update(TokenRow)
                .where(column == hash_token(token.token))
                .values(access_token_revoked_at=now, refresh_token_revoked_at=now)
            )

    # --- helpers -------------------------------------------------------------------------

    async def _issue(
        self,
        s: AsyncSession,
        *,
        user_id: uuid.UUID,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        family_id: uuid.UUID,
    ) -> OAuthToken:
        now = int(self._now())
        access, refresh = new_token(), new_token()
        s.add(
            TokenRow(
                user_id=user_id,
                client_id=client_id,
                family_id=family_id,
                access_token_hash=hash_token(access),
                refresh_token_hash=hash_token(refresh),
                scope=" ".join(scopes),
                resource=resource,
                issued_at=now,
                access_expires_at=now + ACCESS_TTL,
                refresh_expires_at=now + REFRESH_TTL,
            )
        )
        return OAuthToken(
            access_token=access,
            expires_in=ACCESS_TTL,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def _revoke_family(self, s: AsyncSession, family_id: uuid.UUID, now: int) -> None:
        await s.execute(
            update(TokenRow)
            .where(TokenRow.family_id == family_id)
            .values(
                access_token_revoked_at=now,
                refresh_token_revoked_at=now,
            )
        )


def scope_descriptions(scopes: list[str]) -> list[dict[str, Any]]:
    return [{"scope": sc, "label": SCOPE_LABELS.get(sc, sc)} for sc in scopes]
