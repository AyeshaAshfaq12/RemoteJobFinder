"""Profile review on the web app: the fallback when the host can't show the in-chat view."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ValidationError

from app.api.deps import CsrfDep, DbDep, UserDep
from app.db.models import AuditLog
from app.profiles.diff import diff_profiles
from app.profiles.service import ProfileError, get_active, get_version, resolve

router = APIRouter(tags=["profile"])


@router.get("/profile/proposal/{version}")
async def get_proposal(version: int, user_id: UserDep, session: DbDep) -> dict[str, Any]:
    proposed = await get_version(session, user_id, version)
    if proposed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such version")
    active = await get_active(session, user_id)
    changes = diff_profiles(
        active.profile if active else None,
        proposed.profile,
        active.preferences if active else None,
        proposed.preferences,
    )
    return {
        "version": proposed.version,
        "status": proposed.status,
        "base_version": active.version if active else None,
        "changes": changes,
        "proposed": {"profile": proposed.profile, "preferences": proposed.preferences},
        "current": {"profile": active.profile, "preferences": active.preferences} if active else None,
    }


class ResolveIn(BaseModel):
    decision: Literal["accept", "reject"]
    rejected_change_ids: list[str] = []


@router.post("/profile/proposal/{version}/resolve", dependencies=[CsrfDep])
async def resolve_proposal(
    version: int, body: ResolveIn, user_id: UserDep, session: DbDep
) -> dict[str, Any]:
    try:
        active = await resolve(
            session, user_id, version, body.decision == "accept", body.rejected_change_ids
        )
    except (ProfileError, ValidationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.add(
        AuditLog(user_id=user_id, action="profile_resolve_web",
                 meta={"decision": body.decision, "rejected": len(body.rejected_change_ids)})
    )
    return {"version": version, "status": "active" if active else "rejected"}
