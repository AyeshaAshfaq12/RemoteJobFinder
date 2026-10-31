"""Web sign-in: 6-digit email codes and server-side sessions (Build Spec section 11).

Codes: 10-minute expiry, 5 attempts, stored hashed in Redis. Sessions: random id in an
HTTP-only, Secure, SameSite=Lax cookie; the Redis record maps it to the user, and a per-user
set lists active sessions so Settings can revoke them.
"""

import asyncio
import json
import secrets
import smtplib
import time
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

import structlog
from redis.asyncio import Redis

from app.auth.tokens import constant_time_equal, hash_token
from app.settings import Settings

log = structlog.get_logger()

CODE_TTL = 600
CODE_MAX_ATTEMPTS = 5
START_LIMIT_PER_HOUR = 5


@dataclass(frozen=True)
class CodeCheck:
    ok: bool
    reason: str | None = None  # 'expired' | 'wrong_code' | 'too_many_attempts'


class EmailCodes:
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @staticmethod
    def _key(email: str) -> str:
        return f"signin:code:{hash_token(email.lower())}"

    async def issue(self, email: str) -> str | None:
        """Create a new code. Returns None when the address asked too often this hour."""
        rate_key = f"signin:rate:{hash_token(email.lower())}"
        count = await self._r.incr(rate_key)
        if count == 1:
            await self._r.expire(rate_key, 3600)
        if count > START_LIMIT_PER_HOUR:
            return None
        code = f"{secrets.randbelow(1_000_000):06d}"
        await self._r.set(
            self._key(email),
            json.dumps({"hash": hash_token(code), "attempts": 0}),
            ex=CODE_TTL,
        )
        return code

    async def check(self, email: str, code: str) -> CodeCheck:
        key = self._key(email)
        raw = await self._r.get(key)
        if raw is None:
            return CodeCheck(False, "expired")
        data = json.loads(raw)
        if data["attempts"] >= CODE_MAX_ATTEMPTS:
            await self._r.delete(key)
            return CodeCheck(False, "too_many_attempts")
        if constant_time_equal(data["hash"], hash_token(code.strip())):
            await self._r.delete(key)
            return CodeCheck(True)
        data["attempts"] += 1
        ttl = await self._r.ttl(key)
        await self._r.set(key, json.dumps(data), ex=max(ttl, 1))
        if data["attempts"] >= CODE_MAX_ATTEMPTS:
            return CodeCheck(False, "too_many_attempts")
        return CodeCheck(False, "wrong_code")


@dataclass(frozen=True)
class WebSession:
    id: str
    user_id: uuid.UUID
    created_at: int
    user_agent: str | None


class Sessions:
    def __init__(self, redis: Redis, ttl_days: int) -> None:
        self._r = redis
        self._ttl = ttl_days * 86400

    async def create(self, user_id: uuid.UUID, user_agent: str | None) -> str:
        sid = secrets.token_urlsafe(32)
        record = {"user_id": str(user_id), "created_at": int(time.time()), "ua": user_agent}
        await self._r.set(f"session:{hash_token(sid)}", json.dumps(record), ex=self._ttl)
        await self._r.sadd(f"user_sessions:{user_id}", hash_token(sid))
        await self._r.expire(f"user_sessions:{user_id}", self._ttl)
        return sid

    async def get(self, sid: str | None) -> WebSession | None:
        if not sid:
            return None
        raw = await self._r.get(f"session:{hash_token(sid)}")
        if raw is None:
            return None
        rec = json.loads(raw)
        return WebSession(hash_token(sid), uuid.UUID(rec["user_id"]), rec["created_at"], rec["ua"])

    async def revoke(self, sid: str) -> None:
        sess = await self.get(sid)
        await self._r.delete(f"session:{hash_token(sid)}")
        if sess:
            await self._r.srem(f"user_sessions:{sess.user_id}", hash_token(sid))

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        key = f"user_sessions:{user_id}"
        for hashed in await self._r.smembers(key):
            await self._r.delete(f"session:{hashed if isinstance(hashed, str) else hashed.decode()}")
        await self._r.delete(key)


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def send_code(self, to: str, code: str) -> None:
        if not self._s.smtp_host:
            if self._s.env in ("staging", "production"):
                raise RuntimeError("RJF_SMTP_HOST is required outside local/test")
            # Local development only: print the code instead of sending mail.
            log.info("signin_code_local", to_domain=to.split("@")[-1], code=code)
            return
        msg = EmailMessage()
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg["Subject"] = f"{code} is your Remote Job Finder sign-in code"
        msg.set_content(
            f"Your sign-in code is {code}.\n\nIt expires in 10 minutes. "
            "If you didn't ask for it, you can ignore this email."
        )
        await asyncio.to_thread(self._send, msg)

    def _send(self, msg: EmailMessage) -> None:
        assert self._s.smtp_host is not None
        with smtplib.SMTP(self._s.smtp_host, self._s.smtp_port, timeout=10) as smtp:
            if self._s.smtp_starttls:
                smtp.starttls()
            if self._s.smtp_username and self._s.smtp_password:
                smtp.login(self._s.smtp_username, self._s.smtp_password.get_secret_value())
            smtp.send_message(msg)
