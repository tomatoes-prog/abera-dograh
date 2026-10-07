"""Unit tests for realtime server-side history compaction (no network)."""

from types import SimpleNamespace

import pytest

from api.services.pipecat.realtime.history_compaction import (
    RealtimeHistoryCompactor,
    summarize_turns,
)


class FakeService:
    def __init__(self):
        self.handlers = {}
        self.sent = []
        self._disconnecting = False

    def add_event_handler(self, name, handler):
        self.handlers[name] = handler

    async def confirm_conversation_item(self, item_id):
        return message(item_id, "system")

    async def delete_conversation_item_confirmed(self, item_id):
        from pipecat.services.openai.realtime.events import ConversationItemDeleteEvent

        await self.send_client_event(ConversationItemDeleteEvent(item_id=item_id))

    async def send_client_event(self, event):
        self.sent.append(event)


def message(item_id, role):
    return SimpleNamespace(id=item_id, type="message", role=role)


def make_compactor(service=None, **kwargs):
    async def summarize(turns):
        return "resumen de %d turnos" % len(turns)

    params = {"every_n_turns": 20, "summarize": summarize}
    params.update(kwargs)
    compactor = RealtimeHistoryCompactor(**params)
    compactor.attach(service or FakeService())
    return compactor


async def drive_turns(compactor, service, count, start=1):
    for turn in range(start, start + count):
        await service.handlers["on_conversation_item_created"](
            service, f"u{turn}", message(f"u{turn}", "user")
        )
        await service.handlers["on_conversation_item_created"](
            service, f"a{turn}", message(f"a{turn}", "assistant")
        )
        await compactor.notify_turn_completed(
            turn, f"pregunta {turn}", f"respuesta {turn}"
        )
    if compactor._cycle_task is not None:
        await compactor._cycle_task


@pytest.mark.asyncio
async def test_disabled_by_default_does_nothing():
    service = FakeService()
    compactor = RealtimeHistoryCompactor(every_n_turns=0, summarize=None)
    compactor.attach(service)
    assert "on_conversation_item_created" in service.handlers
    await compactor.notify_turn_completed(1, "hola", "buenas")
    assert compactor._cycle_task is None
    assert service.sent == []


@pytest.mark.asyncio
async def test_no_compaction_before_cadence():
    service = FakeService()
    compactor = make_compactor(service)
    await drive_turns(compactor, service, 19)
    assert service.sent == []


@pytest.mark.asyncio
async def test_compacts_at_cadence_keeping_recent_turns():
    service = FakeService()
    compactor = make_compactor(service)
    await drive_turns(compactor, service, 20)
    kinds = [getattr(event, "type", "") for event in service.sent]
    assert kinds[0] == "conversation.item.create"
    assert kinds[1:] == ["conversation.item.delete"] * 30
    deleted = {event.item_id for event in service.sent[1:]}
    # Oldest 30 message items go (turns 1-15); newest 10 stay verbatim.
    assert deleted == {f"u{i}" for i in range(1, 16)} | {f"a{i}" for i in range(1, 16)}
    kept = {item.item_id for item in compactor._items}
    assert kept == {f"u{i}" for i in range(16, 21)} | {f"a{i}" for i in range(16, 21)}


@pytest.mark.asyncio
async def test_summary_note_is_never_deleted():
    service = FakeService()
    compactor = make_compactor(service)
    await drive_turns(compactor, service, 20)
    creates = [
        event for event in service.sent if event.type == "conversation.item.create"
    ]
    assert len(creates) == 1
    assert creates[0].item.role == "system"
    # The server echoes the note back as a system item; a later cycle that
    # ages everything out must still keep it.
    await service.handlers["on_conversation_item_created"](
        service, "sys-note-1", message("sys-note-1", "system")
    )
    service.sent.clear()
    await drive_turns(compactor, service, 20, start=21)
    deleted = {
        event.item_id
        for event in service.sent
        if event.type == "conversation.item.delete"
    }
    assert deleted
    assert "sys-note-1" not in deleted


@pytest.mark.asyncio
async def test_incomplete_tool_pair_is_never_split():
    service = FakeService()
    compactor = make_compactor(service)
    # Incomplete pair (call without output) sits among the OLDEST items.
    await service.handlers["on_conversation_item_created"](
        service,
        "call-old",
        SimpleNamespace(id="call-old", type="function_call", call_id="c1"),
    )
    await drive_turns(compactor, service, 20)
    deleted = {
        event.item_id
        for event in service.sent
        if event.type == "conversation.item.delete"
    }
    assert "call-old" not in deleted
    # ...but ordinary old messages around it still go.
    assert "u1" in deleted


@pytest.mark.asyncio
async def test_complete_old_tool_pair_leaves_together():
    service = FakeService()
    compactor = make_compactor(service)
    await service.handlers["on_conversation_item_created"](
        service,
        "call-old",
        SimpleNamespace(id="call-old", type="function_call", call_id="c9"),
    )
    await service.handlers["on_conversation_item_created"](
        service,
        "out-old",
        SimpleNamespace(id="out-old", type="function_call_output", call_id="c9"),
    )
    await drive_turns(compactor, service, 20)
    deleted = {
        event.item_id
        for event in service.sent
        if event.type == "conversation.item.delete"
    }
    assert {"call-old", "out-old"} <= deleted


@pytest.mark.asyncio
async def test_summary_failure_skips_deletion():
    service = FakeService()

    async def broken(turns):
        return None

    compactor = make_compactor(service, summarize=broken)
    await drive_turns(compactor, service, 20)
    assert service.sent == []
    # Nothing dropped from tracking either, so the next cycle retries.
    assert len(compactor._items) == 40


@pytest.mark.asyncio
async def test_skips_cycle_when_call_ending():
    service = FakeService()
    service._disconnecting = True
    compactor = make_compactor(service)
    compactor._is_active = lambda: False
    await drive_turns(compactor, service, 20)
    assert service.sent == []


@pytest.mark.asyncio
async def test_summarize_turns_uses_inference_llm():
    from unittest.mock import AsyncMock

    llm = SimpleNamespace(run_inference=AsyncMock(return_value="  resumen ok  "))
    turns = [
        SimpleNamespace(turn_id=1, user_text="hola", assistant_text="buenas"),
        SimpleNamespace(turn_id=2, user_text="qué hora es", assistant_text="las tres"),
    ]
    result = await summarize_turns(llm, turns, language="es", workflow_run_id=7)
    assert result == "resumen ok"
    context = llm.run_inference.await_args.args[0]
    assert "hola" in context.messages[0]["content"]
    assert "las tres" in context.messages[0]["content"]


@pytest.mark.asyncio
async def test_summarize_turns_returns_none_on_empty():
    from unittest.mock import AsyncMock

    llm = SimpleNamespace(run_inference=AsyncMock(return_value="   "))
    turns = [SimpleNamespace(turn_id=1, user_text="hola", assistant_text="buenas")]
    assert await summarize_turns(llm, turns) is None


@pytest.mark.asyncio
async def test_unconfirmed_summary_is_retried_without_duplicate_insert_or_deletion():
    from unittest.mock import AsyncMock

    service = FakeService()
    summarize = AsyncMock(return_value="primer resumen")
    service.confirm_conversation_item = AsyncMock(side_effect=TimeoutError())
    compactor = make_compactor(service, summarize=summarize)
    await drive_turns(compactor, service, 20)
    assert [event.type for event in service.sent] == ["conversation.item.create"]
    service.confirm_conversation_item.side_effect = None
    await compactor._run_cycle()
    assert sum(event.type == "conversation.item.create" for event in service.sent) == 1
    summarize.assert_awaited_once()
    assert compactor._pending_summary is None


@pytest.mark.asyncio
async def test_cumulative_summary_replaces_only_our_previous_note():
    from unittest.mock import AsyncMock

    service = FakeService()
    summarize = AsyncMock(side_effect=["dato importante", "dato importante y nuevo"])
    compactor = make_compactor(service, summarize=summarize)
    await drive_turns(compactor, service, 20)
    previous_id = service.sent[0].item.id
    await service.handlers["on_conversation_item_created"](
        service, previous_id, message(previous_id, "system")
    )
    await service.handlers["on_conversation_item_created"](
        service, "instructions", message("instructions", "system")
    )
    await drive_turns(compactor, service, 20, start=21)
    inputs = summarize.await_args.args[0]
    assert inputs[0].assistant_text == "dato importante"
    deleted = {
        event.item_id
        for event in service.sent
        if event.type == "conversation.item.delete"
    }
    assert previous_id in deleted
    assert "instructions" not in deleted
    assert len(compactor._summary_item_ids) == 1


@pytest.mark.asyncio
async def test_failed_deletion_is_not_forgotten_or_resummarized():
    from unittest.mock import AsyncMock

    service = FakeService()
    summarize = AsyncMock(return_value="resumen")
    service.delete_conversation_item_confirmed = AsyncMock(side_effect=TimeoutError())
    compactor = make_compactor(service, summarize=summarize)
    await drive_turns(compactor, service, 20)
    assert compactor._pending_deletions
    service.delete_conversation_item_confirmed.side_effect = None
    await compactor._run_cycle()
    assert not compactor._pending_deletions
    summarize.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_budget_preserves_prior_context():
    from unittest.mock import AsyncMock

    llm = SimpleNamespace(run_inference=AsyncMock(return_value="resumen"))
    turns = [
        SimpleNamespace(
            turn_id=0, user_text="Resumen anterior", assistant_text="dato inicial"
        )
    ]
    turns += [
        SimpleNamespace(turn_id=i, user_text="x" * 1000, assistant_text="y" * 1000)
        for i in range(1, 10)
    ]
    await summarize_turns(llm, turns)
    body = llm.run_inference.await_args.args[0].messages[0]["content"]
    assert "dato inicial" in body
    assert len(body) <= 6000
