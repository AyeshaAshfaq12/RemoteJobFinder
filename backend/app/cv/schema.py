"""Master Profile and CvContent (Build Spec section 8)."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

_ID = r"^[A-Za-z0-9_-]{1,40}$"  # role/project/education ids: format not fixed by the spec
_YM = r"^\d{4}-(0[1-9]|1[0-2])$"  # 'YYYY-MM'


class Bullet(BaseModel):
    id: str = Field(pattern=r"^b_[A-Za-z0-9]{8}$")  # stable across versions
    text: str = Field(min_length=1, max_length=400)
    skills: list[str] = []  # skills this bullet is evidence for
    metrics: list[str] = []  # exact numbers/claims, e.g. '40%', '2M rows'


class Role(BaseModel):
    id: str = Field(pattern=_ID)
    company: str
    title: str
    location: str | None = None
    start: str = Field(pattern=_YM)
    end: str | None = Field(default=None, pattern=_YM)  # None = present
    bullets: list[Bullet]


class Project(BaseModel):
    id: str = Field(pattern=_ID)
    name: str
    url: HttpUrl | None = None
    bullets: list[Bullet]


class Education(BaseModel):
    id: str = Field(pattern=_ID)
    school: str
    degree: str
    start: str = Field(pattern=_YM)
    end: str | None = Field(default=None, pattern=_YM)
    notes: list[str] = []


class MasterProfile(BaseModel):
    name: str
    headline: str
    email: str
    phone: str | None = None
    links: list[HttpUrl] = []
    summary_facts: list[str] = []  # raw facts a summary may draw on
    skills: list[str]  # canonical skill names
    roles: list[Role]
    projects: list[Project] = []
    education: list[Education]
    certifications: list[str] = []

    def all_bullets(self) -> dict[str, Bullet]:
        out: dict[str, Bullet] = {}
        for item in [*self.roles, *self.projects]:
            for b in item.bullets:
                out[b.id] = b
        return out


class CvBullet(BaseModel):
    source_bullet_id: str  # must exist in the profile
    text: str = Field(max_length=260)


class CvSection(BaseModel):
    ref_id: str  # role/project/education id
    bullets: list[CvBullet] = Field(max_length=6)


class CvContent(BaseModel):
    headline: str = Field(max_length=120)
    summary: str = Field(max_length=500)
    skills: list[str] = Field(max_length=24)
    sections_order: list[Literal["experience", "projects", "education", "skills", "certifications"]]
    experience: list[CvSection]
    projects: list[CvSection] = []
    education_ids: list[str]
