"""The call claim must arbitrate concurrent deliveries using shared Redis."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import redis.asyncio as redis

from api.constants import REDIS_URL
from api.services.telephony.providers.whatsapp import routes


@pytest.mark.asyncio
async def test_only_one_concurrent_delivery_can_claim_a_call(monkeypatch):
    client = redis.from_url(REDIS_URL, decode_responses=True)
    call_id = f"test-{uuid4()}"
    monkeypatch.setattr(routes, "_get_redis", AsyncMock(return_value=client))
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(routes._claim_call(call_id) for _ in range(16))), timeout=5
        )
        assert results.count(True) == 1
        assert results.count(False) == 15
        assert (
            0
            < await client.ttl(routes._claim_key(call_id))
            <= routes.CALL_CLAIM_TTL_SECONDS
        )
        await routes._release_claim(call_id)
        assert await routes._claim_call(call_id) is True
    finally:
        await client.delete(routes._claim_key(call_id))
        await client.aclose()
