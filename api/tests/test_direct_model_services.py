import copy
import io
import json
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from api.services.model_services import transcription, voices, workflow_generation


@pytest.fixture
def direct_http(monkeypatch):
    requests = []
    state = SimpleNamespace(status=200, payload={})

    def respond(request):
        requests.append(request)
        return httpx.Response(state.status, json=state.payload)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    return SimpleNamespace(requests=requests, state=state)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["elevenlabs", "cartesia", "deepgram", "rime"])
async def test_voice_catalog_uses_direct_provider_and_only_this_tenants_key(
    monkeypatch, direct_http, provider
):
    saved = SimpleNamespace(provider=provider, api_key="own-tenant-key")
    resolved = AsyncMock(
        return_value=SimpleNamespace(effective=SimpleNamespace(tts=saved))
    )
    monkeypatch.setattr(voices, "get_resolved_ai_model_configuration", resolved)
    direct_http.state.payload = {
        "elevenlabs": {
            "voices": [
                {"voice_id": "voice-1", "name": "Sofía", "labels": {"language": "es"}}
            ]
        },
        "cartesia": {"data": [{"id": "voice-1", "name": "Sofía", "language": "es"}]},
        "deepgram": {
            "tts": [
                {
                    "canonical_name": "aura-2-celeste-es",
                    "name": "Celeste",
                    "languages": ["es"],
                    "architecture": "aura-2",
                }
            ]
        },
        "rime": [
            {
                "speaker": "sofia",
                "lang": "spa",
                "modelId": "mist",
                "genre": ["conversational"],
            }
        ],
    }[provider]
    result = await voices.get_direct_voices(
        organization_id=42, provider=provider, language="es"
    )
    assert len(result["voices"]) == 1 and result["facets"]["languages"] == ["es"]
    request = direct_http.requests[0]
    assert "dograh" not in request.url.host
    assert "own-tenant-key" not in str(request.url)
    if provider != "rime":
        assert "own-tenant-key" in " ".join(request.headers.values())
    resolved.assert_awaited_once_with(organization_id=42)


@pytest.mark.asyncio
async def test_voice_catalog_never_borrows_key_of_another_provider(
    monkeypatch, direct_http
):
    monkeypatch.setattr(
        voices,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(
                    tts=SimpleNamespace(provider="cartesia", api_key="wrong-key")
                ),
            )
        ),
    )
    with pytest.raises(HTTPException) as error:
        await voices.get_direct_voices(
            organization_id=42, provider="elevenlabs", api_key="********"
        )
    assert error.value.status_code == 422 and direct_http.requests == []
    direct_http.state.payload = {"voices": []}
    await voices.get_direct_voices(
        organization_id=42, provider="elevenlabs", api_key="new-elevenlabs-key"
    )
    assert direct_http.requests[0].headers["xi-api-key"] == "new-elevenlabs-key"


@pytest.mark.asyncio
async def test_provider_limit_error_is_preserved(monkeypatch, direct_http):
    monkeypatch.setattr(
        voices,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(
                    tts=SimpleNamespace(provider="elevenlabs", api_key="test-key")
                ),
            )
        ),
    )
    direct_http.state.status = 429
    with pytest.raises(HTTPException) as error:
        await voices.get_direct_voices(organization_id=42, provider="elevenlabs")
    assert error.value.status_code == 429


def _audio() -> UploadFile:
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 32000)
    data.seek(0)
    return UploadFile(data, filename="saludo.wav")


@pytest.mark.asyncio
async def test_realtime_key_can_transcribe_file_without_changing_live_model(
    monkeypatch, direct_http
):
    realtime = SimpleNamespace(
        provider="openai_realtime", model="gpt-realtime-2.1-mini", api_key="tenant-key"
    )
    resolved = AsyncMock(
        return_value=SimpleNamespace(
            effective=SimpleNamespace(stt=None, llm=None, realtime=realtime)
        )
    )
    monkeypatch.setattr(transcription, "get_resolved_ai_model_configuration", resolved)
    direct_http.state.payload = {"text": "Hola, ¿cómo puedo ayudarte?"}
    result = await transcription.transcribe_uploaded_audio(
        organization_id=42, file=_audio(), language="es"
    )
    request = direct_http.requests[0]
    assert str(request.url) == "https://api.openai.com/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer tenant-key"
    assert (
        b"gpt-4o-mini-transcribe" in request.content
        and b"gpt-realtime-2.1-mini" not in request.content
    )
    assert result["transcript"].startswith("Hola") and result["duration_seconds"] == 2
    assert realtime.model == "gpt-realtime-2.1-mini"
    resolved.assert_awaited_once_with(organization_id=42)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["deepgram", "elevenlabs"])
async def test_standalone_file_transcription_uses_configured_provider(
    monkeypatch, direct_http, provider
):
    stt = SimpleNamespace(
        provider=provider,
        model="nova-3" if provider == "deepgram" else "scribe_v1",
        api_key="own-key",
    )
    monkeypatch.setattr(
        transcription,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(stt=stt, realtime=None, llm=None),
            )
        ),
    )
    direct_http.state.payload = (
        {"results": {"channels": [{"alternatives": [{"transcript": "Hola Colombia"}]}]}}
        if provider == "deepgram"
        else {"text": "Hola Colombia"}
    )
    result = await transcription.transcribe_uploaded_audio(
        organization_id=42, file=_audio(), language="es"
    )
    assert result["provider"] == provider and result["transcript"] == "Hola Colombia"
    assert "dograh" not in direct_http.requests[0].url.host
    assert b"RIFF" in direct_http.requests[0].content


@pytest.mark.asyncio
async def test_missing_or_overlarge_audio_does_not_contact_provider(
    monkeypatch, direct_http
):
    config = SimpleNamespace(
        effective=SimpleNamespace(stt=None, realtime=None, llm=None)
    )
    monkeypatch.setattr(
        transcription,
        "get_resolved_ai_model_configuration",
        AsyncMock(return_value=config),
    )
    with pytest.raises(HTTPException) as error:
        await transcription.transcribe_uploaded_audio(
            organization_id=42, file=_audio(), language="es"
        )
    assert error.value.status_code == 422 and direct_http.requests == []
    config.effective.stt = SimpleNamespace(
        provider="openai", api_key="own-key", model="gpt-4o-mini-transcribe"
    )
    monkeypatch.setattr(transcription, "MAX_AUDIO_BYTES", 128)
    with pytest.raises(HTTPException) as error:
        await transcription.transcribe_uploaded_audio(
            organization_id=42, file=_audio(), language="es"
        )
    assert error.value.status_code == 413 and direct_http.requests == []


def test_generated_agent_validates_graph_and_rejects_foreign_resources():
    assert (
        workflow_generation.validate_generated_workflow(
            copy.deepcopy(workflow_generation._EXAMPLE)
        )["name"]
        == "Atención al cliente"
    )
    malformed = copy.deepcopy(workflow_generation._EXAMPLE)
    malformed["workflow_definition"]["nodes"][1]["data"]["document_uuids"] = [
        "foreign-document"
    ]
    with pytest.raises(ValueError, match="otra cuenta"):
        workflow_generation.validate_generated_workflow(malformed)
    malformed = copy.deepcopy(workflow_generation._EXAMPLE)
    malformed["workflow_definition"]["edges"][0]["target"] = "missing-node"
    with pytest.raises(ValueError):
        workflow_generation.validate_generated_workflow(malformed)


@pytest.mark.asyncio
async def test_template_creation_uses_organization_llm_without_vendor_proxy(
    monkeypatch,
):
    config = SimpleNamespace(llm=SimpleNamespace(provider="openai", api_key="own-key"))
    resolve = AsyncMock(return_value=SimpleNamespace(effective=config))
    llm = SimpleNamespace(
        run_inference=AsyncMock(return_value=json.dumps(workflow_generation._EXAMPLE))
    )
    monkeypatch.setattr(
        workflow_generation, "get_resolved_ai_model_configuration", resolve
    )
    monkeypatch.setattr(
        workflow_generation, "create_llm_service", lambda effective: llm
    )
    result = await workflow_generation.generate_workflow(
        organization_id=42,
        call_type="INBOUND",
        use_case="Soporte",
        activity_description="Ayuda con pedidos.",
    )
    assert result["name"] == "Atención al cliente"
    resolve.assert_awaited_once_with(organization_id=42)
    llm.run_inference.assert_awaited_once()
