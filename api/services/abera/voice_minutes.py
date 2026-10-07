"""Short IAM-authorized leases for managed AI voice; billing owns the balance.

Only final receipts are persisted locally. Restoring this Redis data can retry
a receipt, but cannot grant time, reopen a call, or roll back billing's wallet.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
import uuid
from functools import lru_cache

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from loguru import logger
from redis.asyncio import Redis

from api.constants import (
    ABERA_BILLING_API_URL,
    ABERA_BILLING_REGION,
    ABERA_SUBSCRIPTION_ID,
    REDIS_URL,
)

RECEIPTS_KEY = "abera:voice:final-receipts"
BLOCK_SECONDS = 30


class VoiceAuthorizationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _aws_session():
    return boto3.Session()


class BillingVoiceClient:
    def __init__(
        self,
        base_url=ABERA_BILLING_API_URL,
        subscription_id=ABERA_SUBSCRIPTION_ID,
        region=ABERA_BILLING_REGION,
    ):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,46}[a-z0-9]", subscription_id):
            raise VoiceAuthorizationError("Invalid subscription identity")
        if region != "us-east-2" or not re.fullmatch(
            rf"https://[a-z0-9]{{10}}\.execute-api\.{re.escape(region)}\.amazonaws\.com/live",
            base_url,
        ):
            raise VoiceAuthorizationError("Invalid billing endpoint")
        self.url = (
            f"{base_url}/v1/internal/dograh/subscriptions/{subscription_id}/minutes"
        )
        self.region = region

    def _signed_headers(self, url, data):
        credentials = _aws_session().get_credentials()
        if credentials is None:
            raise VoiceAuthorizationError("No runtime IAM credentials")
        request = AWSRequest(
            method="POST",
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(
            credentials.get_frozen_credentials(), "execute-api", self.region
        ).add_auth(request)
        return dict(request.headers)

    async def request(self, operation, **body):
        if operation not in {"balance", "reserve", "extend", "settle"}:
            raise VoiceAuthorizationError("Unknown voice operation")
        url = f"{self.url}/{operation}"
        data = json.dumps(body, separators=(",", ":")).encode()
        try:
            headers = await asyncio.wait_for(
                asyncio.to_thread(self._signed_headers, url, data), timeout=3
            )
            async with httpx.AsyncClient(
                timeout=3, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(url, content=data, headers=headers)
            if response.status_code != 200:
                raise VoiceAuthorizationError(
                    f"Voice authorization failed ({response.status_code})"
                )
            return response.json()
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise VoiceAuthorizationError("Voice metering is unavailable") from exc


async def managed_balance_available():
    try:
        balance = await BillingVoiceClient().request("balance")
        return (
            not balance.get("review_required")
            and balance.get("available_seconds", 0) > 0
        )
    except Exception:
        return False


async def save_final_receipt(call_id, actual_seconds):
    async with Redis.from_url(
        REDIS_URL, decode_responses=True, socket_timeout=3
    ) as redis:
        # No TTL: outages must not discard the final duration.
        await redis.hsetnx(RECEIPTS_KEY, call_id, str(actual_seconds))


async def remove_final_receipt(call_id):
    async with Redis.from_url(
        REDIS_URL, decode_responses=True, socket_timeout=3
    ) as redis:
        await redis.hdel(RECEIPTS_KEY, call_id)


async def retry_voice_receipts(_ctx):
    # A downgrade disables new managed calls, but must still settle calls
    # completed under the previous plan. Billing accepts these receipts.
    if not ABERA_SUBSCRIPTION_ID or not ABERA_BILLING_API_URL:
        return
    client = BillingVoiceClient()
    async with Redis.from_url(
        REDIS_URL, decode_responses=True, socket_timeout=3
    ) as redis:
        # Persist scan position so one unavailable receipt cannot starve others.
        cursor = int(await redis.get(RECEIPTS_KEY + ":cursor") or 0)
        cursor, receipts = await redis.hscan(RECEIPTS_KEY, cursor=cursor, count=100)
        for call_id, seconds in receipts.items():
            try:
                await client.request(
                    "settle", call_id=call_id, actual_seconds=int(seconds)
                )
                await redis.hdel(RECEIPTS_KEY, call_id)
            except Exception:
                logger.warning(
                    "Pending voice receipt could not be delivered: {}", call_id
                )
        await redis.set(RECEIPTS_KEY + ":cursor", cursor)


class ManagedVoiceSession:
    """One runtime attempt, across agent handoffs, with a conservative deadline."""

    def __init__(
        self, workflow_run_id, stop_call, *, client=None, clock=time.monotonic
    ):
        self.client = client or BillingVoiceClient()
        self.call_id = f"run-{workflow_run_id}-{uuid.uuid4().hex}"
        self.stop_call = stop_call
        self.clock = clock
        self.origin = None
        self.billable_at = None
        self.stopped_at = None
        self.authorized = 0
        self.watchdog = None
        self.finished = False

    async def authorize(self):
        if self.origin is not None:
            return
        self.origin = self.clock()
        # If the response is lost, finish() still emits a zero-use receipt.
        receipt = await self.client.request(
            "reserve", call_id=self.call_id, seconds=BLOCK_SECONDS
        )
        self._accept(receipt)
        self.watchdog = asyncio.create_task(
            self._watch(), name=f"voice-lease-{self.call_id}"
        )

    def _accept(self, receipt):
        seconds = receipt.get("authorized_seconds")
        if (
            receipt.get("status") != "ACTIVE"
            or type(seconds) is not int
            or seconds <= self.authorized
        ):
            raise VoiceAuthorizationError("Invalid voice authorization")
        self.authorized = seconds

    def started(self):
        if self.billable_at is None:
            self.billable_at = self.clock()

    def stopped(self):
        if self.stopped_at is None:
            self.stopped_at = self.clock()

    async def _watch(self):
        extension = 1
        while True:
            remaining = self.origin + self.authorized - self.clock()
            if remaining <= 1:  # allow the transport one second to close
                self.stopped()
                self.watchdog = None  # finish may run inside stop_call's handlers
                await self.stop_call()
                return
            await asyncio.sleep(max(0, remaining - 10))
            try:
                receipt = await asyncio.wait_for(
                    self.client.request(
                        "extend",
                        call_id=self.call_id,
                        extension_id=f"block-{extension}",
                        seconds=BLOCK_SECONDS,
                    ),
                    timeout=min(6, max(0.1, remaining - 1)),
                )
                self._accept(receipt)
                extension += 1
            except Exception:
                # Do not allow slow/unavailable billing to extend the deadline.
                await asyncio.sleep(
                    max(0, self.origin + self.authorized - self.clock() - 1)
                )
                self.stopped()
                self.watchdog = None
                await self.stop_call()
                return

    async def finish(self):
        if self.finished:
            return
        self.finished = True
        self.stopped()
        if self.watchdog is not None:
            self.watchdog.cancel()
            await asyncio.gather(self.watchdog, return_exceptions=True)
        if self.origin is None:
            return  # ringing or pipeline setup never reached managed AI
        actual = (
            0
            if self.billable_at is None
            else min(
                self.authorized, max(0, math.ceil(self.stopped_at - self.billable_at))
            )
        )
        try:
            await save_final_receipt(self.call_id, actual)
        except Exception:
            # Still try direct settlement. Billing independently reconciles a
            # crash conservatively if both destinations are unavailable.
            logger.error("Could not persist final voice duration: {}", self.call_id)
        try:
            await self.client.request(
                "settle", call_id=self.call_id, actual_seconds=actual
            )
            await remove_final_receipt(self.call_id)
        except Exception:
            logger.warning("Voice settlement awaiting retry: {}", self.call_id)
