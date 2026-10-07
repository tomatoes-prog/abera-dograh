from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from api.routes import knowledge_base as routes
from api.schemas.knowledge_base import (
    ChunkSearchRequestSchema,
    DocumentUploadRequestSchema,
    ProcessDocumentRequestSchema,
)
from api.tasks import knowledge_base_processing as task

DOCUMENT_UUID = "b082a155-766f-4941-9e52-a0858e699689"
KEY = f"knowledge_base/42/{DOCUMENT_UUID}/catálogo.txt"


@pytest.fixture
def local_task(monkeypatch):
    document = SimpleNamespace(
        id=11,
        organization_id=42,
        document_uuid=DOCUMENT_UUID,
        filename="catálogo.txt",
        custom_metadata={"s3_key": KEY},
    )
    client = SimpleNamespace(
        get_document_by_id=AsyncMock(return_value=document),
        update_document_status=AsyncMock(),
        get_document_by_hash=AsyncMock(return_value=None),
        compute_file_hash=Mock(return_value="hash"),
        get_mime_type=Mock(return_value="text/plain"),
        update_document_metadata=AsyncMock(),
        update_document_full_text=AsyncMock(),
        replace_chunks_for_document=AsyncMock(),
    )
    monkeypatch.setattr(task, "db_client", client)

    async def download(key, path, *, max_size):
        with open(path, "w", encoding="utf-8") as file:
            file.write("Atención en Bogotá")
        return True

    storage = SimpleNamespace(adownload_file=AsyncMock(side_effect=download))
    monkeypatch.setattr(task, "storage_fs", storage)
    result = {
        "full_text": "Atención en Bogotá",
        "docling_metadata": {"processor": "abera-local"},
        "chunks": [
            {
                "chunk_text": "Atención en Bogotá",
                "contextualized_text": "Documento: catálogo\nAtención en Bogotá",
                "chunk_index": 0,
                "token_count": 6,
            }
        ],
    }
    parser = AsyncMock(return_value=result)
    monkeypatch.setattr(task, "process_document_in_queue", parser)
    return SimpleNamespace(
        client=client, storage=storage, parser=parser, document=document
    )


@pytest.mark.asyncio
async def test_rejects_other_tenant_before_downloading_or_writing(local_task):
    local_task.client.get_document_by_id.return_value = None
    with pytest.raises(ValueError, match="organización"):
        await task.process_knowledge_base_document(
            {"redis": AsyncMock()}, 11, KEY, 91, "u"
        )
    local_task.storage.adownload_file.assert_not_awaited()
    local_task.client.update_document_status.assert_not_awaited()
    local_task.client.get_document_by_id.assert_awaited_once_with(
        11, organization_id=91
    )


@pytest.mark.asyncio
async def test_rejects_forged_queue_object_key(local_task):
    with pytest.raises(ValueError, match="organización"):
        await task.process_knowledge_base_document(
            {"redis": AsyncMock()}, 11, KEY.replace("/42/", "/91/"), 42, "u"
        )
    local_task.storage.adownload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_document_needs_no_ai_and_keeps_existing_interface(
    local_task, monkeypatch
):
    embed = AsyncMock(side_effect=AssertionError("Full document must not call AI"))
    monkeypatch.setattr(task, "build_embedding_service", embed)
    await task.process_knowledge_base_document(
        {"redis": AsyncMock()}, 11, KEY, 42, "u", retrieval_mode="full_document"
    )
    local_task.client.update_document_full_text.assert_awaited_once_with(
        11, "Atención en Bogotá"
    )
    assert local_task.client.update_document_status.call_args.args == (11, "completed")
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_embedding_preserves_previous_live_chunks(local_task, monkeypatch):
    from api.services.configuration import ai_model_configuration as configuration

    monkeypatch.setattr(
        configuration,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(
                    embeddings=SimpleNamespace(
                        provider="openai",
                        api_key="test-key",
                        model="text-embedding-3-small",
                    )
                )
            )
        ),
    )
    service = SimpleNamespace(
        get_model_id=lambda: "text-embedding-3-small",
        get_embedding_dimension=lambda: 1536,
        embed_texts=AsyncMock(side_effect=ValueError("provider rejected request")),
    )
    monkeypatch.setattr(
        task, "build_embedding_service", AsyncMock(return_value=service)
    )
    with pytest.raises(ValueError, match="provider rejected"):
        await task.process_knowledge_base_document(
            {"redis": AsyncMock()}, 11, KEY, 42, "u"
        )
    local_task.client.replace_chunks_for_document.assert_not_awaited()
    assert local_task.client.update_document_status.call_args.args == (11, "failed")


@pytest.mark.asyncio
async def test_vector_index_writes_only_after_all_embeddings_succeed(
    local_task, monkeypatch
):
    from api.services.configuration import ai_model_configuration as configuration

    monkeypatch.setattr(
        configuration,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(
                    embeddings=SimpleNamespace(
                        provider="openai",
                        api_key="test-key",
                        model="text-embedding-3-small",
                    )
                )
            )
        ),
    )
    service = SimpleNamespace(
        get_model_id=lambda: "text-embedding-3-small",
        get_embedding_dimension=lambda: 1536,
        embed_texts=AsyncMock(return_value=[[0.0] * 1536]),
    )
    monkeypatch.setattr(
        task, "build_embedding_service", AsyncMock(return_value=service)
    )
    await task.process_knowledge_base_document({"redis": AsyncMock()}, 11, KEY, 42, "u")
    written = local_task.client.replace_chunks_for_document.call_args.kwargs
    assert written["organization_id"] == 42 and written["document_id"] == 11
    assert written["chunks"][0].embedding == [0.0] * 1536
    assert written["chunks"][0].organization_id == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", [KEY.replace("/42/", "/91/"), KEY.replace("catálogo.txt", "../catálogo.txt")]
)
async def test_api_rejects_foreign_or_forged_key_before_database_write(
    key, monkeypatch
):
    create = AsyncMock(side_effect=AssertionError("must not create a row"))
    monkeypatch.setattr(routes.db_client, "create_document", create)
    with pytest.raises(HTTPException) as error:
        await routes.process_document(
            ProcessDocumentRequestSchema(document_uuid=DOCUMENT_UUID, s3_key=key),
            user=SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 403
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_document_upload_uses_the_existing_quota_proxy(monkeypatch):
    from api import constants
    from api.services.abera import storage_upload

    monkeypatch.setattr(constants, "DEPLOYMENT_MODE", "abera")
    ticket = AsyncMock(return_value="https://example.com/api/v1/s3/managed-upload/test")
    monkeypatch.setattr(storage_upload, "create_upload_url", ticket)
    direct_upload = AsyncMock(side_effect=AssertionError("must not bypass quota"))
    monkeypatch.setattr(routes.storage_fs, "aget_presigned_put_url", direct_upload)
    request = DocumentUploadRequestSchema(
        filename="catálogo.txt", mime_type="text/plain", file_size_bytes=123
    )
    result = await routes.get_upload_url(
        request, user=SimpleNamespace(id=1, selected_organization_id=42)
    )
    assert result.upload_url.endswith("/managed-upload/test")
    assert ticket.call_args.args == (result.s3_key, 123, "text/plain")
    direct_upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_without_embedding_key_explains_configuration_before_any_provider_call(
    monkeypatch,
):
    from api.services import gen_ai
    from api.services.configuration import ai_model_configuration as configuration

    monkeypatch.setattr(
        configuration,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(embeddings=None),
            )
        ),
    )
    create = AsyncMock(side_effect=AssertionError("must not contact a provider"))
    monkeypatch.setattr(gen_ai, "build_embedding_service", create)
    with pytest.raises(HTTPException) as error:
        await routes.search_chunks(
            ChunkSearchRequestSchema(query="entregas"),
            user=SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 422 and "Modelos" in error.value.detail
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_with_legacy_mps_config_keeps_clear_disabled_error(monkeypatch):
    from api import constants
    from api.services.configuration import ai_model_configuration as configuration
    from api.services.model_services.policy import MPSDisabledError

    monkeypatch.setattr(constants, "ENABLE_DOGRAH_MPS", False)
    monkeypatch.setattr(
        configuration,
        "get_resolved_ai_model_configuration",
        AsyncMock(
            return_value=SimpleNamespace(
                effective=SimpleNamespace(
                    embeddings=SimpleNamespace(
                        provider="dograh",
                        api_key="old-key",
                        model="text-embedding-3-small",
                    )
                ),
            )
        ),
    )
    with pytest.raises(MPSDisabledError):
        await routes.search_chunks(
            ChunkSearchRequestSchema(query="entregas"),
            user=SimpleNamespace(selected_organization_id=42),
        )
