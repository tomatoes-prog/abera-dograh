"""A wrong realtime model must never start a paid capacity test."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.load_tests import realtime_capacity as harness


async def test_wrong_model_starts_no_calls(monkeypatch):
    monkeypatch.setenv("DOGRAH_TEST_ACCESS_TOKEN", "test-only-token")
    monkeypatch.setattr(
        harness,
        "api_json",
        Mock(
            return_value={
                "realtime": {"provider": "openai_realtime", "model": "another-model"}
            }
        ),
    )
    start_call = AsyncMock()
    monkeypatch.setattr(harness, "call", start_call)
    with pytest.raises(ValueError, match="no calls started"):
        await harness.run(
            SimpleNamespace(
                base_url="http://localhost:8000", expected_model="gpt-realtime-2.1-mini"
            ),
            None,
        )
    start_call.assert_not_awaited()
