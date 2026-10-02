"""Server-side conversation compaction for OpenAI Realtime calls.

The Realtime API bills the full server-side history on every response, so
cost and TPM grow with turn count even though the audio itself streams once.
Every ``every_n_turns`` completed turns, this summarizes the oldest turns with
the call's text LLM and replaces them server-side with a single system note::

    conversation.item.delete  (old message items + complete tool pairs)
    conversation.item.create  (role="system" summary note)

The most recent ``keep_last_turns`` turns stay verbatim, in-flight items are
never touched, and ``function_call``/``function_call_output`` items are only
removed as complete pairs. Our own summary notes are never deleted. If the
summary inference fails, nothing is deleted and the next trigger retries.

Off unless the run enables it via the ``realtime_history_compaction_turns``
workflow configuration (0 disables). Realtime-only: cascade pipelines keep
using ``context_compaction_enabled``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.openai.realtime.events import (
    ConversationItem,
    ConversationItemCreateEvent,
    ConversationItemDeleteEvent,
    ItemContent,
)

DEFAULT_KEEP_LAST_TURNS = 4
SUMMARY_INPUT_CHAR_BUDGET = 6000
SUMMARY_TIMEOUT_SECONDS = 60
SUMMARY_ATTEMPTS = 2

SUMMARY_INSTRUCTIONS = {
    "es": (
        "Resume la conversación telefónica anterior en máximo 150 palabras: "
        "hechos, nombres, cifras, decisiones y temas pendientes. Sin saludos "
        "ni relleno."
    ),
    "en": (
        "Summarize the phone conversation above in at most 150 words: facts, "
        "names, numbers, decisions and open items. No greetings or filler."
    ),
}

SUMMARY_NOTE_PREFIX = {
    "es": "Resumen de la conversación anterior: ",
    "en": "Summary of the earlier conversation: ",
}


@dataclass
class _TrackedItem:
    item_id: str
    kind: str
    role: str | None = None
    call_id: str | None = None


@dataclass
class _CompletedTurn:
    turn_id: int
    user_text: str
    assistant_text: str


@dataclass
class CompactionResult:
    """Outcome of one compaction cycle (also used in logs)."""

    turns_compacted: int = 0
    items_deleted: int = 0
    summary_chars: int = 0
    skipped_reason: str | None = None


def _item_kind(item: object) -> str:
    kind = getattr(item, "type", None)
    return kind if isinstance(kind, str) and kind else "other"


async def summarize_turns(
    inference_llm,
    turns: list[_CompletedTurn],
    *,
    language: str = "es",
    workflow_run_id: int | None = None,
) -> str | None:
    """Summarize completed turns with the call's text LLM (background-safe).

    Returns the summary text, or None when inference fails so the caller can
    skip deletion instead of losing history.
    """
    body = "\n".join(
        f"usuario: {turn.user_text}\nasistente: {turn.assistant_text}"
        for turn in turns
    )
    if len(body) > SUMMARY_INPUT_CHAR_BUDGET:
        body = body[-SUMMARY_INPUT_CHAR_BUDGET:]
    instruction = SUMMARY_INSTRUCTIONS.get(language, SUMMARY_INSTRUCTIONS["es"])
    context = LLMContext()
    context.set_messages([{"role": "user", "content": body}])
    for attempt in range(1, SUMMARY_ATTEMPTS + 1):
        try:
            summary = await asyncio.wait_for(
                inference_llm.run_inference(context, system_instruction=instruction),
                timeout=SUMMARY_TIMEOUT_SECONDS,
            )
            if summary and summary.strip():
                return summary.strip()
            logger.warning(
                "Realtime compaction: empty summary (attempt "
                f"{attempt}, run {workflow_run_id})"
            )
        except Exception as exc:
            logger.warning(
                "Realtime compaction: summary inference failed "
                f"(attempt {attempt}, run {workflow_run_id}): {exc}"
            )
    return None


class RealtimeHistoryCompactor:
    """Compact OpenAI Realtime server history every N completed turns."""

    def __init__(
        self,
        *,
        every_n_turns: int,
        keep_last_turns: int = DEFAULT_KEEP_LAST_TURNS,
        language: str = "es",
        summarize=None,
        workflow_run_id: int | None = None,
    ):
        self._every_n_turns = max(0, int(every_n_turns or 0))
        self._keep_last_turns = max(1, int(keep_last_turns or DEFAULT_KEEP_LAST_TURNS))
        self._language = language if language in SUMMARY_INSTRUCTIONS else "es"
        self._summarize = summarize
        self._workflow_run_id = workflow_run_id
        self._service = None
        self._is_active = lambda: True
        self._items: list[_TrackedItem] = []
        self._turns: list[_CompletedTurn] = []
        self._compacted_through_turn = 0
        self._summary_item_ids: set[str] = set()
        self._completed_turns = 0
        self._cycle_lock = asyncio.Lock()
        self._cycle_task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self._every_n_turns > 0

    def attach(
        self,
        service,
        *,
        is_active=None,
    ) -> "RealtimeHistoryCompactor":
        """Track server item IDs on the realtime service (multi-handler safe)."""
        self._service = service
        if is_active is not None:
            self._is_active = is_active
        service.add_event_handler(
            "on_conversation_item_created", self._on_item_created
        )
        return self

    async def _on_item_created(self, service, item_id: str, item: object) -> None:
        # Note: pipecat invokes event handlers as handler(service, *args),
        # so the owning service arrives as the first positional argument.
        self._items.append(
            _TrackedItem(
                item_id=item_id,
                kind=_item_kind(item),
                role=getattr(item, "role", None),
                call_id=getattr(item, "call_id", None),
            )
        )

    async def notify_turn_completed(
        self, turn_id: int, user_text: str, assistant_text: str
    ) -> None:
        """Called (via TranscriptLogCoordinator) when a turn has both texts."""
        if not self.enabled or not assistant_text:
            return
        self._completed_turns += 1
        self._turns.append(
            _CompletedTurn(
                turn_id=turn_id, user_text=user_text or "", assistant_text=assistant_text
            )
        )
        if self._completed_turns % self._every_n_turns == 0:
            if self._cycle_task is None or self._cycle_task.done():
                self._cycle_task = asyncio.create_task(self._run_cycle())
            else:
                logger.debug(
                    "Realtime compaction: previous cycle still running, "
                    f"skipping trigger at turn {turn_id}"
                )

    async def _run_cycle(self) -> CompactionResult:
        result = CompactionResult()
        if self._service is None or self._summarize is None:
            result.skipped_reason = "not attached"
            return result
        if not self._is_active():
            result.skipped_reason = "call ending"
            return result
        if self._cycle_lock.locked():
            result.skipped_reason = "already running"
            return result
        async with self._cycle_lock:
            return await self._compact_once()

    def _delete_set(self) -> tuple[list[_TrackedItem], set[str]]:
        """Old items safe to delete + ids of our own summary notes to keep."""
        # Keep window scales with observed fragmentation: audio commits can
        # create many server items per turn, so a fixed item count would keep
        # less than keep_last_turns of verbatim history.
        turns_seen = max(1, self._completed_turns)
        per_turn = max(2, -(-len(self._items) // turns_seen))
        keep_messages = max(10, self._keep_last_turns * per_turn)
        # System notes (including our own summaries) are never eligible:
        # they hold prior compactions and stay tiny.
        message_indexes = [
            index
            for index, item in enumerate(self._items)
            if item.kind == "message"
            and item.role != "system"
            and item.item_id not in self._summary_item_ids
        ]
        cutoff = (
            message_indexes[-keep_messages]
            if len(message_indexes) > keep_messages
            else None
        )
        if cutoff is None:
            return [], set(self._summary_item_ids)

        old = self._items[:cutoff]
        # Tool pairs only leave together and only when both sides are old.
        paired: dict[str, list[_TrackedItem]] = {}
        for item in old:
            if item.kind in ("function_call", "function_call_output") and item.call_id:
                paired.setdefault(item.call_id, []).append(item)
        paired_ids: set[str] = set()
        for call_id, members in paired.items():
            kinds = {member.kind for member in members}
            if {"function_call", "function_call_output"} <= kinds:
                paired_ids.update(member.item_id for member in members)
        # Invariant: old messages + complete old tool pairs, nothing else.
        # System notes are always kept (see above).
        delete = [
            item
            for item in old
            if (item.kind == "message" and item.role != "system")
            or item.item_id in paired_ids
        ]
        return delete, set(self._summary_item_ids)

    async def _compact_once(self) -> CompactionResult:
        result = CompactionResult()
        horizon = self._completed_turns - self._keep_last_turns
        pending = [
            turn
            for turn in self._turns
            if turn.turn_id <= horizon and turn.turn_id > self._compacted_through_turn
        ]
        delete, _ = self._delete_set()
        if not pending or not delete:
            result.skipped_reason = "nothing eligible"
            return result
        if self._summarize is None:
            result.skipped_reason = "no summarizer"
            return result
        summary = await self._summarize(pending)
        if not summary:
            result.skipped_reason = "summary failed"
            logger.warning(
                "Realtime compaction: skipping deletion, summary failed "
                f"(run {self._workflow_run_id})"
            )
            return result
        note = SUMMARY_NOTE_PREFIX[self._language] + summary
        try:
            await self._service.send_client_event(
                ConversationItemCreateEvent(
                    item=ConversationItem(
                        type="message",
                        role="system",
                        content=[ItemContent(type="input_text", text=note)],
                    )
                )
            )
        except Exception as exc:
            result.skipped_reason = f"summary insert failed: {exc}"
            logger.warning(f"Realtime compaction: {result.skipped_reason}")
            return result
        deleted_ids: set[str] = set()
        for item in delete:
            try:
                await self._service.send_client_event(
                    ConversationItemDeleteEvent(item_id=item.item_id)
                )
                deleted_ids.add(item.item_id)
            except Exception as exc:
                logger.warning(
                    f"Realtime compaction: delete {item.item_id} failed: {exc}"
                )
        # Only drop ids we actually deleted; failures stay tracked so a
        # later cycle retries them instead of re-summarizing.
        self._items = [
            item for item in self._items if item.item_id not in deleted_ids
        ]
        deleted = len(deleted_ids)
        self._compacted_through_turn = max(
            self._compacted_through_turn, max(turn.turn_id for turn in pending)
        )
        self._turns = [
            turn
            for turn in self._turns
            if turn.turn_id > self._compacted_through_turn
        ]
        result.turns_compacted = len(pending)
        result.items_deleted = deleted
        result.summary_chars = len(note)
        logger.info(
            "Realtime compaction: compacted "
            f"{result.turns_compacted} turns into {result.summary_chars} chars, "
            f"deleted {deleted}/{len(delete)} items (run {self._workflow_run_id})"
        )
        return result
