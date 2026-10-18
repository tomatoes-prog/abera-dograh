"""Replay durable cleanup after Redis loss or a worker interruption."""

import json

from loguru import logger

from api.db import db_client
from api.db.knowledge_base_storage_client import validate_document_object
from api.services.storage import storage_fs


async def sweep_document_storage(ctx):
    # Redis stores only a resumable inventory cursor; deletion authority and
    # retries remain in PostgreSQL. Restarting a scan is safe and idempotent.
    redis = ctx.get("redis")
    cursor_key = "knowledge-base:storage-inventory"
    try:
        raw = await redis.get(cursor_key) if redis else None
        cursor = json.loads(raw) if raw else None
        rows, next_cursor = await storage_fs.alist_object_versions(
            "knowledge_base/", cursor
        )
        for row in rows:
            parts = row["key"].split("/")
            if (
                len(parts) != 4
                or parts[0] != "knowledge_base"
                or not parts[1].isdigit()
            ):
                logger.warning("Objeto de documentos con propietario no identificado")
                continue
            try:
                recognized = await db_client.discover_document_object(
                    int(parts[1]), parts[2], row["key"], row["modified_at"]
                )
            except ValueError:
                logger.warning("Objeto de documentos con identidad no verificable")
                continue
            if not recognized:
                logger.warning("Objeto de documentos sin organización vigente")
        if redis:
            if next_cursor:
                await redis.set(cursor_key, json.dumps(next_cursor))
            else:
                await redis.delete(cursor_key)
    except NotImplementedError:
        pass  # Non-versioned test/local adapters still replay durable intents.
    except Exception:  # noqa: BLE001 - Keep durable retries without exporting SDK bodies.
        logger.warning(
            "No se pudo completar el inventario de documentos; se reintentará"
        )
    for item in await db_client.claim_document_cleanup():
        success = False
        try:
            validate_document_object(
                item["object_key"], item["organization_id"], item["document_uuid"]
            )
            success = await storage_fs.adelete_file(item["object_key"])
        except Exception:  # noqa: BLE001 - Keep durable retries without exporting SDK bodies.
            # Persist a sanitized failure code; do not export SDK bodies/URLs.
            logger.warning(
                "No se pudo verificar la limpieza del archivo {}", item["id"]
            )
        await db_client.finish_document_cleanup(
            item["id"], item["organization_id"], success=success
        )
