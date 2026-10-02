"""Idempotent, local-only admin creation for one Abera subscription.

Run after migrations inside the tenant runtime. The password is supplied from
the subscription's Secrets Manager secret and is never printed. Re-running
does not reset a customer's changed password.
"""

from __future__ import annotations

import asyncio
import os
import re

from api.constants import DEPLOYMENT_MODE
from api.db import db_client
from api.utils.auth import hash_password

SUBSCRIPTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,100}$")


async def provision_admin(
    subscription_id: str, email: str, initial_password: str
) -> int:
    if DEPLOYMENT_MODE != "abera":
        raise RuntimeError("Admin provisioning requires DEPLOYMENT_MODE=abera")
    if not SUBSCRIPTION_RE.fullmatch(subscription_id):
        raise ValueError("Invalid subscription ID")
    if len(initial_password) < 20:
        raise ValueError("Initial password must have at least 20 characters")

    existing = await db_client.get_user_by_email(email)
    if existing is None:
        user = await db_client.create_user_with_email(
            email=email,
            password_hash=hash_password(initial_password),
        )
    else:
        user = existing

    provider_id = f"abera_{subscription_id}"
    organization, _ = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=provider_id, user_id=user.id
    )
    if user.selected_organization_id not in (None, organization.id):
        raise RuntimeError("Admin email belongs to another organization")
    if user.is_superuser:
        raise RuntimeError("Abera tenant admin cannot be a platform superuser")
    await db_client.add_user_to_organization(user.id, organization.id)
    if user.selected_organization_id != organization.id:
        await db_client.update_user_selected_organization(user.id, organization.id)
    return organization.id


def main() -> None:
    subscription_id = os.environ["ABERA_SUBSCRIPTION_ID"]
    email = os.environ["ABERA_ADMIN_EMAIL"]
    password = os.environ["ABERA_ADMIN_PASSWORD"]
    asyncio.run(provision_admin(subscription_id, email, password))


if __name__ == "__main__":
    main()
