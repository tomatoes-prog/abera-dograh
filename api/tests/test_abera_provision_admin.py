from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.abera import provision_admin as provisioning


@pytest.mark.asyncio
async def test_retries_keep_existing_password_and_organization(monkeypatch):
    monkeypatch.setattr(provisioning, "DEPLOYMENT_MODE", "abera")
    user = SimpleNamespace(id=4, selected_organization_id=8, is_superuser=False)
    organization = SimpleNamespace(id=8)
    get_user = AsyncMock(return_value=user)
    create_user = AsyncMock()
    get_org = AsyncMock(return_value=(organization, False))
    add_member = AsyncMock()
    update_selected = AsyncMock()
    monkeypatch.setattr(provisioning.db_client, "get_user_by_email", get_user)
    monkeypatch.setattr(provisioning.db_client, "create_user_with_email", create_user)
    monkeypatch.setattr(
        provisioning.db_client, "get_or_create_organization_by_provider_id", get_org
    )
    monkeypatch.setattr(provisioning.db_client, "add_user_to_organization", add_member)
    monkeypatch.setattr(
        provisioning.db_client, "update_user_selected_organization", update_selected
    )

    result = await provisioning.provision_admin(
        "sub_123", "admin@example.com", "a" * 24
    )

    assert result == 8
    create_user.assert_not_awaited()
    update_selected.assert_not_awaited()
    get_org.assert_awaited_once_with(org_provider_id="abera_sub_123", user_id=4)
    add_member.assert_awaited_once_with(4, 8)


@pytest.mark.asyncio
async def test_admin_cannot_be_attached_to_another_organization(monkeypatch):
    monkeypatch.setattr(provisioning, "DEPLOYMENT_MODE", "abera")
    user = SimpleNamespace(id=4, selected_organization_id=99, is_superuser=False)
    monkeypatch.setattr(
        provisioning.db_client,
        "get_user_by_email",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        provisioning.db_client,
        "get_or_create_organization_by_provider_id",
        AsyncMock(return_value=(SimpleNamespace(id=8), False)),
    )
    with pytest.raises(RuntimeError, match="another organization"):
        await provisioning.provision_admin("sub_123", "admin@example.com", "a" * 24)
