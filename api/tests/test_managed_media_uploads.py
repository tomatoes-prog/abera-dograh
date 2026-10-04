"""Managed media retains upload quotas and cannot reference neighboring objects."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import constants
from api.routes import workflow, workflow_recording
from api.schemas.workflow_recording import (
    BatchRecordingCreateRequestSchema,
    BatchRecordingUploadRequestSchema,
)
from api.services.abera import storage_upload


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["abera", "oss"])
async def test_recording_upload_uses_exact_size_and_managed_quota(monkeypatch, mode):
    monkeypatch.setattr(constants, "DEPLOYMENT_MODE", mode)
    monkeypatch.setattr(
        workflow_recording,
        "_generate_unique_recording_id",
        AsyncMock(return_value="saludo01"),
    )
    grant = AsyncMock(return_value="https://example.com/managed-upload/ticket")
    presign = AsyncMock(return_value="https://example.com/direct-upload")
    monkeypatch.setattr(storage_upload, "create_upload_url", grant)
    monkeypatch.setattr(
        workflow_recording.storage_fs, "aget_presigned_put_url", presign
    )
    result = await workflow_recording.get_upload_urls(
        BatchRecordingUploadRequestSchema(
            files=[
                {"filename": "saludo.wav", "mime_type": "audio/wav", "file_size": 321}
            ]
        ),
        user=SimpleNamespace(selected_organization_id=42),
    )
    key = "recordings/42/saludo01/saludo.wav"
    assert result.items[0].storage_key == key
    if mode == "abera":
        grant.assert_awaited_once_with(key, 321, "audio/wav")
        presign.assert_not_awaited()
    else:
        presign.assert_awaited_once_with(
            file_path=key, expiration=1800, content_type="audio/wav", max_size=321
        )
        grant.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_filename_does_not_issue_partial_batch_grants(monkeypatch):
    grant = AsyncMock()
    presign = AsyncMock()
    monkeypatch.setattr(storage_upload, "create_upload_url", grant)
    monkeypatch.setattr(
        workflow_recording.storage_fs, "aget_presigned_put_url", presign
    )
    with pytest.raises(HTTPException) as error:
        await workflow_recording.get_upload_urls(
            BatchRecordingUploadRequestSchema(
                files=[
                    {"filename": "saludo.wav", "file_size": 321},
                    {"filename": "../otra.wav", "file_size": 321},
                ]
            ),
            user=SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 422
    grant.assert_not_awaited()
    presign.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "recordings/91/saludo01/saludo.wav",
        "recordings/42/otro-audio/saludo.wav",
        "recordings/42/saludo01/../saludo.wav",
    ],
)
async def test_recording_creation_rejects_foreign_or_forged_references_before_writes(
    monkeypatch, key
):
    create = AsyncMock()
    monkeypatch.setattr(workflow_recording.db_client, "create_recording", create)
    with pytest.raises(HTTPException) as error:
        await workflow_recording.create_recordings(
            BatchRecordingCreateRequestSchema(
                recordings=[
                    {
                        "recording_id": "valid001",
                        "storage_key": "recordings/42/valid001/saludo.wav",
                        "transcript": "Hola",
                    },
                    {
                        "recording_id": "saludo01",
                        "storage_key": key,
                        "transcript": "Hola",
                    },
                ]
            ),
            user=SimpleNamespace(id=1, selected_organization_id=42),
        )
    assert error.value.status_code == 403
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambient_audio_uses_quota_grant_for_owned_workflow(monkeypatch):
    monkeypatch.setattr(constants, "DEPLOYMENT_MODE", "abera")
    get_workflow = AsyncMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(workflow.db_client, "get_workflow", get_workflow)
    grant = AsyncMock(return_value="https://example.com/managed-upload/ticket")
    presign = AsyncMock()
    monkeypatch.setattr(storage_upload, "create_upload_url", grant)
    monkeypatch.setattr(workflow.storage_fs, "aget_presigned_put_url", presign)
    result = await workflow.get_ambient_noise_upload_url(
        workflow.AmbientNoiseUploadRequest(
            workflow_id=7, filename="oficina.wav", file_size=321
        ),
        user=SimpleNamespace(selected_organization_id=42),
    )
    assert result.storage_key.startswith("ambient-noise/42/7/")
    get_workflow.assert_awaited_once_with(7, organization_id=42)
    grant.assert_awaited_once_with(result.storage_key, 321, "audio/wav")
    presign.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambient_audio_cannot_issue_grant_for_neighbor_workflow(monkeypatch):
    monkeypatch.setattr(
        workflow.db_client, "get_workflow", AsyncMock(return_value=None)
    )
    grant = AsyncMock()
    monkeypatch.setattr(storage_upload, "create_upload_url", grant)
    with pytest.raises(HTTPException) as error:
        await workflow.get_ambient_noise_upload_url(
            workflow.AmbientNoiseUploadRequest(
                workflow_id=7, filename="oficina.wav", file_size=321
            ),
            user=SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 404
    grant.assert_not_awaited()
