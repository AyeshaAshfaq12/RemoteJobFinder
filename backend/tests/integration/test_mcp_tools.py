"""Every tool end to end over real OAuth + /mcp, idempotent submit, and user scoping."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.models import AuditLog, Job, JobSighting
from app.deps import Deps
from tests.integration.mcp_helpers import ORIGIN, Tokens, call, oauth_login, rpc

pytestmark = pytest.mark.integration

JD = (
    "Acme builds payments infrastructure for emerging markets. As a Backend Engineer on the "
    "Payments team you will design and run Python services on Postgres, own APIs end to end, "
    "and work with the product manager and designers. Requirements: 4+ years of backend "
    "experience, strong SQL, and experience running services in production."
)

PROFILE: dict[str, Any] = {
    "name": "Test User",
    "headline": "Backend Engineer",
    "email": "a@example.com",
    "skills": ["Python", "PostgreSQL", "FastAPI"],
    "roles": [
        {
            "id": "r1",
            "company": "Initech",
            "title": "Backend Engineer",
            "start": "2021-01",
            "end": None,
            "bullets": [
                {
                    "id": "b_aaaaaaa1",
                    "text": "Built FastAPI services on Postgres serving 2M requests a day",
                    "skills": ["FastAPI", "PostgreSQL"],
                    "metrics": ["2M requests a day"],
                }
            ],
        }
    ],
    "education": [{"id": "e1", "school": "NUST", "degree": "BS CS", "start": "2016-09"}],
}
PREFS = {"target_titles": ["Backend Engineer"], "country_code": "PK", "us_overlap_hours": 2}


def job(**kw: Any) -> dict[str, Any]:
    base = {
        "title": "Senior Backend Engineer",
        "company_name": "Acme",
        "company_domain": "acme.io",
        "location_text": "Remote - Worldwide",
        "remote_type": "remote",
        "salary_text": "$5k-7k/month",
        "apply_url": "https://jobs.lever.co/acme/1",
        "source_url": "https://jobs.lever.co/acme/1",
        "source_kind": "ats",
        "jd_text": JD,
    }
    base.update(kw)
    return base


async def onboard(client: AsyncClient, d: Deps, email: str) -> Tokens:
    t = await oauth_login(client, d, email)
    up = await call(client, t.access, "update_profile",
                    {"profile": {**PROFILE, "email": email}, "preferences": PREFS})
    assert not up.get("isError"), up
    version = up["structuredContent"]["version"]
    assert "review" in up["content"][0]["text"]
    ok = await call(client, t.access, "ui_resolve_profile_change",
                    {"version": version, "decision": "accept"})
    assert not ok.get("isError"), ok
    return t


async def test_full_journey(client: AsyncClient, deps_: Deps) -> None:
    t = await onboard(client, deps_, "a@example.com")

    prof = (await call(client, t.access, "get_profile"))["structuredContent"]
    assert prof["profile_version"] == 1
    assert len(prof["crawl_plan"]["queries"]) == 10  # 5 ATS + 4 boards + 1 worldwide, 1 title
    assert prof["crawl_plan"]["fetch_budget"] == 30

    # Idempotent submit: same job twice -> 1 job, 2 sightings.
    s1 = await call(client, t.access, "submit_jobs", {"jobs": [job()]})
    s2 = await call(client, t.access, "submit_jobs", {"jobs": [job()]})
    r1, r2 = s1["structuredContent"]["results"][0], s2["structuredContent"]["results"][0]
    assert r1["is_new"] and not r2["is_new"]
    assert r1["job_id"] == r2["job_id"]
    assert (r1["sightings"], r2["sightings"]) == (1, 2)
    assert r1["eligible_for_user"] and r1["needs_scoring"]
    assert s1["structuredContent"]["needs_company_check"][0]["name"] == "Acme"
    async with deps_.sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Job)) == 1
        assert await s.scalar(select(func.count()).select_from(JobSighting)) == 2
    job_id = r1["job_id"]
    company_id = s1["structuredContent"]["needs_company_check"][0]["company_id"]

    health = await call(client, t.access, "update_company_health", {
        "company_id": company_id, "flag": "shrinking", "note": "Laid off 20% in Sept",
        "source_url": "https://news.example.com/acme-layoffs"})
    assert health["structuredContent"]["recomputed_jobs"] == 1

    found = (await call(client, t.access, "search_jobs"))["structuredContent"]["jobs"]
    assert [j["job_id"] for j in found] == [job_id]
    assert found[0]["jd_text"] == JD  # full JD, decided 2026-10-29

    bad = await call(client, t.access, "save_job_scores", {"scores": [{
        "job_id": job_id, "fit_band": "match", "fit_summary": "x",
        "must_haves_met": [{"requirement": "Python", "evidence_bullet_id": "b_NOTREAL0"}],
        "gaps": [], "jd_quality_flags": []}]})
    assert bad["isError"]
    assert bad["structuredContent"]["error"]["code"] == "validation_failed"

    saved = await call(client, t.access, "save_job_scores", {"scores": [{
        "job_id": job_id, "fit_band": "match", "fit_summary": "Strong FastAPI + Postgres match.",
        "must_haves_met": [{"requirement": "Python", "evidence_bullet_id": "b_aaaaaaa1"}],
        "gaps": [{"requirement": "Kubernetes", "severity": "low"}],
        "jd_quality_flags": ["no_team"]}]})
    short = saved["structuredContent"]
    assert short["counts"]["match"] == 1
    # base: shrinking 15 - salary 10 = 5; + no_team 3 = 8 -> low
    assert short["jobs"][0]["ghost_score"] == 8
    assert short["jobs"][0]["ghost_band"] == "low"
    assert (await call(client, t.access, "search_jobs"))["structuredContent"]["jobs"] == []

    detail = (await call(client, t.access, "get_job", {"job_id": job_id}))["structuredContent"]
    assert len(detail["sightings"]) == 2
    assert detail["score"]["fit_band"] == "match"
    shrink = next(r for r in detail["ghost_reasons"] if r["code"] == "company_shrinking")
    assert shrink["source_url"] == "https://news.example.com/acme-layoffs"
    assert all("submitted_by" not in s for s in detail["sightings"])

    tr = await call(client, t.access, "track_application", {"job_id": job_id, "status": "applied"})
    card = tr["structuredContent"]
    assert card["follow_up_at"] is not None and card["ghost_band_at_apply"] == "low"
    board = (await call(client, t.access, "list_applications"))["structuredContent"]
    assert board["counts"]["applied"] == 1
    moved = await call(client, t.access, "ui_set_application_status",
                       {"application_id": card["id"], "status": "interviewing"})
    assert moved["structuredContent"]["status"] == "interviewing"

    dis = await call(client, t.access, "ui_dismiss_job", {"job_id": job_id})
    assert dis["structuredContent"]["dismissed"] is True

    cv = await call(client, t.access, "generate_cv", {"job_id": job_id, "content": {}, "kit": {}})
    assert cv["isError"] and cv["structuredContent"]["error"]["code"] == "unavailable"

    async with deps_.sessionmaker() as s:
        actions = set(await s.scalars(select(AuditLog.action)))
    assert {"get_profile", "submit_jobs", "save_job_scores", "track_application"} <= actions


async def test_tools_need_profile(client: AsyncClient, deps_: Deps) -> None:
    t = await oauth_login(client, deps_, "new@example.com")
    r = await call(client, t.access, "search_jobs")
    assert r["isError"] and r["structuredContent"]["error"]["code"] == "no_profile"
    first = await call(client, t.access, "update_profile", {"profile": PROFILE})
    assert first["isError"]
    assert "preferences are required" in first["structuredContent"]["error"]["message"]


async def test_partial_profile_acceptance(client: AsyncClient, deps_: Deps) -> None:
    t = await onboard(client, deps_, "p@example.com")
    edited = {
        **PROFILE, "email": "p@example.com", "headline": "Senior Backend Engineer",
        "skills": [*PROFILE["skills"], "Go"],
    }
    up = (await call(client, t.access, "update_profile", {"profile": edited}))["structuredContent"]
    ids = {c["id"] for c in up["changes"]}
    assert ids == {"basics.headline", "skills+Go"}
    await call(client, t.access, "ui_resolve_profile_change",
               {"version": up["version"], "decision": "accept", "rejected_change_ids": ["skills+Go"]})
    prof = (await call(client, t.access, "get_profile"))["structuredContent"]
    assert prof["profile_version"] == up["version"]
    assert prof["profile"]["headline"] == "Senior Backend Engineer"
    assert "Go" not in prof["profile"]["skills"]


async def test_scope_is_enforced(client: AsyncClient, deps_: Deps) -> None:
    t = await oauth_login(client, deps_, "s@example.com", scopes="jobs profile cv tracker")
    ok = await call(client, t.access, "list_applications")
    assert not ok.get("isError")
    # A token missing a required scope is refused at the /mcp door.
    limited = await oauth_login(client, deps_, "s2@example.com", scopes="jobs")
    r = await rpc(client, limited.access, "tools/list")
    assert r.status_code == 403


async def test_refresh_rotation_and_reuse(client: AsyncClient, deps_: Deps) -> None:
    t = await oauth_login(client, deps_, "r@example.com")
    body = {"grant_type": "refresh_token", "refresh_token": t.refresh, "client_id": t.client_id}
    first = await client.post("/token", data=body)
    assert first.status_code == 200, first.text
    new = first.json()
    assert new["refresh_token"] != t.refresh
    assert (await rpc(client, new["access_token"], "tools/list")).status_code == 200
    # Old access token was rotated out.
    assert (await rpc(client, t.access, "tools/list")).status_code == 401
    # Reusing the old refresh token revokes the whole family.
    reuse = await client.post("/token", data=body)
    assert reuse.status_code == 400
    assert (await rpc(client, new["access_token"], "tools/list")).status_code == 401


async def test_cross_user_isolation(client: AsyncClient, deps_: Deps) -> None:
    a = await onboard(client, deps_, "a@example.com")
    sub = await call(client, a.access, "submit_jobs", {"jobs": [job()]})
    job_id = sub["structuredContent"]["results"][0]["job_id"]
    await call(client, a.access, "save_job_scores", {"scores": [{
        "job_id": job_id, "fit_band": "match", "fit_summary": "ok",
        "must_haves_met": [], "gaps": [], "jd_quality_flags": []}]})
    app_a = (await call(client, a.access, "track_application",
                        {"job_id": job_id, "status": "applied", "notes": "secret note"}))
    app_id = app_a["structuredContent"]["id"]
    pending = await call(client, a.access, "update_profile",
                         {"profile": {**PROFILE, "headline": "A's private headline"}})
    a_version = pending["structuredContent"]["version"]

    b = await oauth_login(client, deps_, "b@example.com")
    prof_b = (await call(client, b.access, "get_profile"))["structuredContent"]
    assert prof_b["profile"] is None
    detail_b = (await call(client, b.access, "get_job", {"job_id": job_id}))["structuredContent"]
    assert detail_b["score"] is None and detail_b["application"] is None  # shared job, private rest
    board_b = (await call(client, b.access, "list_applications"))["structuredContent"]
    assert board_b["cards"] == []
    move = await call(client, b.access, "ui_set_application_status",
                      {"application_id": app_id, "status": "withdrawn"})
    assert move["structuredContent"]["error"]["code"] == "not_found"
    dis = await call(client, b.access, "ui_dismiss_job", {"job_id": job_id})
    assert dis["structuredContent"]["error"]["code"] == "not_found"
    steal = await call(client, b.access, "ui_resolve_profile_change",
                       {"version": a_version, "decision": "accept"})
    assert steal["isError"]
    # A's data is untouched.
    board_a = (await call(client, a.access, "list_applications"))["structuredContent"]
    assert board_a["cards"][0]["status"] == "applied"
    assert board_a["cards"][0]["notes"] == "secret note"


async def test_web_profile_review_fallback(client: AsyncClient, deps_: Deps) -> None:
    from tests.integration.mcp_helpers import sign_in

    t = await oauth_login(client, deps_, "w@example.com")
    up = await call(client, t.access, "update_profile",
                    {"profile": {**PROFILE, "email": "w@example.com"}, "preferences": PREFS})
    version = up["structuredContent"]["version"]
    assert f"{ORIGIN}/profile/review?version={version}" in up["content"][0]["text"]

    assert (await client.get(f"/api/profile/proposal/{version}")).status_code == 401
    await sign_in(client, deps_, "w@example.com")
    got = await client.get(f"/api/profile/proposal/{version}")
    assert got.status_code == 200 and got.json()["status"] == "proposed"
    cross = await client.post(f"/api/profile/proposal/{version}/resolve",
                              json={"decision": "accept"}, headers={"origin": "https://evil.example"})
    assert cross.status_code == 403
    res = await client.post(f"/api/profile/proposal/{version}/resolve",
                            json={"decision": "accept"}, headers={"origin": ORIGIN})
    assert res.status_code == 200 and res.json()["status"] == "active"
