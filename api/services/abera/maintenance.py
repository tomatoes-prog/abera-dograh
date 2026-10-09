"""Keep managed startup writers paused while migrations/readiness are pending."""

import asyncio


async def wait_for_writes(redis):
    while await redis.get("abera:updating"):
        await asyncio.sleep(1)


async def before_job(ctx):
    from api.constants import DEPLOYMENT_MODE

    if DEPLOYMENT_MODE == "abera":
        await wait_for_writes(ctx["redis"])
