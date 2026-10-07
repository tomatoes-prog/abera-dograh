"""Single-use, size-bounded uploads that preserve the existing browser PUT flow."""

import json
import os
import tempfile
import uuid

from fastapi import HTTPException, Request

from api.services.storage import storage_fs
from api.tasks.arq import get_arq_redis
from api.utils.common import get_backend_endpoints


async def create_upload_url(key: str, size: int, content_type: str) -> str:
    redis = await get_arq_redis()
    token = uuid.uuid4().hex
    await redis.set(
        "storage-upload:" + token,
        json.dumps({"key": key, "size": size, "content_type": content_type}),
        ex=900,
        nx=True,
    )
    origin, _ = await get_backend_endpoints()
    return f"{origin}/api/v1/s3/managed-upload/{token}"


async def receive_upload(token: str, request: Request):
    if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(404, "Upload not found")
    redis = await get_arq_redis()
    # Redeem before reading bytes: replays and competing uploads are rejected.
    raw = await redis.getdel("storage-upload:" + token)
    if raw is None:
        raise HTTPException(410, "Upload expired or already used")
    grant = json.loads(raw)
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != grant["content_type"]
    ):
        raise HTTPException(400, "Unexpected content type")
    with tempfile.NamedTemporaryFile(delete=False) as output:
        path = output.name
    try:
        received = 0
        with open(path, "wb") as output:
            async for chunk in request.stream():
                received += len(chunk)
                if received > grant["size"]:
                    raise HTTPException(413, "Upload exceeds the authorized size")
                output.write(chunk)
        if received != grant["size"]:
            raise HTTPException(400, "Upload size does not match the authorized size")
        if not await storage_fs.aupload_file(path, grant["key"]):
            raise HTTPException(503, "Could not store upload")
    finally:
        os.unlink(path)
