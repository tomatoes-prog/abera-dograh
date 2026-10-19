"""Organization-scoped durable cleanup, independent of Redis job delivery."""

import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from api.db.base_client import BaseDBClient
from api.db.models import (
    KnowledgeBaseChunkModel,
    KnowledgeBaseDocumentModel,
    KnowledgeBaseStorageObjectModel,
    OrganizationModel,
)


class DocumentUploadExpired(ValueError):
    pass


def storage_object_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def validate_document_object(
    key: str, organization_id: int, document_uuid: str
) -> None:
    canonical = str(uuid.UUID(document_uuid))
    prefix = f"knowledge_base/{organization_id}/{canonical}/"
    filename = key.removeprefix(prefix)
    if (
        not key.startswith(prefix)
        or not filename
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise ValueError("El archivo no pertenece a esta organización.")


class KnowledgeBaseStorageClient(BaseDBClient):
    async def discover_document_object(
        self,
        organization_id: int,
        document_uuid: str,
        object_key: str,
        modified_at=None,
    ) -> bool:
        """Register historical/late objects without authorizing unknown tenants."""
        validate_document_object(object_key, organization_id, document_uuid)
        async with self.async_session() as session:
            if not await session.get(OrganizationModel, organization_id):
                return False
            document = await session.scalar(
                select(KnowledgeBaseDocumentModel).where(
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                )
            )
            item = await session.get(
                KnowledgeBaseStorageObjectModel,
                storage_object_id(object_key),
                with_for_update=True,
            )
            if (
                modified_at is not None
                and modified_at > datetime.now(UTC) - timedelta(hours=2)
                and (item is None or item.state != "purged")
            ):
                return True
            if item is None:
                active = document is not None and document.is_active
                item = KnowledgeBaseStorageObjectModel(
                    id=storage_object_id(object_key),
                    organization_id=organization_id,
                    document_uuid=document_uuid,
                    object_key=object_key,
                    state="attached" if active else "deleting",
                    delete_after=None if active else datetime.now(UTC),
                )
                session.add(item)
            elif item.state == "purged":
                # A timed-out old writer cannot escape its durable tombstone.
                item.state, item.object_key, item.delete_after = (
                    "deleting",
                    object_key,
                    datetime.now(UTC),
                )
            await session.commit()
            return True

    @asynccontextmanager
    async def document_content_write_guard(
        self, document_id: int, organization_id: int
    ):
        """Serialize a storage writer with deletion of the same document."""
        async with self.async_session() as session:
            document = await session.scalar(
                select(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.id == document_id,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active.is_(True),
                )
                .with_for_update()
            )
            if not document:
                raise DocumentUploadExpired("El documento ya fue eliminado.")
            yield
            await session.commit()

    async def register_document_upload(
        self, organization_id: int, document_uuid: str, object_key: str
    ) -> None:
        validate_document_object(object_key, organization_id, document_uuid)
        async with self.async_session() as session:
            item = await session.get(
                KnowledgeBaseStorageObjectModel,
                storage_object_id(object_key),
                with_for_update=True,
            )
            if item and (
                item.organization_id != organization_id
                or item.state in {"deleting", "purged"}
            ):
                raise DocumentUploadExpired(
                    "La carga venció; selecciona el archivo de nuevo."
                )
            if not item:
                session.add(
                    KnowledgeBaseStorageObjectModel(
                        id=storage_object_id(object_key),
                        organization_id=organization_id,
                        document_uuid=document_uuid,
                        object_key=object_key,
                        state="awaiting",
                        delete_after=datetime.now(UTC) + timedelta(hours=2),
                    )
                )
            await session.commit()

    async def _attach_document_object(
        self, session, organization_id: int, document_uuid: str, object_key: str
    ) -> None:
        validate_document_object(object_key, organization_id, document_uuid)
        item = await session.get(
            KnowledgeBaseStorageObjectModel,
            storage_object_id(object_key),
            with_for_update=True,
        )
        if item:
            if (
                item.organization_id != organization_id
                or item.state in {"deleting", "purged"}
                or (item.state == "awaiting" and item.delete_after <= datetime.now(UTC))
            ):
                raise DocumentUploadExpired(
                    "La carga venció; selecciona el archivo de nuevo."
                )
            item.state, item.delete_after = "attached", None
        else:
            # An upload signed immediately before the migration can still finish.
            session.add(
                KnowledgeBaseStorageObjectModel(
                    id=storage_object_id(object_key),
                    organization_id=organization_id,
                    document_uuid=document_uuid,
                    object_key=object_key,
                    state="attached",
                )
            )

    async def claim_document_cleanup(self, limit: int = 50) -> list[dict]:
        """A persisted claim fences late processing and survives a worker crash."""
        now = datetime.now(UTC)
        async with self.async_session() as session:
            items = list(
                (
                    await session.execute(
                        select(KnowledgeBaseStorageObjectModel)
                        .where(
                            KnowledgeBaseStorageObjectModel.state.in_(
                                ("awaiting", "deleting")
                            ),
                            KnowledgeBaseStorageObjectModel.delete_after <= now,
                        )
                        .order_by(KnowledgeBaseStorageObjectModel.delete_after)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars()
            )
            result = []
            for item in items:
                active = await session.scalar(
                    select(KnowledgeBaseDocumentModel.id).where(
                        KnowledgeBaseDocumentModel.organization_id
                        == item.organization_id,
                        KnowledgeBaseDocumentModel.document_uuid == item.document_uuid,
                        KnowledgeBaseDocumentModel.is_active.is_(True),
                    )
                )
                if active:
                    item.state, item.delete_after = "attached", None
                    continue
                item.state = "deleting"
                item.attempts += 1
                # A crashed claim is retried; another worker cannot race this one.
                item.delete_after = now + timedelta(minutes=10)
                result.append(
                    {
                        "id": item.id,
                        "organization_id": item.organization_id,
                        "document_uuid": item.document_uuid,
                        "object_key": item.object_key,
                    }
                )
            await session.commit()
            return result

    async def finish_document_cleanup(
        self, item_id: str, organization_id: int, *, success: bool
    ) -> None:
        async with self.async_session() as session:
            document_uuid = await session.scalar(
                select(KnowledgeBaseStorageObjectModel.document_uuid).where(
                    KnowledgeBaseStorageObjectModel.id == item_id,
                    KnowledgeBaseStorageObjectModel.organization_id == organization_id,
                    KnowledgeBaseStorageObjectModel.state == "deleting",
                )
            )
            if not document_uuid:
                return
            # Match delete_document's lock order: document, then its intents.
            # A retried DELETE must not deadlock the cleanup acknowledgement.
            document = await session.scalar(
                select(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                    KnowledgeBaseDocumentModel.is_active.is_(False),
                )
                .with_for_update()
            )
            item = await session.scalar(
                select(KnowledgeBaseStorageObjectModel)
                .where(
                    KnowledgeBaseStorageObjectModel.id == item_id,
                    KnowledgeBaseStorageObjectModel.organization_id == organization_id,
                    KnowledgeBaseStorageObjectModel.state == "deleting",
                )
                .with_for_update()
            )
            if not item:
                return
            if success:
                item.state, item.purged_at, item.last_error = (
                    "purged",
                    datetime.now(UTC),
                    None,
                )
                item.object_key, item.delete_after = "", None
                if document:
                    await session.execute(
                        delete(KnowledgeBaseChunkModel).where(
                            KnowledgeBaseChunkModel.organization_id == organization_id,
                            KnowledgeBaseChunkModel.document_id == document.id,
                        )
                    )
                    document.full_text, document.total_chunks = None, 0
                    document.filename, document.file_hash, document.source_url = (
                        "Documento eliminado",
                        None,
                        None,
                    )
                    document.custom_metadata, document.docling_metadata = {}, {}
                    document.processing_error = None
            else:
                item.last_error = "STORAGE_CLEANUP_UNVERIFIED"
            await session.commit()
