"""Resolve temporary instance-role credentials for Abera's Nova Sonic service."""

from __future__ import annotations

import os

NOVA_MODEL = "amazon.nova-2-sonic-v1:0"
NOVA_REGION = "us-east-1"


def managed_nova_enabled() -> bool:
    return (
        os.getenv("DEPLOYMENT_MODE") == "abera"
        and os.getenv("ABERA_PLAN") == "pro"
        and os.getenv("ABERA_MANAGED_NOVA_ENABLED") == "true"
    )


def uses_managed_voice(config) -> bool:
    realtime = getattr(config, "realtime", None)
    return bool(
        managed_nova_enabled()
        and getattr(config, "is_realtime", False)
        and realtime is not None
        and realtime.provider == "aws_nova_sonic"
        and not realtime.aws_access_key
        and not realtime.aws_secret_key
    )


def validate_managed_nova(model: str, region: str) -> None:
    if not managed_nova_enabled():
        raise ValueError("Managed Nova Sonic is unavailable for this subscription")
    if model != NOVA_MODEL or region != NOVA_REGION:
        raise ValueError("Managed Nova Sonic model and region are fixed by Abera")


def temporary_nova_credentials(model: str, region: str) -> tuple[str, str, str | None]:
    """Fetch a current frozen credential snapshot from the EC2 role.

    The returned values are passed directly to Pipecat and are never persisted
    in the tenant's model configuration or exposed through the API.
    """
    validate_managed_nova(model, region)
    import boto3

    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS instance-role credentials available")
    frozen = credentials.get_frozen_credentials()
    return frozen.access_key, frozen.secret_key, frozen.token
