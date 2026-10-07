"""Managed recording uploads use the file transfer path and persist keys."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import workflow_run_artifacts


@pytest.mark.asyncio
async def test_file_backed_recordings_upload_without_byte_copy(monkeypatch):
    filesystem = SimpleNamespace(
        aupload_file=AsyncMock(return_value=True),
        acreate_file_from_bytes=AsyncMock(),
    )
    update_run = AsyncMock()
    monkeypatch.setattr(workflow_run_artifacts, "storage_fs", filesystem)
    monkeypatch.setattr(
        workflow_run_artifacts,
        "get_current_storage_backend",
        lambda: SimpleNamespace(name="S3", value="1"),
    )
    monkeypatch.setattr(
        workflow_run_artifacts.db_client, "update_workflow_run", update_run
    )

    await workflow_run_artifacts.upload_workflow_run_artifacts(
        88,
        mixed_audio_path="/tmp/mixed.wav",
        user_audio_path="/tmp/user.wav",
        bot_audio_path="/tmp/bot.wav",
    )

    assert filesystem.aupload_file.await_count == 3
    filesystem.aupload_file.assert_any_await("/tmp/mixed.wav", "recordings/88.wav")
    filesystem.aupload_file.assert_any_await("/tmp/user.wav", "recordings/88/user.wav")
    filesystem.aupload_file.assert_any_await("/tmp/bot.wav", "recordings/88/bot.wav")
    filesystem.acreate_file_from_bytes.assert_not_awaited()
    assert update_run.await_args.kwargs["extra"]["recordings"].keys() == {
        "mixed",
        "user",
        "bot",
    }
