"""Browser links must be signed for a reachable host without moving server I/O."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import aioboto3
import pytest

from api.services.filesystem.s3 import S3FileSystem


@pytest.fixture
def filesystem():
    fs = S3FileSystem(
        "private-documents",
        endpoint_url="http://storage.internal:9000",
        public_endpoint_url="http://localhost:9000",
        signature_version="s3v4",
        addressing_style="path",
        key_prefix="subscriptions/example",
    )
    # Explicit dummy credentials make these real SDK signing tests network-free.
    fs.session = aioboto3.Session(
        aws_access_key_id="local-signing-test",
        aws_secret_access_key="local-signing-test-secret",
    )
    return fs


@pytest.mark.parametrize("operation", ["GET", "PUT"])
async def test_browser_links_are_signed_for_public_host(filesystem, operation):
    key = "knowledge_base/1/document/lista de precios.txt"
    if operation == "PUT":
        url = await filesystem.aget_presigned_put_url(key, content_type="text/plain")
    else:
        url = await filesystem.aget_signed_url(key, force_inline=True)
    parsed = urlsplit(url)
    assert parsed.netloc == "localhost:9000"
    assert (
        parsed.path
        == "/private-documents/subscriptions/example/knowledge_base/1/document/lista%20de%20precios.txt"
    )
    query = parse_qs(parsed.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "host" in query["X-Amz-SignedHeaders"][0].split(";")
    assert query["X-Amz-Signature"]
    if operation == "PUT":
        assert "content-type" in query["X-Amz-SignedHeaders"][0].split(";")
    else:
        assert query["response-content-disposition"] == ["inline"]


async def test_internal_download_link_keeps_server_host(filesystem):
    url = await filesystem.aget_signed_url(
        "recordings/1.wav", use_internal_endpoint=True
    )
    assert urlsplit(url).netloc == "storage.internal:9000"


@pytest.mark.parametrize("public_endpoint", [None, ""])
async def test_unset_browser_endpoint_preserves_existing_links(
    filesystem, public_endpoint
):
    filesystem.public_endpoint_url = public_endpoint
    get_url = await filesystem.aget_signed_url("document.txt")
    put_url = await filesystem.aget_presigned_put_url("document.txt")
    assert urlsplit(get_url).netloc == "storage.internal:9000"
    assert urlsplit(put_url).netloc == "storage.internal:9000"


async def test_server_reads_and_writes_keep_internal_endpoint(filesystem, monkeypatch):
    client = SimpleNamespace(
        head_object=AsyncMock(return_value={"ContentLength": 4}),
        put_object=AsyncMock(),
        download_file=AsyncMock(),
    )
    endpoints = []

    @asynccontextmanager
    async def factory(service, **kwargs):
        endpoints.append(kwargs["endpoint_url"])
        yield client

    monkeypatch.setattr(filesystem.session, "client", factory)
    assert await filesystem.aget_file_metadata("document.txt")
    assert await filesystem.acreate_file(
        "document.txt", SimpleNamespace(read=AsyncMock(return_value=b"test"))
    )
    assert await filesystem.adownload_file("document.txt", "/tmp/document.txt")
    assert endpoints == ["http://storage.internal:9000"] * 3
    assert (
        client.put_object.await_args.kwargs["Key"]
        == "subscriptions/example/document.txt"
    )


async def test_managed_upload_cannot_bypass_quota_with_public_endpoint(filesystem):
    filesystem.storage_limit_bytes = 100
    with pytest.raises(ValueError, match="quota-controlled"):
        await filesystem.aget_presigned_put_url("document.txt")
