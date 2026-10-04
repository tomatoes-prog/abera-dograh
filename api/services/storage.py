import os
import re

from loguru import logger

from api.constants import (
    ABERA_STORAGE_LIMIT_BYTES,
    ENABLE_AWS_S3,
    ENVIRONMENT,
    S3_ADDRESSING_STYLE,
    S3_BUCKET,
    S3_ENDPOINT_URL,
    S3_REGION,
    S3_SIGNATURE_VERSION,
)
from api.enums import Environment, StorageBackend

from .filesystem import BaseFileSystem, NullFileSystem, S3FileSystem


def get_storage_for_backend(backend: str) -> BaseFileSystem:
    """Get storage instance for a specific backend enum.

    Maps StorageBackend enum codes to actual storage implementations:
    - Code 1 (S3): AWS S3 via S3FileSystem
    Historical MinIO values require an explicit data migration.
    """
    if backend == StorageBackend.MINIO.value:
        raise ValueError("Legacy MinIO objects must be migrated to S3 before access")

    # Code 1: AWS S3 implementation (cloud deployments)
    if backend == StorageBackend.S3.value:
        if not S3_BUCKET:
            raise ValueError(
                "S3_BUCKET environment variable is required when using S3 storage"
            )
        bucket = S3_BUCKET
        region = S3_REGION
        logger.info(
            f"Initializing {backend} storage with bucket '{bucket}' in region '{region}'"
        )
        key_prefix = ""
        if os.getenv("DEPLOYMENT_MODE") == "abera":
            subscription_id = os.environ["ABERA_SUBSCRIPTION_ID"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,47}", subscription_id):
                raise ValueError("Invalid ABERA_SUBSCRIPTION_ID for S3 isolation")
            key_prefix = f"subscriptions/{subscription_id}"
        return S3FileSystem(
            bucket_name=bucket,
            region_name=region,
            endpoint_url=S3_ENDPOINT_URL,
            signature_version=S3_SIGNATURE_VERSION,
            addressing_style=S3_ADDRESSING_STYLE,
            key_prefix=key_prefix,
            storage_limit_bytes=ABERA_STORAGE_LIMIT_BYTES if key_prefix else None,
        )

    # Future backend implementations can be added here:
    # elif backend == StorageBackend.GCS:  # Code 3
    #     return GoogleCloudFileSystem(...)
    # elif backend == StorageBackend.AZURE:  # Code 4
    #     return AzureBlobFileSystem(...)

    else:
        raise ValueError(f"Unknown storage backend: {backend}")


def get_current_storage_backend() -> StorageBackend:
    """Get the current storage backend enum."""
    return StorageBackend.get_current_backend()


# Create a single storage instance at module load time.
# In the test environment we skip the real backend so import doesn't require
# MinIO/S3 to be reachable; tests that need storage must inject a real fs.
if ENVIRONMENT == Environment.TEST.value:
    logger.info("ENVIRONMENT=test — using NullFileSystem (no storage backend)")
    storage_fs: BaseFileSystem = NullFileSystem()
else:
    _backend = StorageBackend.get_current_backend()
    logger.info(
        f"Initializing storage backend: {_backend.name} (value: {_backend.value}, ENABLE_AWS_S3={ENABLE_AWS_S3})"
    )
    storage_fs = get_storage_for_backend(_backend.value)


# For backward compatibility, keep get_storage() function
def get_storage() -> BaseFileSystem:
    """Get the module-level storage instance.

    Deprecated: Use 'from api.services.storage import storage_fs' instead.
    """
    return storage_fs
