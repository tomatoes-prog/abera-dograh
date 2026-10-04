"""The deployed tenant must fit the connection budget reserved by Automations."""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from api.db import base_client


@pytest.mark.asyncio
async def test_managed_clients_share_a_bounded_pool(monkeypatch):
    monkeypatch.setattr(base_client, "DEPLOYMENT_MODE", "abera")
    base_client._managed_engine.cache_clear()
    first = base_client.BaseDBClient()
    second = base_client.BaseDBClient()
    try:
        assert first.engine is second.engine
        assert first.engine.pool.size() == 2
        assert first.engine.pool._max_overflow == 0
        assert first.engine.pool.timeout() == 15
    finally:
        await first.engine.dispose()
        base_client._managed_engine.cache_clear()


@pytest.mark.asyncio
async def test_rds_url_uses_asyncpg_supported_tls_argument():
    engine = create_async_engine("postgresql+asyncpg://tenant:example@db.internal/app?ssl=verify-full")
    try:
        _, kwargs = engine.dialect.create_connect_args(engine.url)
        assert kwargs["ssl"] == "verify-full"
        assert "sslmode" not in kwargs and "sslrootcert" not in kwargs
    finally:
        await engine.dispose()
