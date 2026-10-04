from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from api.services.filesystem.quota import StorageQuotaExceeded
from api.services.filesystem.s3 import S3FileSystem


def fs_with_client(monkeypatch, *, used=90, previous=0):
    fs = S3FileSystem("private", key_prefix="subscriptions/one", storage_limit_bytes=100)
    client = SimpleNamespace(put_object=AsyncMock(), upload_file=AsyncMock(), copy_object=AsyncMock())

    async def pages(**kwargs):
        assert kwargs["Prefix"] == "subscriptions/one/"
        yield {"Contents": [{"Size": used}]}

    client.get_paginator = Mock(return_value=SimpleNamespace(paginate=pages))
    if previous:
        client.head_object = AsyncMock(return_value={"ContentLength": previous})
    else:
        client.head_object = AsyncMock(side_effect=ClientError({"Error": {"Code": "404"}}, "HeadObject"))

    @asynccontextmanager
    async def factory(*args, **kwargs):
        yield client

    @asynccontextmanager
    async def lock(*args):
        yield

    monkeypatch.setattr(fs.session, "client", factory)
    monkeypatch.setattr("api.services.filesystem.s3.storage_write_lock", lock)
    return fs, client


async def test_quota_rejects_before_put(monkeypatch):
    fs, client = fs_with_client(monkeypatch)
    with pytest.raises(StorageQuotaExceeded):
        await fs.acreate_file("recordings/1.wav", SimpleNamespace(read=AsyncMock(return_value=b"x" * 11)))
    client.put_object.assert_not_awaited()


async def test_replacement_counts_only_growth(monkeypatch):
    fs, client = fs_with_client(monkeypatch, previous=20)
    assert await fs.acreate_file("recordings/1.wav", SimpleNamespace(read=AsyncMock(return_value=b"x" * 30)))
    assert client.put_object.await_args.kwargs["Key"] == "subscriptions/one/recordings/1.wav"


async def test_file_upload_obeys_quota(monkeypatch, tmp_path):
    fs, client = fs_with_client(monkeypatch)
    path = tmp_path / "recording.wav"
    path.write_bytes(b"x" * 11)
    with pytest.raises(StorageQuotaExceeded):
        await fs.aupload_file(str(path), "recordings/1.wav")
    client.upload_file.assert_not_awaited()


async def test_copy_obeys_quota(monkeypatch):
    fs, client = fs_with_client(monkeypatch)
    client.head_object.side_effect = [{"ContentLength": 20}, ClientError({"Error": {"Code": "404"}}, "HeadObject")]
    with pytest.raises(StorageQuotaExceeded):
        await fs.acopy_file("source.wav", "copy.wav")
    client.copy_object.assert_not_awaited()


async def test_managed_presign_cannot_bypass_quota(monkeypatch):
    fs, _ = fs_with_client(monkeypatch)
    with pytest.raises(ValueError, match="quota-controlled"):
        await fs.aget_presigned_put_url("campaigns/1/a.csv")


@pytest.mark.parametrize("advertised,parts,expected", [
    (4, [b"data", b""], True),
    (500, [b"data", b""], False),
    (4, [b"data", b"extra", b""], False),
])
async def test_bounded_download_enforces_header_and_actual_bytes(monkeypatch, tmp_path, advertised, parts, expected):
    fs, client = fs_with_client(monkeypatch)
    body = AsyncMock()
    body.__aenter__.return_value = body
    body.read.side_effect = parts
    client.get_object = AsyncMock(return_value={"ContentLength": advertised, "Body": body})
    path = tmp_path / "document.txt"
    if expected:
        assert await fs.adownload_file("knowledge_base/1/example.txt", str(path), max_size=4)
        assert path.read_bytes() == b"data"
    else:
        with pytest.raises(ValueError, match="supera"):
            await fs.adownload_file("knowledge_base/1/example.txt", str(path), max_size=4)
    body.__aexit__.assert_awaited_once()


async def test_quota_store_failure_prevents_writes(monkeypatch):
    from api.services.filesystem.quota import StorageQuotaUnavailable, storage_write_lock
    fs, client = fs_with_client(monkeypatch)
    monkeypatch.setattr("api.services.filesystem.s3.storage_write_lock", storage_write_lock)
    monkeypatch.setattr("api.tasks.arq.get_arq_redis", AsyncMock(side_effect=ConnectionError("offline")))
    with pytest.raises(StorageQuotaUnavailable):
        await fs.acreate_file("a.txt", SimpleNamespace(read=AsyncMock(return_value=b"a")))
    client.put_object.assert_not_awaited()


async def test_competing_writes_cannot_exceed_subscription_budget(monkeypatch):
    import asyncio
    from api.services.filesystem.quota import storage_write_lock
    from api.tasks.arq import get_arq_redis
    fs, client = fs_with_client(monkeypatch, used=0)
    objects = {}

    async def pages(**kwargs):
        yield {"Contents": [{"Size": len(value)} for value in objects.values()]}

    async def put(**kwargs):
        await asyncio.sleep(0.05)
        objects[kwargs["Key"]] = kwargs["Body"]

    client.get_paginator = Mock(return_value=SimpleNamespace(paginate=pages))
    client.put_object.side_effect = put
    monkeypatch.setattr("api.services.filesystem.s3.storage_write_lock", storage_write_lock)
    results = await asyncio.gather(*(
        fs.acreate_file(f"{index}.txt", SimpleNamespace(read=AsyncMock(return_value=b"a" * 60)))
        for index in range(2)
    ), return_exceptions=True)
    assert sum(result is True for result in results) == 1
    assert sum(isinstance(result, StorageQuotaExceeded) for result in results) == 1
    assert sum(map(len, objects.values())) == 60


@pytest.mark.parametrize("key", ["transcripts/999.txt", "recordings/999/user.wav", "campaigns/2/a.csv", "voicemail_detections/a.wav"])
async def test_foreign_metadata_never_reaches_storage(monkeypatch, key):
    from api.routes import s3_signed_url as route
    monkeypatch.setattr(route.db_client, "get_workflow_run", AsyncMock(return_value=None))
    store = SimpleNamespace(aget_file_metadata=AsyncMock())
    monkeypatch.setattr(route, "storage_fs", store)
    with pytest.raises(HTTPException) as error:
        await route.get_file_metadata(key, SimpleNamespace(is_superuser=False, selected_organization_id=1))
    assert error.value.status_code == 403
    store.aget_file_metadata.assert_not_awaited()


async def test_upload_token_is_consumed_and_size_enforced(monkeypatch):
    import json
    from api.services.abera import storage_upload as service
    redis = SimpleNamespace(getdel=AsyncMock(side_effect=[json.dumps({"key": "campaigns/1/a.csv", "size": 2, "content_type": "text/csv"}), None]))
    monkeypatch.setattr(service, "get_arq_redis", AsyncMock(return_value=redis))
    store = SimpleNamespace(aupload_file=AsyncMock())
    monkeypatch.setattr(service, "storage_fs", store)

    async def chunks():
        yield b"abc"

    request = SimpleNamespace(headers={"content-type": "text/csv"}, stream=chunks)
    with pytest.raises(HTTPException) as error:
        await service.receive_upload("a" * 32, request)
    assert error.value.status_code == 413
    store.aupload_file.assert_not_awaited()
    with pytest.raises(HTTPException) as error:
        await service.receive_upload("a" * 32, request)
    assert error.value.status_code == 410
