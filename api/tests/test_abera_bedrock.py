from types import SimpleNamespace

import pytest

from api.services.abera import bedrock


def test_basic_cannot_borrow_instance_role(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    monkeypatch.setenv("ABERA_PLAN", "basic")
    monkeypatch.setenv("ABERA_MANAGED_NOVA_ENABLED", "true")
    with pytest.raises(ValueError, match="unavailable"):
        bedrock.validate_managed_nova(bedrock.NOVA_MODEL, bedrock.NOVA_REGION)


def test_pro_cannot_select_a_different_chargeable_model(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    monkeypatch.setenv("ABERA_PLAN", "pro")
    monkeypatch.setenv("ABERA_MANAGED_NOVA_ENABLED", "true")
    with pytest.raises(ValueError, match="fixed"):
        bedrock.validate_managed_nova("amazon.other-model", bedrock.NOVA_REGION)


def test_pro_reads_temporary_role_credentials(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    monkeypatch.setenv("ABERA_PLAN", "pro")
    monkeypatch.setenv("ABERA_MANAGED_NOVA_ENABLED", "true")
    frozen = SimpleNamespace(
        access_key="short-lived-id",
        secret_key="short-lived-secret",
        token="short-lived-token",
    )
    session = SimpleNamespace(
        get_credentials=lambda: SimpleNamespace(get_frozen_credentials=lambda: frozen)
    )
    monkeypatch.setattr("boto3.Session", lambda: session)
    assert bedrock.temporary_nova_credentials(
        bedrock.NOVA_MODEL, bedrock.NOVA_REGION
    ) == ("short-lived-id", "short-lived-secret", "short-lived-token")
