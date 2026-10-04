import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.abera import voice_minutes as voice


@pytest.fixture
def receipts(monkeypatch):
    save, remove = AsyncMock(), AsyncMock()
    monkeypatch.setattr(voice, "save_final_receipt", save)
    monkeypatch.setattr(voice, "remove_final_receipt", remove)
    return save, remove


@pytest.mark.parametrize("url", ["http://billing.local/live", "https://evil.example/live",
                                   "https://abc123def4.execute-api.us-east-2.amazonaws.com/live?x=y"])
def test_billing_signature_cannot_be_sent_to_arbitrary_host(url):
    with pytest.raises(voice.VoiceAuthorizationError):
        voice.BillingVoiceClient(url, "sub-123")


@pytest.mark.asyncio
async def test_ringing_and_failed_start_do_not_consume_ai_seconds(receipts):
    client = SimpleNamespace(request=AsyncMock(return_value={"status": "ACTIVE", "authorized_seconds": 30}))
    call = voice.ManagedVoiceSession(3, AsyncMock(), client=client)
    await call.finish()
    client.request.assert_not_awaited()
    call = voice.ManagedVoiceSession(4, AsyncMock(), client=client)
    await call.authorize()
    await call.finish()
    assert client.request.await_args.kwargs["actual_seconds"] == 0


@pytest.mark.asyncio
async def test_final_duration_is_saved_before_delivery_and_never_includes_cleanup(receipts):
    now = [10.0]
    client = SimpleNamespace(request=AsyncMock(return_value={"status": "ACTIVE", "authorized_seconds": 30}))
    call = voice.ManagedVoiceSession(4, AsyncMock(), client=client, clock=lambda: now[0])
    await call.authorize()
    now[0] = 12
    call.started()
    now[0] = 22.2
    call.stopped()
    now[0] = 29
    await call.finish()
    await call.finish()
    receipts[0].assert_awaited_once_with(call.call_id, 11)
    assert client.request.await_count == 2
    assert client.request.await_args.kwargs["actual_seconds"] == 11


@pytest.mark.asyncio
async def test_failed_billing_cannot_extend_voice_deadline(receipts, monkeypatch):
    now = [0.0]
    async def sleep(seconds):
        now[0] += seconds
    monkeypatch.setattr(voice.asyncio, "sleep", sleep)
    client = SimpleNamespace(request=AsyncMock(side_effect=voice.VoiceAuthorizationError("outage")))
    stop = AsyncMock()
    call = voice.ManagedVoiceSession(5, stop, client=client, clock=lambda: now[0])
    call.origin, call.authorized = 0, 30
    call.started()
    await call._watch()
    stop.assert_awaited_once()
    assert now[0] == 29
    await call.finish()
    receipts[0].assert_awaited_once_with(call.call_id, 29)
    receipts[1].assert_not_awaited()  # remains durable for retry


@pytest.mark.asyncio
async def test_last_partial_block_stops_and_does_not_overrun(receipts, monkeypatch):
    now = [0.0]
    async def sleep(seconds):
        now[0] += seconds
    monkeypatch.setattr(voice.asyncio, "sleep", sleep)
    stop = AsyncMock()
    client = SimpleNamespace(request=AsyncMock(side_effect=voice.VoiceAuthorizationError("empty")))
    call = voice.ManagedVoiceSession(6, stop, client=client, clock=lambda: now[0])
    call.origin, call.authorized = 0, 4
    call.started()
    await call._watch()
    assert now[0] == 3
    stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_after_restore_only_sends_final_receipts(monkeypatch):
    from api.services.abera import bedrock
    # Receipts survive both restoring a backup and downgrading Pro to Basic.
    monkeypatch.setattr(bedrock, "managed_nova_enabled", lambda: False)
    monkeypatch.setattr(voice, "ABERA_SUBSCRIPTION_ID", "sub-test")
    monkeypatch.setattr(voice, "ABERA_BILLING_API_URL", "https://abcdefghij.execute-api.us-east-2.amazonaws.com/live")
    redis = AsyncMock()
    redis.get.return_value = "0"
    redis.hscan.return_value = (0, {"run-1-stable": "19"})
    redis.__aenter__.return_value = redis
    monkeypatch.setattr(voice.Redis, "from_url", lambda *a, **k: redis)
    client = SimpleNamespace(request=AsyncMock(return_value={}))
    monkeypatch.setattr(voice, "BillingVoiceClient", lambda: client)
    await voice.retry_voice_receipts({})
    client.request.assert_awaited_once_with("settle", call_id="run-1-stable", actual_seconds=19)


@pytest.mark.asyncio
async def test_deadline_can_finish_inside_transport_close_handler(receipts):
    client = SimpleNamespace(request=AsyncMock(return_value={}))
    call = voice.ManagedVoiceSession(7, AsyncMock(), client=client, clock=lambda: 30)
    call.origin, call.authorized = 0, 30
    call.billable_at = 0
    call.stop_call = call.finish
    call.watchdog = asyncio.create_task(call._watch())
    await call.watchdog
    assert call.finished
    receipts[0].assert_awaited_once_with(call.call_id, 30)


@pytest.mark.asyncio
async def test_new_runtime_clears_only_call_leases_and_preserves_jobs_and_receipts():
    from api.services.abera.reset_runtime_leases import reset_runtime_leases
    keys = {"arq:queue", "arq:job:123", "abera:voice:final-receipts", "concurrent_calls:42",
            "concurrent_calls_fleet", "workflow_slot_mapping:123", "rate_limit:42"}
    import fnmatch
    async def scan_iter(*, match, count):
        for key in sorted(keys):
            if fnmatch.fnmatch(key, match):
                yield key
    async def delete(*removed):
        keys.difference_update(removed)
    await reset_runtime_leases(SimpleNamespace(scan_iter=scan_iter, delete=delete))
    assert keys == {"arq:queue", "arq:job:123", "abera:voice:final-receipts"}
