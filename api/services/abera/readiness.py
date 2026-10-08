"""Managed host readiness: live workers and the rendered local login page."""

import asyncio
from urllib.request import urlopen

WORKER_HEALTH_KEY = "abera:health:worker"
ORCHESTRATOR_HEALTH_KEY = "abera:health:orchestrator"


async def orchestrator_heartbeat(redis, listener_ready):
    await listener_ready.wait()
    try:
        while True:
            await redis.set(ORCHESTRATOR_HEALTH_KEY, "ready", ex=15)
            await asyncio.sleep(5)
    finally:
        await redis.delete(ORCHESTRATOR_HEALTH_KEY)


async def check_workers(redis):
    values = await redis.mget(WORKER_HEALTH_KEY, ORCHESTRATOR_HEALTH_KEY)
    if len(values) != 2 or not all(values):
        raise RuntimeError("Worker or campaign orchestrator heartbeat is absent")


def check_ui():
    # Fixed Docker-network URL; never accept a user-controlled probe target.
    with urlopen("http://ui:3010/auth/login", timeout=5) as response:
        if response.status != 200 or b"<html" not in response.read(2 * 1024 * 1024).lower():
            raise RuntimeError("The local login page is not ready")


async def main():
    from redis.asyncio import Redis
    from api.constants import DEPLOYMENT_MODE, REDIS_URL

    if DEPLOYMENT_MODE != "abera":
        raise RuntimeError("Managed readiness requires DEPLOYMENT_MODE=abera")
    async with Redis.from_url(REDIS_URL, socket_timeout=5, socket_connect_timeout=5) as redis:
        await check_workers(redis)
        check_ui()


if __name__ == "__main__":
    asyncio.run(main())
