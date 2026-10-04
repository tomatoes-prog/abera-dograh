"""Run once before writers start on a new, exclusive subscription runtime.

Queue jobs and final billing receipts survive. Live call slots cannot survive a
process replacement or a restore, and are never evidence of a current call.
"""
import asyncio

from redis.asyncio import Redis

from api.constants import DEPLOYMENT_MODE, REDIS_URL

STALE_PATTERNS = ("concurrent_calls:*", "workflow_slot_mapping:*", "rate_limit:*")


async def reset_runtime_leases(redis):
    await redis.delete("concurrent_calls_fleet")
    for pattern in STALE_PATTERNS:
        batch = []
        async for key in redis.scan_iter(match=pattern, count=100):
            batch.append(key)
            if len(batch) == 100:
                await redis.delete(*batch)
                batch.clear()
        if batch:
            await redis.delete(*batch)


async def main():
    if DEPLOYMENT_MODE != "abera":
        raise RuntimeError("Lease reset requires an exclusive Abera runtime")
    async with Redis.from_url(REDIS_URL, socket_timeout=5) as redis:
        await reset_runtime_leases(redis)


if __name__ == "__main__":
    asyncio.run(main())
