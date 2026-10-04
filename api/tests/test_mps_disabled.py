"""The default installation must work without the upstream service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from api import constants
from api.routes.user import get_default_configurations
from api.services import organization_bootstrap, quota_service, workflow_run_billing
from api.services.mps_service_key_client import MPSServiceKeyClient
from api.services.model_services.policy import MPSDisabledError


@pytest.fixture(autouse=True)
def mps_off(monkeypatch):
    monkeypatch.setattr(constants, "ENABLE_DOGRAH_MPS", False)
    for module in (organization_bootstrap, quota_service, workflow_run_billing):
        monkeypatch.setattr(module, "ENABLE_DOGRAH_MPS", False)


@pytest.mark.asyncio
async def test_default_model_catalog_only_offers_available_providers():
    catalog = await get_default_configurations()
    for field in ("llm", "tts", "stt", "embeddings"):
        assert "dograh" not in getattr(catalog, field)
        assert getattr(catalog, field)
    assert "openai_realtime" in catalog.realtime


@pytest.mark.asyncio
async def test_bootstrap_does_not_mint_keys_or_provision_sip(monkeypatch):
    monkeypatch.setattr(organization_bootstrap, "DEPLOYMENT_MODE", "oss")
    read = AsyncMock(side_effect=AssertionError("must not bootstrap"))
    monkeypatch.setattr(organization_bootstrap.db_client, "get_configuration", read)
    assert await organization_bootstrap.ensure_organization_bootstrapped(42, created_by="test") is True
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_client_cannot_send_http_when_disabled(monkeypatch):
    sent = []
    def respond(request):
        sent.append(request)
        return httpx.Response(200, json={})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    client = MPSServiceKeyClient()
    with pytest.raises(MPSDisabledError):
        await client.create_service_key(name="test", organization_id=42, created_by="test")
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["oss", "saas", "abera"])
@pytest.mark.parametrize("provider,allowed", [("openai", True), ("dograh", False)])
async def test_byok_calls_work_and_legacy_managed_calls_fail_closed(monkeypatch, mode, provider, allowed):
    monkeypatch.setattr(quota_service, "DEPLOYMENT_MODE", mode)
    workflow = SimpleNamespace(id=7, user_id=1, organization_id=42, workflow_configurations={})
    monkeypatch.setattr(quota_service.db_client, "get_workflow", AsyncMock(return_value=workflow))
    monkeypatch.setattr(quota_service.db_client, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=1)))
    config = SimpleNamespace(managed_service_version=1, llm=SimpleNamespace(provider=provider, api_key="test-key"),
                             tts=None, stt=None, embeddings=None)
    monkeypatch.setattr(quota_service, "get_effective_ai_model_configuration_for_workflow", AsyncMock(return_value=config))
    monkeypatch.setattr(quota_service.mps_service_key_client, "authorize_workflow_run_start",
                        AsyncMock(side_effect=AssertionError("must not call MPS")))
    monkeypatch.setattr(quota_service.mps_service_key_client, "check_service_key_usage",
                        AsyncMock(side_effect=AssertionError("must not call MPS")))
    from api.services.abera import bedrock
    monkeypatch.setattr(bedrock, "managed_nova_enabled", lambda: False)
    result = await quota_service.authorize_workflow_run_start(workflow_id=7, organization_id=42)
    assert result.has_quota is allowed
    if not allowed:
        assert result.error_code == "unsupported_provider"


@pytest.mark.asyncio
async def test_managed_abera_does_not_bypass_its_billing(monkeypatch):
    monkeypatch.setattr(quota_service, "DEPLOYMENT_MODE", "abera")
    monkeypatch.setattr(quota_service.db_client, "get_workflow", AsyncMock(return_value=SimpleNamespace(
        id=7, user_id=1, organization_id=42, workflow_configurations={},
    )))
    monkeypatch.setattr(quota_service.db_client, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(quota_service, "get_effective_ai_model_configuration_for_workflow", AsyncMock(return_value=SimpleNamespace(
        managed_service_version=1, llm=None, tts=None, stt=None, embeddings=None,
    )))
    from api.services.abera import bedrock
    monkeypatch.setattr(bedrock, "uses_managed_voice", lambda config: True)
    from api.services.abera import voice_minutes
    monkeypatch.setattr(voice_minutes, "managed_balance_available", AsyncMock(return_value=False))
    result = await quota_service.authorize_workflow_run_start(workflow_id=7, organization_id=42)
    assert result.has_quota is False and result.error_code == "metering_unavailable"


@pytest.mark.asyncio
async def test_usage_not_reported_to_vendor(monkeypatch):
    monkeypatch.setattr(workflow_run_billing, "DEPLOYMENT_MODE", "saas")
    remote = AsyncMock(side_effect=AssertionError("must not report"))
    monkeypatch.setattr(workflow_run_billing.mps_service_key_client, "report_platform_usage", remote)
    await workflow_run_billing.report_workflow_run_platform_usage(SimpleNamespace(id=7))
    remote.assert_not_awaited()
