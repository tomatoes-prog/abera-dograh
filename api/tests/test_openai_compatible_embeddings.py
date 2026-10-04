"""Custom embeddings use the configured endpoint, credential and vector size."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from pydantic import TypeAdapter, ValidationError

from api.services.configuration import check_validity
from api.services.configuration.registry import EmbeddingsConfig, OpenAICompatibleEmbeddingsConfiguration
from api.services.gen_ai.embedding.factory import build_embedding_service
from api.services.gen_ai.embedding.openai_compatible_service import validate_embedding_vectors


def _configuration(**changes):
    values = {"provider": "openai_compatible", "api_key": "own-provider-key", "model": "provider/model-v1", "base_url": "https://embeddings.example/v1"}
    values.update(changes)
    return TypeAdapter(EmbeddingsConfig).validate_python(values)


def test_custom_provider_preserves_url_model_and_key_through_configuration_schema():
    config = _configuration(base_url=" https://embeddings.example/v1/ ", model=" provider/model-v1 ")
    assert isinstance(config, OpenAICompatibleEmbeddingsConfiguration)
    assert config.base_url == "https://embeddings.example/v1"
    assert config.model_dump()["api_key"] == "own-provider-key"
    assert config.model == "provider/model-v1"


@pytest.mark.parametrize("url", [
    "file:///private/keys", "https://user:secret@embeddings.example/v1",
    "https://embeddings.example/v1?api_key=secret", "https://embeddings.example/v1#secret",
    "https://embeddings.example/v1/embeddings", "https://embeddings.example:invalid/v1", "",
])
def test_custom_url_rejects_embedded_secrets_invalid_urls_and_complete_endpoint(url):
    with pytest.raises(ValidationError):
        _configuration(base_url=url)


@pytest.mark.parametrize("vector", [[0.1] * 1024, [float("nan")] * 1536, [float("inf")] * 1536, [True] * 1536])
def test_incompatible_or_invalid_vectors_are_rejected_before_indexing(vector):
    with pytest.raises(ValueError):
        validate_embedding_vectors([vector], expected_count=1)


def test_missing_vectors_are_rejected():
    with pytest.raises(ValueError, match="número"):
        validate_embedding_vectors([], expected_count=1)


@pytest.mark.asyncio
async def test_custom_endpoint_handles_indexing_and_search_without_any_vendor_proxy(monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={"object": "list", "model": body["model"], "data": [
            {"object": "embedding", "index": index, "embedding": [0.1] * 1536}
            for index, _ in enumerate(body["input"])
        ], "usage": {"prompt_tokens": 3, "total_tokens": 3}})

    db = SimpleNamespace(search_similar_chunks=AsyncMock(return_value=[{"chunk_text": "Bogotá"}]))
    config = _configuration()
    service = await build_embedding_service(
        db_client=db, provider=config.provider, api_key=config.api_key,
        model=config.model, base_url=config.base_url, resolve_correlation=True,
    )
    assert service.client._client.follow_redirects is False
    await service.client.close()
    service.client = openai.AsyncOpenAI(
        api_key=config.api_key, base_url=config.base_url, max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=False, trust_env=False),
    )
    try:
        vectors = await service.embed_texts(["Atención en Bogotá", "Horario de entregas"])
        result = await service.search_similar_chunks("entregas", organization_id=42, document_uuids=["own-document"])
        assert len(vectors) == 2 and all(len(vector) == 1536 for vector in vectors)
        assert result == [{"chunk_text": "Bogotá"}]
        assert all(str(request.url) == "https://embeddings.example/v1/embeddings" for request in requests)
        assert all(request.headers["authorization"] == "Bearer own-provider-key" for request in requests)
        assert all(json.loads(request.content)["model"] == "provider/model-v1" for request in requests)
        assert all("metadata" not in json.loads(request.content) for request in requests)
        assert db.search_similar_chunks.await_args.kwargs["organization_id"] == 42
        assert db.search_similar_chunks.await_args.kwargs["document_uuids"] == ["own-document"]
    finally:
        await service.client.close()


@pytest.mark.parametrize("dimensions", [1536, 1024])
def test_configuration_probes_embeddings_instead_of_requiring_model_catalog(monkeypatch, dimensions):
    requests = []
    original = openai.OpenAI
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"object": "list", "model": "provider/model-v1", "data": [
            {"object": "embedding", "index": 0, "embedding": [0.1] * dimensions}
        ], "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    def make_client(**kwargs):
        assert kwargs["http_client"].follow_redirects is False
        kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False, trust_env=False)
        return original(**kwargs)
    monkeypatch.setattr(check_validity.openai, "OpenAI", make_client)
    errors = check_validity.UserConfigurationValidator()._validate_service(_configuration(), "embeddings", required=False)
    assert bool(errors) == (dimensions != 1536)
    if errors:
        assert "1536" in errors[0]["message"]
    assert len(requests) == 1 and str(requests[0].url).endswith("/v1/embeddings")
    assert json.loads(requests[0].content)["input"] == ["Prueba"]


def test_hosted_mode_rejects_private_embedding_endpoints_before_provider_validation(monkeypatch):
    from api.utils import url_security
    monkeypatch.setattr(url_security, "DEPLOYMENT_MODE", "abera")
    probe = AsyncMock(side_effect=AssertionError("must not contact internal services"))
    validator = check_validity.UserConfigurationValidator()
    monkeypatch.setitem(validator._validator_map, "openai_compatible", probe)
    errors = validator._validate_service(_configuration(base_url="http://169.254.169.254/v1"), "embeddings")
    assert errors and "public IP" in errors[0]["message"]
    probe.assert_not_called()


@pytest.mark.parametrize("key", ["", "**********-key"])
def test_changing_url_cannot_forward_an_inherited_or_hidden_key(key):
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
    from api.services.configuration.merge import merge_user_configurations

    saved = EffectiveAIModelConfiguration(embeddings=_configuration())
    with pytest.raises(ValueError, match="vuelve a ingresar"):
        merge_user_configurations(saved, {"embeddings": {
            "provider": "openai_compatible", "model": "provider/model-v1", "base_url": "https://another-provider.example/v1", "api_key": key,
        }})


def test_unchanged_url_keeps_masked_key_and_changed_url_accepts_a_new_key():
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
    from api.services.configuration.masking import mask_key
    from api.services.configuration.merge import merge_user_configurations

    saved = EffectiveAIModelConfiguration(embeddings=_configuration())
    payload = saved.embeddings.model_dump()
    payload["api_key"] = mask_key("own-provider-key")
    unchanged = merge_user_configurations(saved, {"embeddings": payload})
    assert unchanged.embeddings.api_key == "own-provider-key"
    payload.update(base_url="https://another-provider.example/v1", api_key="new-provider-key")
    changed = merge_user_configurations(saved, {"embeddings": payload})
    assert changed.embeddings.api_key == "new-provider-key"
    assert saved.embeddings.base_url == "https://embeddings.example/v1"


def test_v2_configuration_blocks_redirecting_a_stored_key_to_another_endpoint():
    from api.schemas.ai_model_configuration import OrganizationAIModelConfigurationV2
    from api.services.configuration.ai_model_configuration import mask_ai_model_configuration_v2, merge_ai_model_configuration_v2_secrets

    saved = OrganizationAIModelConfigurationV2.model_validate({
        "mode": "byok", "byok": {"mode": "pipeline", "pipeline": {
            "llm": {"provider": "openai", "api_key": "text-key"},
            "tts": {"provider": "openai", "api_key": "speech-key"},
            "stt": {"provider": "openai", "api_key": "speech-key"},
            "embeddings": _configuration().model_dump(),
        }},
    })
    payload = mask_ai_model_configuration_v2(saved)
    payload["byok"]["pipeline"]["embeddings"]["base_url"] = "https://another-provider.example/v1"
    incoming = OrganizationAIModelConfigurationV2.model_validate(payload)
    with pytest.raises(ValueError, match="vuelve a ingresar"):
        merge_ai_model_configuration_v2_secrets(incoming, saved)
