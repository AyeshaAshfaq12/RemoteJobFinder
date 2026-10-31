"""OAuth tables (migration 001). Codes and tokens are stored as SHA-256 hashes only."""

import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    client_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column(String(64))
    client_id_issued_at: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    client_secret_expires_at: Mapped[int | None] = mapped_column(Integer)
    client_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class OAuthAuthorizationCode(Base):
    __tablename__ = "oauth_authorization_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    code_challenge: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    resource: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[int] = mapped_column(Integer, nullable=False)
    access_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    refresh_expires_at: Mapped[int | None] = mapped_column(Integer)
    access_token_revoked_at: Mapped[int | None] = mapped_column(Integer)
    refresh_token_revoked_at: Mapped[int | None] = mapped_column(Integer)
