"""Sample all local Dograh containers while the Realtime capacity test runs.

Run on the Docker host, not inside the API container. Docker Desktop must be
limited to 2 CPUs and 4 GiB for a result comparable to a t3a.medium.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

UNITS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
}


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def bytes_used(value: str) -> int:
    match = re.fullmatch(r"([0-9.]+)\s*([A-Za-z]+)", value.split("/")[0].strip())
    if not match:
        raise ValueError("Unrecognized Docker memory usage")
    return round(float(match.group(1)) * UNITS[match.group(2)])


def snapshot(names: list[str]) -> list[dict]:
    raw = docker("stats", "--no-stream", "--format", "{{json .}}", *names)
    rows = []
    for line in raw.splitlines():
        item = json.loads(line)
        rows.append(
            {
                "name": item["Name"],
                "cpu_percent_of_one_core": float(item["CPUPerc"].rstrip("%")),
                "memory_bytes": bytes_used(item["MemUsage"]),
                "memory_limit": item["MemUsage"].split("/")[1].strip(),
                "pids": int(item["PIDs"]),
                "network_io": item["NetIO"],
            }
        )
    if {row["name"] for row in rows} != set(names):
        raise RuntimeError("Docker stats did not return every requested container")
    return rows


def container_state(names: list[str]) -> dict:
    raw = docker(
        "inspect",
        "--format",
        "{{.Name}}|{{.State.Running}}|{{.State.OOMKilled}}|{{.RestartCount}}",
        *names,
    )
    return {
        parts[0].lstrip("/"): {
            "running": parts[1] == "true",
            "oom_killed": parts[2] == "true",
            "restart_count": int(parts[3]),
        }
        for line in raw.splitlines()
        if (parts := line.split("|"))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--containers", nargs="+", required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-uncapped",
        action="store_true",
        help="Collect diagnostics only; these are not t3a.medium-equivalent",
    )
    args = parser.parse_args()
    if args.duration < 30 or args.interval < 2:
        parser.error("duration must be >=30 seconds and interval >=2 seconds")
    cpus, memory = docker("info", "--format", "{{.NCPU}} {{.MemTotal}}").split()
    capacity = {"cpus": int(cpus), "memory_bytes": int(memory)}
    comparable = capacity["cpus"] <= 2 and capacity["memory_bytes"] <= 4 * 1024**3
    if not comparable and not args.allow_uncapped:
        parser.error(
            "Docker has more than 2 CPUs or 4 GiB; cap Docker Desktop or use --allow-uncapped"
        )
    before = container_state(args.containers)
    names = list(before)
    if len(names) != len(args.containers):
        parser.error("Every requested container must exist and have a distinct name")
    samples = []
    errors: list[dict] = []
    failures = 0
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            at = datetime.now(timezone.utc).isoformat()
            try:
                rows = snapshot(names)
            except subprocess.CalledProcessError as error:
                # A transient Docker daemon hiccup must not discard the samples
                # collected so far; tolerate a few, then stop with partial data.
                failures += 1
                errors.append({"at": at, "error": f"snapshot failed {failures}x"})
                if failures > 5:
                    break
                time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
                continue
            failures = 0
            samples.append(
                {
                    "at": at,
                    "containers": rows,
                    "total_cpu_percent_of_one_core": round(
                        sum(r["cpu_percent_of_one_core"] for r in rows), 2
                    ),
                    "total_memory_bytes": sum(r["memory_bytes"] for r in rows),
                }
            )
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        pass
    try:
        state_after = container_state(names)
    except Exception as error:
        state_after = {"error": f"{type(error).__name__}"}
    result = {
        "docker_capacity": capacity,
        "comparable_to_t3a_medium_resources": comparable,
        "container_state_before": before,
        "container_state_after": state_after,
        "samples": samples,
        "snapshot_errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"{len(samples)} samples written to {args.output}; 2-vCPU/4-GiB comparable: {comparable}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
