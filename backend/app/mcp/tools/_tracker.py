"""Application tracker logic shared by track_application, list_applications, and the view tool."""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Company, Cv, Job, JobScore
from app.mcp.runtime import ToolFail
from app.mcp.tools._shared import now_utc
from app.mcp.tools.schemas import ApplicationStatus

FOLLOW_UP_DAYS = 7
CLOSED = ("rejected", "withdrawn", "ghosted")
COLUMNS = ("saved", "applying", "applied", "interviewing", "offer", "closed")


async def upsert_application(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    status: ApplicationStatus,
    notes: str | None = None,
    cv_id: uuid.UUID | None = None,
) -> Application:
    if await session.get(Job, job_id) is None:
        raise ToolFail("not_found", f"No job with id '{job_id}'.")
    if cv_id is not None:
        cv_owner = await session.scalar(select(Cv.user_id).where(Cv.id == cv_id))
        if cv_owner != user_id:
            raise ToolFail("not_found", f"No CV with id '{cv_id}'.")
    now = now_utc()
    values: dict[str, Any] = {"user_id": user_id, "job_id": job_id, "status": status,
                              "updated_at": now}
    if notes is not None:
        values["notes"] = notes
    if cv_id is not None:
        values["cv_id"] = cv_id
    stmt = insert(Application).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Application.user_id, Application.job_id],
        set_={k: v for k, v in values.items() if k not in ("user_id", "job_id")},
    ).returning(Application.id)
    app_id = await session.scalar(stmt)
    app = await session.get(Application, app_id, populate_existing=True)
    assert app is not None
    if status == "applied" and app.applied_at is None:
        app.applied_at = now
        app.follow_up_at = now.date() + timedelta(days=FOLLOW_UP_DAYS)
    await session.flush()
    return app


async def _ghost_band_at_apply(
    session: AsyncSession, user_id: uuid.UUID, app: Application
) -> str | None:
    q = select(JobScore.ghost_band).where(
        JobScore.user_id == user_id, JobScore.job_id == app.job_id
    )
    if app.applied_at is not None:
        before = await session.scalar(
            q.where(JobScore.scored_at <= app.applied_at)
            .order_by(JobScore.scored_at.desc())
            .limit(1)
        )
        if before:
            return before
    return await session.scalar(q.order_by(JobScore.scored_at.desc()).limit(1))


async def card(session: AsyncSession, user_id: uuid.UUID, app: Application) -> dict[str, Any]:
    job = await session.get(Job, app.job_id)
    company = await session.get(Company, job.company_id) if job else None
    today = date.today()
    return {
        "id": str(app.id),
        "job_id": str(app.job_id),
        "title": job.title if job else None,
        "company": company.name if company else None,
        "company_domain": company.domain if company else None,
        "apply_url": job.apply_url if job else None,
        "status": app.status,
        "column": "closed" if app.status in CLOSED else app.status,
        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        "days_since_applied": (today - app.applied_at.date()).days if app.applied_at else None,
        "follow_up_at": app.follow_up_at.isoformat() if app.follow_up_at else None,
        "follow_up_due": bool(
            app.status == "applied" and app.follow_up_at and app.follow_up_at <= today
        ),
        "ghost_band_at_apply": await _ghost_band_at_apply(session, user_id, app),
        "cv_id": str(app.cv_id) if app.cv_id else None,
        "notes": app.notes,
        "updated_at": app.updated_at.isoformat(),
    }


async def board(
    session: AsyncSession, user_id: uuid.UUID, statuses: list[str] | None
) -> dict[str, Any]:
    q = select(Application).where(Application.user_id == user_id)
    if statuses:
        q = q.where(Application.status.in_(statuses))
    apps = list(await session.scalars(q.order_by(Application.updated_at.desc())))
    cards = [await card(session, user_id, a) for a in apps]
    return {
        "columns": list(COLUMNS),
        "cards": cards,
        "follow_ups_due": sum(1 for c in cards if c["follow_up_due"]),
        "counts": {col: sum(1 for c in cards if c["column"] == col) for col in COLUMNS},
    }
