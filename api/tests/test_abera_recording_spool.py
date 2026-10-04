"""Managed Dograh keeps long recordings off the call process heap."""

import io
import os
import wave

import pytest

from api.services.pipecat.in_memory_buffers import InMemoryAudioBuffer


@pytest.mark.asyncio
async def test_managed_recording_spills_to_disk_without_changing_wav(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    buffer = InMemoryAudioBuffer(workflow_run_id=1, sample_rate=16000)
    pcm = b"\x00\x01" * (1024 * 1024 + 1)
    try:
        await buffer.append(pcm)
        assert buffer.size == len(pcm)
        assert buffer._spool._rolled

        with wave.open(io.BytesIO(await buffer.to_wav_bytes()), "rb") as wav:
            assert wav.getframerate() == 16000
            assert wav.getnchannels() == 1
            assert wav.readframes(wav.getnframes()) == pcm
    finally:
        await buffer.close()
    assert buffer._spool.closed


@pytest.mark.asyncio
async def test_oss_recording_keeps_existing_memory_behavior(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    buffer = InMemoryAudioBuffer(workflow_run_id=2, sample_rate=8000)
    assert buffer._spool is None
    await buffer.append(b"\x00\x01")
    with wave.open(io.BytesIO(await buffer.to_wav_bytes()), "rb") as wav:
        assert wav.readframes(1) == b"\x00\x01"


@pytest.mark.asyncio
async def test_managed_wav_file_preserves_audio_without_building_wav_bytes(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "abera")
    buffer = InMemoryAudioBuffer(workflow_run_id=3, sample_rate=16000)
    pcm = b"\x01\x02" * (1024 * 1024 + 1)
    path = None
    try:
        await buffer.append(pcm)
        path = await buffer.to_wav_tempfile()
        with wave.open(path, "rb") as wav:
            assert wav.getframerate() == 16000
            assert wav.getnchannels() == 1
            assert wav.readframes(wav.getnframes()) == pcm
    finally:
        await buffer.close()
        if path is not None:
            os.unlink(path)
