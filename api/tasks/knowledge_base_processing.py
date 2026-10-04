"""ARQ background task for processing knowledge base documents.

Document conversion and chunking run locally in a bounded subprocess. Only
embedding requests use the organization's explicitly configured provider.
"""

import os
import tempfile

from loguru import logger
from arq import Retry

from api.db import db_client
from api.db.models import KnowledgeBaseChunkModel
from api.services.gen_ai import build_embedding_service
from api.services.knowledge_base.processing import (
    MAX_FILE_SIZE_BYTES,
    process_document_in_queue,
)
from api.services.storage import storage_fs

EMBEDDING_BATCH_SIZE = 64


async def _embed_texts_in_batches(
    embedding_service,
    texts: list[str],
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> list[list[float]]:
    """Generate embeddings in bounded batches for provider stability."""
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        logger.info(
            f"Generating embedding batch {start // batch_size + 1} ({len(batch)} texts)"
        )
        embeddings.extend(await embedding_service.embed_texts(batch))
    return embeddings


async def process_knowledge_base_document(
    ctx,
    document_id: int,
    s3_key: str,
    organization_id: int,
    created_by_provider_id: str,
    max_tokens: int = 128,
    retrieval_mode: str = "chunked",
):
    """Download, extract locally, embed if needed, and atomically replace chunks.

    Args:
        ctx: ARQ context
        document_id: Database ID of the document
        s3_key: S3 key where the file is stored
        organization_id: Organization ID
        created_by_provider_id: Uploading user's provider ID (kept for queued-job compatibility)
        max_tokens: Maximum number of tokens per chunk (default: 128)
        retrieval_mode: "chunked" for vector search or "full_document" for full text
    """
    logger.info(
        f"Processing knowledge base document: document_id={document_id}, "
        f"s3_key={s3_key}, org={organization_id}, mode={retrieval_mode}"
    )

    temp_file_path = None
    document = await db_client.get_document_by_id(
        document_id, organization_id=organization_id,
    )
    if (
        not document
        or (document.custom_metadata or {}).get("s3_key") != s3_key
        or not s3_key.startswith(f"knowledge_base/{organization_id}/{document.document_uuid}/")
    ):
        # Do not download, parse, or update a document owned by another tenant.
        raise ValueError("El documento no pertenece a esta organización.")

    try:
        await db_client.update_document_status(document_id, "processing")

        filename = document.filename
        file_extension = os.path.splitext(filename)[1] or ".bin"

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_file_path = temp_file.name
        temp_file.close()

        logger.info(f"Downloading file from S3: {s3_key}")
        download_success = await storage_fs.adownload_file(s3_key, temp_file_path, max_size=MAX_FILE_SIZE_BYTES)
        if not download_success:
            raise Exception(f"Failed to download file from S3: {s3_key}")
        if not os.path.exists(temp_file_path):
            raise FileNotFoundError(f"Downloaded file not found: {temp_file_path}")

        file_size = os.path.getsize(temp_file_path)
        logger.info(f"Downloaded file size: {file_size} bytes")

        if file_size > MAX_FILE_SIZE_BYTES:
            error_message = (
                f"File size ({file_size / (1024 * 1024):.1f}MB) exceeds the "
                f"maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            )
            logger.warning(f"Document {document_id}: {error_message}")
            await db_client.update_document_status(
                document_id, "failed", error_message=error_message
            )
            return

        file_hash = db_client.compute_file_hash(temp_file_path)
        mime_type = db_client.get_mime_type(temp_file_path)

        # Reject duplicates (same hash already ingested for this org).
        existing_doc = await db_client.get_document_by_hash(file_hash, organization_id)
        if existing_doc and existing_doc.id != document_id:
            error_message = (
                f"This content is identical to '{existing_doc.filename}'. "
                f"Keep only one copy of it in the knowledge base."
            )
            logger.warning(
                f"Duplicate document detected: {document_id} is duplicate of "
                f"{existing_doc.id} ({existing_doc.filename})"
            )
            await db_client.update_document_metadata(
                document_id,
                file_size_bytes=file_size,
                file_hash=file_hash,
                mime_type=mime_type,
            )
            await db_client.update_document_status(
                document_id,
                "failed",
                error_message=error_message,
                docling_metadata={
                    "duplicate_of": existing_doc.document_uuid,
                    "duplicate_filename": existing_doc.filename,
                },
            )
            return

        await db_client.update_document_metadata(
            document_id,
            file_size_bytes=file_size,
            file_hash=file_hash,
            mime_type=mime_type,
        )

        embeddings_provider = None
        embeddings_api_key = None
        embeddings_model = None
        embeddings_base_url = None
        embeddings_endpoint = None
        embeddings_api_version = None
        if retrieval_mode == "chunked":
            from api.services.configuration.ai_model_configuration import (
                apply_managed_embeddings_base_url,
                get_resolved_ai_model_configuration,
            )

            resolved_config = await get_resolved_ai_model_configuration(
                organization_id=document.organization_id,
            )
            effective_config = resolved_config.effective
            if effective_config.embeddings:
                embeddings_provider = getattr(
                    effective_config.embeddings, "provider", None
                )
                embeddings_api_key = effective_config.embeddings.api_key
                embeddings_model = effective_config.embeddings.model
                embeddings_base_url = apply_managed_embeddings_base_url(
                    provider=embeddings_provider,
                    base_url=getattr(effective_config.embeddings, "base_url", None),
                )
                embeddings_endpoint = getattr(
                    effective_config.embeddings, "endpoint", None
                )
                embeddings_api_version = getattr(
                    effective_config.embeddings, "api_version", None
                )
                logger.info(
                    f"Using user embeddings config: provider={embeddings_provider}, "
                    f"model={embeddings_model}"
                )

        logger.info(f"Processing document locally (mode={retrieval_mode})")
        processing_result = await process_document_in_queue(
            redis=ctx["redis"],
            file_path=temp_file_path,
            filename=filename,
            retrieval_mode=retrieval_mode,
            max_tokens=max_tokens,
        )

        docling_metadata = processing_result.get("docling_metadata", {})

        if retrieval_mode == "full_document":
            full_text = processing_result.get("full_text") or ""
            await db_client.update_document_full_text(document_id, full_text)
            await db_client.update_document_status(
                document_id,
                "completed",
                total_chunks=0,
                docling_metadata=docling_metadata,
            )
            logger.info(
                f"Successfully processed full_document {document_id}. "
                f"Text length: {len(full_text)} chars"
            )
            return

        if not embeddings_api_key:
            error_message = (
                "Configura una API key de embeddings en Modelos para procesar "
                "el documento por fragmentos. También puedes usar documento completo."
            )
            logger.warning(f"Document {document_id}: {error_message}")
            await db_client.update_document_status(
                document_id, "failed", error_message=error_message
            )
            return

        embedding_service = await build_embedding_service(
            db_client=db_client,
            provider=embeddings_provider,
            api_key=embeddings_api_key,
            model=embeddings_model,
            base_url=embeddings_base_url,
            endpoint=embeddings_endpoint,
            api_version=embeddings_api_version,
            resolve_correlation=False,
        )

        extracted_chunks = processing_result.get("chunks", [])
        if not extracted_chunks:
            raise ValueError("No se encontraron fragmentos de texto para indexar.")

        chunk_records = []
        chunk_texts = []
        for chunk in extracted_chunks:
            contextualized = chunk.get("contextualized_text") or chunk["chunk_text"]
            chunk_records.append(
                KnowledgeBaseChunkModel(
                    document_id=document_id,
                    organization_id=organization_id,
                    chunk_text=chunk["chunk_text"],
                    contextualized_text=contextualized,
                    chunk_index=chunk["chunk_index"],
                    chunk_metadata=chunk.get("chunk_metadata") or {},
                    embedding_model=embedding_service.get_model_id(),
                    embedding_dimension=embedding_service.get_embedding_dimension(),
                    token_count=chunk.get("token_count", 0),
                )
            )
            chunk_texts.append(contextualized)

        logger.info(
            f"Generating embeddings for {len(chunk_texts)} chunks "
            f"using {embedding_service.get_model_id()}"
        )
        embeddings = await _embed_texts_in_batches(embedding_service, chunk_texts)
        if len(embeddings) != len(chunk_records):
            raise ValueError(
                "Embedding count mismatch: "
                f"expected {len(chunk_records)}, got {len(embeddings)}"
            )
        for chunk_record, embedding in zip(chunk_records, embeddings):
            chunk_record.embedding = embedding

        logger.info("Storing chunks in database")
        await db_client.replace_chunks_for_document(
            document_id=document_id,
            organization_id=organization_id,
            chunks=chunk_records,
        )

        await db_client.update_document_status(
            document_id,
            "completed",
            total_chunks=len(chunk_records),
            docling_metadata=docling_metadata,
        )

        logger.info(
            f"Successfully processed knowledge base document {document_id}. "
            f"Total chunks: {len(chunk_records)}"
        )

    except Retry:
        await db_client.update_document_status(document_id, "pending")
        raise
    except Exception as e:
        logger.exception(
            "Error processing knowledge base document {}: {}", document_id, e
        )
        await db_client.update_document_status(
            document_id, "failed", error_message=str(e)
        )
        raise

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_file_path}: {e}")
