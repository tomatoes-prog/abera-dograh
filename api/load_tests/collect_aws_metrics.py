"""Export EC2 and CloudWatch Agent metrics for one Abera Dograh DEV run.

Read-only. Use an AWS profile with cloudwatch:GetMetricData,
cloudwatch:ListMetrics and ec2:DescribeInstances permissions.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def instance_record(ec2, instance_id: str, subscription_id: str) -> dict:
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    instances = [
        item for reservation in reservations for item in reservation["Instances"]
    ]
    if len(instances) != 1:
        raise ValueError("Expected one EC2 instance")
    instance = instances[0]
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
    if (
        tags.get("abera:product-id") != "abera-dograh"
        or tags.get("abera:subscription-id") != subscription_id
    ):
        raise ValueError(
            "The instance does not belong to the requested Dograh subscription"
        )
    if tags.get("abera:environment") != "dev":
        raise ValueError("Capacity collection is limited to DEV")
    return {
        "instance_id": instance_id,
        "instance_type": instance["InstanceType"],
        "state": instance["State"]["Name"],
        "subscription_id": subscription_id,
    }


def agent_metrics(cloudwatch, instance_id: str) -> dict:
    found = {}
    pager = cloudwatch.get_paginator("list_metrics")
    for page in pager.paginate(
        Namespace="Abera/Dograh",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
    ):
        for metric in page["Metrics"]:
            name = metric["MetricName"]
            dims = {item["Name"]: item["Value"] for item in metric["Dimensions"]}
            if name in {"mem_used_percent", "mem_available"}:
                found.setdefault(name, metric["Dimensions"])
            elif name == "cpu_usage_active" and dims.get("cpu") == "cpu-total":
                found[name] = metric["Dimensions"]
            elif name == "disk_used_percent" and dims.get("path") == "/":
                found[name] = metric["Dimensions"]
    return found


def query(
    namespace: str, name: str, dims: list[dict], period: int, number: int
) -> dict:
    return {
        "Id": f"m{number}",
        "MetricStat": {
            "Metric": {"Namespace": namespace, "MetricName": name, "Dimensions": dims},
            "Period": period,
            "Stat": "Average",
        },
        "ReturnData": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--start", required=True, type=timestamp)
    parser.add_argument("--end", required=True, type=timestamp)
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("--end must follow --start")
    session = boto3.Session(region_name=args.region)
    identity = instance_record(
        session.client("ec2"), args.instance_id, args.subscription_id
    )
    cw = session.client("cloudwatch")
    dimension = [{"Name": "InstanceId", "Value": args.instance_id}]
    wanted = [
        ("AWS/EC2", "CPUUtilization", dimension, 60),
        ("AWS/EC2", "CPUCreditBalance", dimension, 300),
        ("AWS/EC2", "NetworkIn", dimension, 60),
        ("AWS/EC2", "NetworkOut", dimension, 60),
    ]
    available = agent_metrics(cw, args.instance_id)
    for name in (
        "cpu_usage_active",
        "mem_used_percent",
        "mem_available",
        "disk_used_percent",
    ):
        if name in available:
            wanted.append(("Abera/Dograh", name, available[name], 10))
    queries = [query(*item, number=index) for index, item in enumerate(wanted, 1)]
    data = {}
    request = {
        "MetricDataQueries": queries,
        "StartTime": args.start,
        "EndTime": args.end,
        "ScanBy": "TimestampAscending",
    }
    while True:
        response = cw.get_metric_data(**request)
        for item in response["MetricDataResults"]:
            target = data.setdefault(item["Id"], [])
            target.extend(
                {"at": at.isoformat(), "value": value}
                for at, value in zip(item["Timestamps"], item["Values"])
            )
        if not response.get("NextToken"):
            break
        request["NextToken"] = response["NextToken"]
    result = {
        "instance": identity,
        "region": args.region,
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "missing_agent_metrics": sorted(
            set(
                (
                    "cpu_usage_active",
                    "mem_used_percent",
                    "mem_available",
                    "disk_used_percent",
                )
            )
            - set(available)
        ),
        "metrics": {
            f"{namespace}/{name}": data.get(f"m{index}", [])
            for index, (namespace, name, _, _) in enumerate(wanted, 1)
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"CloudWatch metrics written to {args.output}; missing agent metrics: {result['missing_agent_metrics']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
