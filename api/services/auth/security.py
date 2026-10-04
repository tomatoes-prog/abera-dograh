"""Validate local authentication and throttle password attempts across workers."""

import hashlib

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from api import constants

_redis = None
_LOGIN_WINDOW = 600
_LOGIN_LIMIT = 10
_ATTEMPT_SCRIPT = """
local highest = 0
for _, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then redis.call('EXPIRE', key, ARGV[1]) end
    highest = math.max(highest, count)
end
return highest
"""


def validate_runtime_security() -> None:
    if constants.AUTH_PROVIDER != "local":
        return
    secret = constants.OSS_JWT_SECRET
    if len(secret) < 32 or secret.lower().startswith("change-me"):
        raise ValueError("OSS_JWT_SECRET must be a random secret of at least 32 characters")
    if not constants.TELEPHONY_WS_TOKEN_SECRET:
        raise ValueError("Telephony media token secret is required")
    if not constants.TELEPHONY_WS_TOKEN_ENFORCE:
        raise ValueError("TELEPHONY_WS_TOKEN_ENFORCE must be true for local authentication")


async def throttle_login(request: Request, email: str) -> None:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(constants.REDIS_URL)
    ip = request.client.host if request.client else "unknown"
    keys = [
        "login:ip:" + hashlib.sha256(ip.encode()).hexdigest(),
        "login:email:" + hashlib.sha256(email.strip().casefold().encode()).hexdigest(),
    ]
    try:
        count = await _redis.eval(_ATTEMPT_SCRIPT, len(keys), *keys, _LOGIN_WINDOW)
    except Exception:
        raise HTTPException(503, "Login protection is temporarily unavailable") from None
    if count > _LOGIN_LIMIT:
        raise HTTPException(429, "Too many login attempts; try again later", headers={"Retry-After": str(_LOGIN_WINDOW)})


async def close_login_protection() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
