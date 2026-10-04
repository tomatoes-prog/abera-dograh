from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import constants
from api.services.auth import security


@pytest.mark.parametrize("secret", ["", "short", "change-me-in-production" + "x" * 40])
def test_runtime_rejects_weak_secret(monkeypatch, secret):
    monkeypatch.setattr(constants, "AUTH_PROVIDER", "local")
    monkeypatch.setattr(constants, "OSS_JWT_SECRET", secret)
    with pytest.raises(ValueError, match="OSS_JWT_SECRET"):
        security.validate_runtime_security()


def test_runtime_rejects_disabled_media_auth(monkeypatch):
    monkeypatch.setattr(constants, "AUTH_PROVIDER", "local")
    monkeypatch.setattr(constants, "OSS_JWT_SECRET", "x" * 64)
    monkeypatch.setattr(constants, "TELEPHONY_WS_TOKEN_SECRET", "y" * 64)
    monkeypatch.setattr(constants, "TELEPHONY_WS_TOKEN_ENFORCE", False)
    with pytest.raises(ValueError, match="ENFORCE"):
        security.validate_runtime_security()


async def test_login_throttle_and_redis_failure(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[10, 11, RuntimeError("down")]))
    monkeypatch.setattr(security, "_redis", redis)
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.1"))
    await security.throttle_login(request, "User@example.com")
    with pytest.raises(HTTPException) as error:
        await security.throttle_login(request, "user@example.com")
    assert error.value.status_code == 429
    with pytest.raises(HTTPException) as error:
        await security.throttle_login(request, "user@example.com")
    assert error.value.status_code == 503
    assert "user@example.com" not in repr(redis.eval.call_args)


async def test_explicit_local_url_never_queries_tunnel(monkeypatch):
    from api.utils import common

    monkeypatch.setattr(common, "BACKEND_API_ENDPOINT", "http://localhost:8000")
    monkeypatch.setattr(common, "ENABLE_CLOUDFLARE_TUNNEL", False)
    tunnel = AsyncMock()
    monkeypatch.setattr(common.TunnelURLProvider, "get_tunnel_urls", tunnel)
    assert await common.get_backend_endpoints() == (
        "http://localhost:8000",
        "ws://localhost:8000",
    )
    tunnel.assert_not_awaited()
