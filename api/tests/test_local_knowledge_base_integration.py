"""A real PostgreSQL/pgvector round trip, with local parsing and fake embeddings."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.gen_ai.embedding.openai_service import OpenAIEmbeddingService
from api.services.workflow.tools import knowledge_base as retrieval
from api.tasks import knowledge_base_processing as task


@pytest.mark.asyncio
async def test_ingest_both_modes_and_retrieve_without_crossing_tenants(
    db_session, monkeypatch, tmp_path
):
    from api.services.configuration import ai_model_configuration as configuration

    monkeypatch.setattr(task, "db_client", db_session)
    monkeypatch.setattr(retrieval, "db_client", db_session)
    monkeypatch.setattr(retrieval, "ensure_tracing", lambda: False)
    vector = [0.1] * 1536
    reader_files = {}

    async def download(key, path, *, max_size):
        with open(path, "w", encoding="utf-8") as destination:
            destination.write(reader_files[key])
        return True

    monkeypatch.setattr(task, "storage_fs", SimpleNamespace(adownload_file=download))

    class FakeEmbeddingService(OpenAIEmbeddingService):
        async def embed_texts(self, texts):
            return [vector[:] for _text in texts]

        async def embed_text(self, text):
            return vector[:]

    embedding_service = FakeEmbeddingService(db_client=db_session, api_key="test-key")
    monkeypatch.setattr(
        task, "build_embedding_service", AsyncMock(return_value=embedding_service)
    )
    monkeypatch.setattr(
        retrieval, "build_embedding_service", AsyncMock(return_value=embedding_service)
    )
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
                ),
            )
        ),
    )

    # Exercise the actual bounded reader without consuming an ARQ lease shared
    # with other tests; the distributed lease is covered by its dedicated tests.
    from api.services.knowledge_base.processing import process_document_locally

    async def parse(*, redis, **arguments):
        return await process_document_locally(**arguments)

    monkeypatch.setattr(task, "process_document_in_queue", parse)

    documents = []
    organizations = []
    for index, (mode, text) in enumerate(
        [
            ("full_document", "Café colombiano: precio 25.000 COP."),
            ("chunked", "Entregas a Bogotá en dos días hábiles."),
            ("chunked", "SECRETO DE OTRA CUENTA: ventas y contactos privados."),
        ]
    ):
        if index in {0, 2}:
            user, _ = await db_session.get_or_create_user_by_provider_id(
                "local-kb-user-" + uuid.uuid4().hex
            )
            (
                organization,
                _,
            ) = await db_session.get_or_create_organization_by_provider_id(
                "local-kb-org-" + uuid.uuid4().hex, user.id
            )
            organizations.append(organization.id)
        identifier = str(uuid.uuid4())
        key = f"knowledge_base/{organization.id}/{identifier}/document-{index}.txt"
        reader_files[key] = text
        document = await db_session.create_document(
            organization_id=organization.id,
            created_by=user.id,
            document_uuid=identifier,
            filename=f"document-{index}.txt",
            file_size_bytes=0,
            file_hash="",
            mime_type="text/plain",
            custom_metadata={"s3_key": key},
            retrieval_mode=mode,
        )
        await task.process_knowledge_base_document(
            {"redis": None},
            document.id,
            key,
            organization.id,
            user.provider_id,
            retrieval_mode=mode,
        )
        documents.append(
            await db_session.get_document_by_id(
                document.id, organization_id=organization.id
            )
        )
    assert all(document.processing_status == "completed" for document in documents)

    full = await retrieval.retrieve_from_knowledge_base(
        query="¿Cuánto cuesta el café?",
        organization_id=organizations[0],
        document_uuids=[documents[0].document_uuid],
    )
    assert full["total_results"] == 1 and "25.000 COP" in full["chunks"][0]["text"]
    retrieval.build_embedding_service.assert_not_awaited()

    indexed = await retrieval.retrieve_from_knowledge_base(
        query="¿Cuándo llega mi pedido?",
        organization_id=organizations[0],
        document_uuids=[documents[1].document_uuid],
        embeddings_api_key="test-key",
        embeddings_provider="openai",
    )
    assert indexed["total_results"] == 1
    assert "Bogotá" in indexed["chunks"][0]["text"]
    # Both tenants have identical vectors. The SQL tenant filter, not vector
    # distance, must stop the other account's document from appearing.
    all_own = await retrieval.retrieve_from_knowledge_base(
        query="ventas",
        organization_id=organizations[0],
        embeddings_api_key="test-key",
        embeddings_provider="openai",
    )
    assert all_own["total_results"] >= 1
    assert "SECRETO" not in str(all_own)
