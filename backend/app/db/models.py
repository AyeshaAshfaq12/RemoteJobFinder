"""ORM models mirroring migration 001 (Build Spec section 4). The migration is the truth."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(2))
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    cv_quota_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = _now()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # AES-256-GCM MasterProfile
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, unique=True)
    ats_type: Mapped[str | None] = mapped_column(Text)
    ats_slug: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)
    health_note: Mapped[str | None] = mapped_column(Text)
    health_flag: Mapped[str | None] = mapped_column(Text, server_default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_norm: Mapped[str] = mapped_column(Text, nullable=False)
    seniority: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_countries: Mapped[list[str] | None] = mapped_column(ARRAY(String(2)))
    tz_min_overlap_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    remote_type: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[date | None] = mapped_column(Date)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    on_company_ats: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    first_seen_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobSighting(Base):
    __tablename__ = "job_sightings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[datetime] = _now()
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class JobPostingHistory(Base):
    __tablename__ = "job_postings_history"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True
    )
    title_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    posted_at: Mapped[date | None] = mapped_column(Date)


class GhostSignals(Base):
    __tablename__ = "ghost_signals"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    on_company_ats: Mapped[bool] = mapped_column(Boolean, nullable=False)
    repost_count_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    age_days: Mapped[int | None] = mapped_column(Integer)
    salary_listed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    company_health: Mapped[str] = mapped_column(Text, nullable=False)
    base_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = _now()


class JobScore(Base):
    __tablename__ = "job_scores"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    profile_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    fit_band: Mapped[str] = mapped_column(Text, nullable=False)
    fit_summary: Mapped[str] = mapped_column(Text, nullable=False)
    must_haves_met: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    jd_quality_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ghost_score: Mapped[int] = mapped_column(Integer, nullable=False)
    ghost_band: Mapped[str] = mapped_column(Text, nullable=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    scored_at: Mapped[datetime] = _now()


class Cv(Base):
    __tablename__ = "cvs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tex_key: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    kit: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    cv_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cvs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _now()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = _now()
