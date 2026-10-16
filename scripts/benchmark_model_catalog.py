"""Reproducible, provider-free ASGI benchmark for the old and new catalogs.

Run on Linux with Python 3.13 and api/.env.test in an isolated test environment:
    python -m scripts.benchmark_model_catalog --label before --output result.json

No lifespan/startup or provider calls run. Authentication is replaced only for
this in-process benchmark. Results measure catalog rendering and serialization,
not real voice latency, network throughput or a production capacity limit.
"""

import argparse
import asyncio
import json
import resource
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from loguru import logger


async def benchmark(requests: int, concurrency: int) -> dict:
    logger.remove()
    from api.app import app
    from api.services.auth.depends import get_user

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    path = "/api/v1/model-connections/catalog"
    if path not in paths:
        path = "/api/v1/user/configurations/defaults"
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=1, selected_organization_id=42, provider_id="benchmark-only"
    )
    durations = []
    sizes = []
    semaphore = asyncio.Semaphore(concurrency)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://benchmark.test"
        ) as client:
            for _ in range(20):
                response = await client.get(path)
                response.raise_for_status()

            async def request():
                async with semaphore:
                    started = time.perf_counter()
                    response = await client.get(path)
                    response.raise_for_status()
                    durations.append((time.perf_counter() - started) * 1000)
                    sizes.append(len(response.content))

            cpu_started = time.process_time()
            started = time.perf_counter()
            await asyncio.gather(*(request() for _ in range(requests)))
            elapsed = time.perf_counter() - started
            cpu = time.process_time() - cpu_started
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    return {
        "endpoint": path,
        "requests": requests,
        "concurrency": concurrency,
        "warmup_requests": 20,
        "elapsed_seconds": round(elapsed, 3),
        "cpu_seconds": round(cpu, 3),
        "requests_per_second": round(requests / elapsed, 2),
        "median_ms": round(statistics.median(durations), 3),
        "p95_ms": round(sorted(durations)[int(len(durations) * 0.95) - 1], 3),
        "response_bytes": sizes[0],
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if args.requests < 20 or args.concurrency < 1:
        parser.error("Use at least 20 requests and one concurrent request")
    result = {
        "label": args.label,
        **asyncio.run(benchmark(args.requests, args.concurrency)),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
