"""Serialize managed storage writes and enforce the current-object byte limit."""

import asyncio
import hashlib
from contextlib import asynccontextmanager, suppress


class StorageQuotaExceeded(Exception):
    pass


class StorageQuotaUnavailable(Exception):
    pass


@asynccontextmanager
async def storage_write_lock(bucket: str, prefix: str):
    from api.tasks.arq import get_arq_redis

    name = "storage-quota:" + hashlib.sha256(f"{bucket}/{prefix}".encode()).hexdigest()
    try:
        redis = await get_arq_redis()
        lock = redis.lock(name, timeout=600, blocking_timeout=15, thread_local=False)
        acquired = await lock.acquire()
    except Exception as exc:
        raise StorageQuotaUnavailable("Storage quota service is unavailable") from exc
    if not acquired:
        raise StorageQuotaUnavailable("Storage is busy; retry the upload")
    owner = asyncio.current_task()
    lease_lost = False

    async def renew():
        nonlocal lease_lost
        while True:
            await asyncio.sleep(60)
            try:
                await lock.extend(600, replace_ttl=True)
            except Exception:
                lease_lost = True
                owner.cancel()
                return

    renewal = asyncio.create_task(renew())
    try:
        yield
    except asyncio.CancelledError as exc:
        if lease_lost:
            raise StorageQuotaUnavailable("Storage write lease was lost") from exc
        raise
    finally:
        renewal.cancel()
        with suppress(asyncio.CancelledError):
            await renewal
        with suppress(Exception):
            await lock.release()
