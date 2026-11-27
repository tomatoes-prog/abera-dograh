from unittest.mock import AsyncMock

import pytest

from api.services.workflow.pipecat_engine_callbacks import create_max_duration_callback
from pipecat.utils.enums import EndTaskReason


@pytest.mark.asyncio
async def test_max_duration_callback_aborts_immediately():
    engine = AsyncMock()

    callback = create_max_duration_callback(engine)
    await callback()

    engine.end_call_with_reason.assert_awaited_once_with(
        EndTaskReason.CALL_DURATION_EXCEEDED.value,
        abort_immediately=True,
    )
