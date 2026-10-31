"""Versioned Master Profiles. Nothing becomes active until the user approves it.

profiles.data holds the MasterProfile JSON encrypted with AES-256-GCM (AAD = user id), so a
row copied to another user cannot be decrypted. Every query is scoped by user_id.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cv.schema import MasterProfile
from app.db.models import Profile
from app.mcp.tools.schemas import Preferences
from app.profiles.diff import Change, apply_partial, diff_profiles
from app.security.crypto import keyring


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class StoredProfile:
    version: int
    status: str
    profile: dict[str, Any]
    preferences: dict[str, Any]


def _encrypt(user_id: uuid.UUID, profile: dict[str, Any]) -> bytes:
    return keyring().encrypt(json.dumps(profile).encode("utf-8"), aad=user_id.bytes)


def _decrypt(user_id: uuid.UUID, blob: bytes) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(keyring().decrypt(blob, aad=user_id.bytes))
    return data


def _stored(user_id: uuid.UUID, row: Profile) -> StoredProfile:
    return StoredProfile(row.version, row.status, _decrypt(user_id, row.data), row.preferences)


def validate_ids(profile: MasterProfile) -> None:
    """Bullet and item ids must be unique so diffs and CV provenance are unambiguous."""
    seen: set[str] = set()
    for item in [*profile.roles, *profile.projects, *profile.education]:
        if item.id in seen:
            raise ProfileError(f"duplicate id '{item.id}'")
        seen.add(item.id)
    bullets: set[str] = set()
    for item in [*profile.roles, *profile.projects]:
        for b in item.bullets:
            if b.id in bullets:
                raise ProfileError(f"duplicate bullet id '{b.id}'")
            bullets.add(b.id)


async def get_active(session: AsyncSession, user_id: uuid.UUID) -> StoredProfile | None:
    row = await session.scalar(
        select(Profile).where(Profile.user_id == user_id, Profile.status == "active")
    )
    return _stored(user_id, row) if row else None


async def get_version(
    session: AsyncSession, user_id: uuid.UUID, version: int
) -> StoredProfile | None:
    row = await session.scalar(
        select(Profile).where(Profile.user_id == user_id, Profile.version == version)
    )
    return _stored(user_id, row) if row else None


@dataclass(frozen=True)
class Proposal:
    version: int
    base_version: int | None
    changes: list[Change]
    proposed: StoredProfile
    active: StoredProfile | None


async def propose(
    session: AsyncSession,
    user_id: uuid.UUID,
    profile: MasterProfile,
    preferences: Preferences | None,
) -> Proposal:
    validate_ids(profile)
    active = await get_active(session, user_id)
    if preferences is None and active is None:
        raise ProfileError(
            "preferences are required for the first profile (target_titles and country_code)"
        )
    prefs = preferences.model_dump(mode="json") if preferences else active.preferences  # type: ignore[union-attr]
    data = profile.model_dump(mode="json")

    # A newer proposal supersedes any older pending one.
    await session.execute(
        update(Profile)
        .where(Profile.user_id == user_id, Profile.status == "proposed")
        .values(status="rejected")
    )
    latest = await session.scalar(
        select(func.max(Profile.version)).where(Profile.user_id == user_id)
    )
    version = (latest or 0) + 1
    session.add(
        Profile(user_id=user_id, version=version, data=_encrypt(user_id, data),
                preferences=prefs, status="proposed")
    )
    await session.flush()
    changes = diff_profiles(
        active.profile if active else None, data, active.preferences if active else None, prefs
    )
    proposed = StoredProfile(version, "proposed", data, prefs)
    return Proposal(version, active.version if active else None, changes, proposed, active)


async def resolve(
    session: AsyncSession,
    user_id: uuid.UUID,
    version: int,
    accept: bool,
    rejected_change_ids: list[str] | None = None,
) -> StoredProfile | None:
    """Accept (fully or partially) or reject a proposed version. Returns the new active one."""
    row = await session.scalar(
        select(Profile)
        .where(Profile.user_id == user_id, Profile.version == version)
        .with_for_update()
    )
    if row is None or row.status != "proposed":
        raise ProfileError(f"version {version} is not a pending proposal")
    if not accept:
        row.status = "rejected"
        return None

    proposed = _decrypt(user_id, row.data)
    prefs = dict(row.preferences)
    if rejected_change_ids:
        active = await get_active(session, user_id)
        changes = diff_profiles(
            active.profile if active else None,
            proposed,
            active.preferences if active else None,
            prefs,
        )
        proposed, prefs = apply_partial(proposed, prefs, changes, set(rejected_change_ids))
        MasterProfile.model_validate(proposed)  # partial acceptance must still be a valid profile
        Preferences.model_validate(prefs)
        row.data = _encrypt(user_id, proposed)
        row.preferences = prefs

    await session.execute(
        update(Profile)
        .where(Profile.user_id == user_id, Profile.status == "active")
        .values(status="superseded")
    )
    await session.flush()
    row.status = "active"
    await session.flush()
    return StoredProfile(row.version, "active", proposed, prefs)
