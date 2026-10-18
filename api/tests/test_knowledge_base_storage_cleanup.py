"""A lost queue job or late worker must not leave tenant files behind."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import update

from api.db.knowledge_base_storage_client import (
    DocumentUploadExpired,
    storage_object_id,
)
from api.db.models import KnowledgeBaseChunkModel, KnowledgeBaseStorageObjectModel
from api.services.filesystem.local import LocalFileSystem
from api.services.filesystem.s3 import S3FileSystem
from api.tasks import knowledge_base_cleanup as cleanup


async def tenant(client):
    identifier = uuid.uuid4().hex
    user, _ = await client.get_or_create_user_by_provider_id(
        "cleanup-user-" + identifier
    )
    org, _ = await client.get_or_create_organization_by_provider_id(
        "cleanup-org-" + identifier, user.id
    )
    return user, org.id


async def document(client):
    user, org = await tenant(client)
    identifier = str(uuid.uuid4())
    key = f"knowledge_base/{org}/{identifier}/archivo.txt"
    await client.register_document_upload(org, identifier, key)
    doc = await client.create_document(
        organization_id=org,
        created_by=user.id,
        filename="archivo.txt",
        document_uuid=identifier,
        file_size_bytes=6,
        file_hash="hash",
        mime_type="text/plain",
        custom_metadata={"s3_key": key},
        retrieval_mode="full_document",
    )
    await client.update_document_full_text(doc.id, "privado")
    return doc, key


async def intent(client, key):
    async with client.async_session() as session:
        return await session.get(
            KnowledgeBaseStorageObjectModel, storage_object_id(key)
        )


async def expire(client, key):
    async with client.async_session() as session:
        await session.execute(
            update(KnowledgeBaseStorageObjectModel)
            .where(KnowledgeBaseStorageObjectModel.id == storage_object_id(key))
            .values(delete_after=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()


async def test_deleted_document_releases_local_bytes_and_cannot_be_resurrected(
    db_session, monkeypatch, tmp_path
):
    doc, key = await document(db_session)
    fs = LocalFileSystem(str(tmp_path))
    await fs.acreate_file_from_bytes(key, b"privado")
    assert await db_session.delete_document(doc.document_uuid, doc.organization_id)
    monkeypatch.setattr(cleanup, "db_client", db_session)
    monkeypatch.setattr(cleanup, "storage_fs", fs)
    await cleanup.sweep_document_storage({})
    assert not (tmp_path / key).exists()
    saved = await intent(db_session, key)
    assert saved.state == "purged" and saved.purged_at and saved.object_key == ""
    await db_session.update_document_full_text(doc.id, "late provider response")
    await db_session.update_document_status(doc.id, "completed", total_chunks=1)
    chunks = [
        KnowledgeBaseChunkModel(
            document_id=doc.id,
            organization_id=doc.organization_id,
            chunk_text="late",
            chunk_index=0,
            embedding=[0.0] * 1536,
        )
    ]
    assert (
        await db_session.replace_chunks_for_document(
            doc.id, doc.organization_id, chunks
        )
        == []
    )
    assert await db_session.get_chunks_for_document(doc.id, doc.organization_id) == []
    assert (
        await db_session.get_full_text_documents(
            doc.organization_id, [doc.document_uuid]
        )
        == []
    )
    with pytest.raises(DocumentUploadExpired):
        async with db_session.document_content_write_guard(doc.id, doc.organization_id):
            pytest.fail("A deleted document cannot admit a storage writer")


async def test_other_organization_cannot_delete_or_finish_cleanup(
    db_session, monkeypatch
):
    doc, key = await document(db_session)
    _, other_org = await tenant(db_session)
    assert not await db_session.delete_document(doc.document_uuid, other_org)
    assert await db_session.claim_document_cleanup() == []
    assert await db_session.delete_document(doc.document_uuid, doc.organization_id)
    (item,) = await db_session.claim_document_cleanup()
    await db_session.finish_document_cleanup(item["id"], other_org, success=True)
    assert (await intent(db_session, key)).state == "deleting"


async def test_abandoned_upload_is_durable_and_expired_processing_is_rejected(
    db_session, monkeypatch
):
    user, org = await tenant(db_session)
    identifier = str(uuid.uuid4())
    key = f"knowledge_base/{org}/{identifier}/abandonado.txt"
    await db_session.register_document_upload(org, identifier, key)
    assert await db_session.claim_document_cleanup() == []
    await expire(db_session, key)
    with pytest.raises(DocumentUploadExpired):
        await db_session.create_document(
            organization_id=org,
            created_by=user.id,
            filename="abandonado.txt",
            document_uuid=identifier,
            file_size_bytes=1,
            file_hash="",
            mime_type="text/plain",
            custom_metadata={"s3_key": key},
        )
    files = SimpleNamespace(adelete_file=AsyncMock(return_value=False))
    monkeypatch.setattr(cleanup, "db_client", db_session)
    monkeypatch.setattr(cleanup, "storage_fs", files)
    await cleanup.sweep_document_storage({})
    saved = await intent(db_session, key)
    assert (
        saved.state == "deleting" and saved.last_error == "STORAGE_CLEANUP_UNVERIFIED"
    )
    assert await db_session.claim_document_cleanup() == []
    await expire(db_session, key)
    files.adelete_file.return_value = True
    await cleanup.sweep_document_storage({})
    assert (await intent(db_session, key)).state == "purged"
    assert (await intent(db_session, key)).attempts == 2


async def test_active_document_survives_even_if_an_old_upload_deadline_is_due(
    db_session,
):
    doc, key = await document(db_session)
    async with db_session.async_session() as session:
        await session.execute(
            update(KnowledgeBaseStorageObjectModel)
            .where(KnowledgeBaseStorageObjectModel.id == storage_object_id(key))
            .values(state="awaiting", delete_after=datetime.now(UTC))
        )
        await session.commit()
    assert await db_session.claim_document_cleanup() == []
    assert (await intent(db_session, key)).state == "attached"
    assert await db_session.get_document_by_uuid(doc.document_uuid, doc.organization_id)


@pytest.mark.parametrize(
    "key", ["knowledge_base/999/no/archivo.txt", "../archivo.txt", "/archivo.txt"]
)
async def test_upload_intent_rejects_foreign_or_traversal_keys(db_session, key):
    _, org = await tenant(db_session)
    with pytest.raises(ValueError):
        await db_session.register_document_upload(org, str(uuid.uuid4()), key)


async def test_versioned_s3_deletion_erases_exact_versions_and_markers_only():
    fs = S3FileSystem("bucket", key_prefix="subscriptions/owned")
    key = fs._key("knowledge_base/1/doc/file.txt")
    versions = [
        {"Key": key, "VersionId": "v1"},
        {"Key": key + ".neighbor", "VersionId": "foreign"},
    ]
    markers = [{"Key": key, "VersionId": "marker"}]

    async def pages(**_):
        yield {"Versions": list(versions), "DeleteMarkers": list(markers)}

    client = Mock()
    client.get_paginator.return_value.paginate.side_effect = pages

    async def delete_version(**args):
        versions[:] = [
            x
            for x in versions
            if (x["Key"], x["VersionId"]) != (args["Key"], args["VersionId"])
        ]
        markers[:] = [
            x
            for x in markers
            if (x["Key"], x["VersionId"]) != (args["Key"], args["VersionId"])
        ]

    client.delete_object = AsyncMock(side_effect=delete_version)
    client.head_object = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "404"}}, "HeadObject")
    )
    context = AsyncMock()
    context.__aenter__.return_value = client
    fs.session = SimpleNamespace(client=lambda *_, **__: context)
    fs.aget_file_metadata = AsyncMock(return_value=None)
    assert await fs.adelete_file("knowledge_base/1/doc/file.txt")
    assert (
        versions == [{"Key": key + ".neighbor", "VersionId": "foreign"}]
        and markers == []
    )
    assert client.delete_object.await_count == 2


async def test_native_access_denial_cannot_confirm_file_absence():
    fs = S3FileSystem("bucket", key_prefix="subscriptions/owned")

    async def pages(**_):
        yield {"Versions": [], "DeleteMarkers": []}

    client = Mock()
    client.get_paginator.return_value.paginate.side_effect = pages
    client.head_object = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
    )
    context = AsyncMock()
    context.__aenter__.return_value = client
    fs.session = SimpleNamespace(client=lambda *_, **__: context)
    with pytest.raises(ClientError, match="AccessDenied"):
        await fs.adelete_file("knowledge_base/1/document/file.txt")


async def test_local_deletion_cannot_escape_its_root(tmp_path):
    with pytest.raises(ValueError):
        await LocalFileSystem(str(tmp_path)).adelete_file("../neighbor.txt")


async def test_native_inventory_recovers_legacy_and_late_files_without_queue_state(
    db_session, monkeypatch
):
    _, org = await tenant(db_session)
    key = f"knowledge_base/{org}/{uuid.uuid4()}/legacy.txt"
    storage = SimpleNamespace(
        alist_object_versions=AsyncMock(
            return_value=(
                [{"key": key, "modified_at": datetime.now(UTC) - timedelta(hours=3)}],
                None,
            )
        ),
        adelete_file=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(cleanup, "db_client", db_session)
    monkeypatch.setattr(cleanup, "storage_fs", storage)
    await cleanup.sweep_document_storage({})
    assert (await intent(db_session, key)).state == "purged"
    await cleanup.sweep_document_storage({})  # A late old writer uploaded again.
    assert (await intent(db_session, key)).state == "purged"
    assert (await intent(db_session, key)).attempts == 2


async def test_inventory_keeps_recent_uploads_and_active_documents(
    db_session, monkeypatch
):
    doc, key = await document(db_session)
    recent = f"knowledge_base/{doc.organization_id}/{uuid.uuid4()}/recent.txt"
    storage = SimpleNamespace(
        alist_object_versions=AsyncMock(
            return_value=(
                [
                    {"key": key, "modified_at": datetime.now(UTC) - timedelta(days=2)},
                    {"key": recent, "modified_at": datetime.now(UTC)},
                ],
                None,
            )
        ),
        adelete_file=AsyncMock(),
    )
    monkeypatch.setattr(cleanup, "db_client", db_session)
    monkeypatch.setattr(cleanup, "storage_fs", storage)
    await cleanup.sweep_document_storage({})
    storage.adelete_file.assert_not_awaited()
    assert (await intent(db_session, key)).state == "attached"
    assert await intent(db_session, recent) is None


@pytest.mark.parametrize(
    "cursor",
    [
        {"KeyMarker": "subscriptions/another/knowledge_base/file"},
        {
            "KeyMarker": "subscriptions/owned/knowledge_base/file",
            "Bucket": "foreign-bucket",
        },
    ],
)
async def test_inventory_cursor_cannot_change_bucket_or_subscription(cursor):
    fs = S3FileSystem("private", key_prefix="subscriptions/owned")
    with pytest.raises(ValueError):
        await fs.alist_object_versions("knowledge_base/", cursor)


async def test_delete_waits_for_a_storage_writer_from_another_database_session(
    test_engine,
):
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from api.db.db_client import DBClient
    from api.db.models import (
        KnowledgeBaseDocumentModel,
        OrganizationModel,
        UserModel,
        organization_users_association,
    )

    client = DBClient()
    await client.engine.dispose()
    client.engine = test_engine
    client.async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    doc, _key = await document(client)
    operation = None
    try:
        started = asyncio.Event()

        async def remove():
            started.set()
            return await client.delete_document(doc.document_uuid, doc.organization_id)

        async with client.document_content_write_guard(doc.id, doc.organization_id):
            operation = asyncio.create_task(remove())
            await started.wait()
            await asyncio.sleep(0.1)
            assert not operation.done(), (
                "Deletion must wait until the writer releases its document"
            )
        assert await asyncio.wait_for(operation, 5)
    finally:
        if operation is not None and not operation.done():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
        async with client.async_session() as session:
            await session.execute(
                delete(KnowledgeBaseStorageObjectModel).where(
                    KnowledgeBaseStorageObjectModel.organization_id
                    == doc.organization_id
                )
            )
            await session.execute(
                delete(KnowledgeBaseDocumentModel).where(
                    KnowledgeBaseDocumentModel.id == doc.id
                )
            )
            await session.execute(
                delete(organization_users_association).where(
                    organization_users_association.c.organization_id
                    == doc.organization_id
                )
            )
            await session.execute(
                delete(OrganizationModel).where(
                    OrganizationModel.id == doc.organization_id
                )
            )
            await session.execute(
                delete(UserModel).where(UserModel.id == doc.created_by)
            )
            await session.commit()
