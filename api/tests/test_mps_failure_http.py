import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.errors.mps import MPS_UNAVAILABLE_PUBLIC_MESSAGE, MPSUnavailableError
from fastapi import HTTPException
from api.routes import user as user_routes


@pytest.mark.asyncio
async def test_voice_catalog_preserves_direct_provider_limit_error(monkeypatch):
    route_log_failure = Mock()
    get_voices = AsyncMock(side_effect=HTTPException(429, "Provider limit"))
    monkeypatch.setattr(
        user_routes,
        "get_direct_voices",
        get_voices,
    )
    monkeypatch.setattr(user_routes, "log_failure", route_log_failure)

    with pytest.raises(HTTPException) as error:
        await user_routes.get_voices(
            provider="cartesia",
            user=SimpleNamespace(
                selected_organization_id=42,
                provider_id="provider-123",
            ),
        )

    route_log_failure.assert_not_called()
    assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_mps_unavailable_handler_returns_customer_safe_503():
    from api.app import app, handle_mps_unavailable_error

    assert app.exception_handlers[MPSUnavailableError] is handle_mps_unavailable_error

    response = await handle_mps_unavailable_error(
        None,
        MPSUnavailableError("validate_service_key", status_code=503),
    )

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": MPS_UNAVAILABLE_PUBLIC_MESSAGE}
