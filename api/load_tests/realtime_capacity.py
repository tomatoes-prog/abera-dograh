"""Run real WebRTC calls from outside the Dograh host being measured.

The selected workflows must already use openai_realtime/gpt-realtime-2.1-mini.
Run on a separate load generator with aiortc and PyAV installed, outside the
EC2 host or Docker VM whose capacity is being measured.
"""

from __future__ import annotations

import argparse
import math
import numpy as np
import asyncio
import json
import os
import time
import uuid
import wave
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from aiortc import (
    AudioStreamTrack,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame
from websockets import connect


SAMPLE_RATE = 48_000
FRAME_SAMPLES = 960  # 20 ms at 48 kHz
FRAME_BYTES = FRAME_SAMPLES * 2  # mono PCM16


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as recording:
        if (recording.getnchannels(), recording.getsampwidth(), recording.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError("Audio must be mono, 16-bit PCM WAV at 48 kHz")
        samples = recording.readframes(recording.getnframes())
    if len(samples) < FRAME_BYTES:
        raise ValueError("Audio must contain at least 20 ms of speech")
    return samples


class RepeatingSpeechTrack(AudioStreamTrack):
    """Send paced speech bursts with silence between turns."""

    def __init__(self, audio: bytes, *, speak_seconds: float, cycle_seconds: float, phase_seconds: float,
                 warmup_seconds: float = 12.0):
        super().__init__()
        self.audio = audio
        self.speak_frames = round(speak_seconds / 0.02)
        self.cycle_frames = round(cycle_seconds / 0.02)
        self.phase_frames = round(phase_seconds / 0.02)
        # Lead silence so the first burst never talks over the greeting while
        # the runtime holds the caller muted (MuteUntilFirstBotComplete).
        self.warmup_frames = round(warmup_seconds / 0.02)
        self.frame_index = 0
        self.started_at: float | None = None
        self.last_turn_end: float | None = None
        self.turn_number = 0
        if not 0 < self.speak_frames < self.cycle_frames:
            raise ValueError("speak_seconds must be shorter than cycle_seconds")

    async def recv(self) -> AudioFrame:
        if self.started_at is None:
            self.started_at = time.monotonic()
        due = self.started_at + self.frame_index * 0.02
        await asyncio.sleep(max(0.0, due - time.monotonic()))

        phase = (self.frame_index + self.phase_frames) % self.cycle_frames
        if self.frame_index < self.warmup_frames:
            chunk = bytes(FRAME_BYTES)
        elif phase < self.speak_frames:
            offset = (phase * FRAME_BYTES) % len(self.audio)
            chunk = self.audio[offset : offset + FRAME_BYTES]
            if len(chunk) < FRAME_BYTES:
                chunk += self.audio[: FRAME_BYTES - len(chunk)]
        else:
            chunk = bytes(FRAME_BYTES)
        if phase == self.speak_frames:
            self.turn_number += 1
            self.last_turn_end = time.monotonic()

        frame = AudioFrame(format="s16", layout="mono", samples=FRAME_SAMPLES)
        frame.planes[0].update(chunk)
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self.frame_index * FRAME_SAMPLES
        frame.time_base = Fraction(1, SAMPLE_RATE)
        self.frame_index += 1
        return frame


def api_json(base_url: str, path: str, token: str, *, method: str = "GET", body: dict | None = None,
             devops_secret: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if devops_secret is None:
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["X-Dograh-Devops-Secret"] = devops_secret
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base_url + path, data=payload, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def websocket_url(base_url: str, workflow_id: int, run_id: int, token: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    path = f"{parts.path.rstrip('/')}/api/v1/ws/signaling/{workflow_id}/{run_id}"
    return urlunsplit((scheme, parts.netloc, path, f"token={quote(token, safe='')}", ""))


async def observe_audio(track, result: dict, speech: RepeatingSpeechTrack) -> None:
    measured_turn = 0
    try:
        while True:
            frame = await track.recv()
            result["received_audio_frames"] += 1
            # The server latency histogram is the primary timing measurement.
            # Client frames prove that speech reached the caller.
            samples = frame.to_ndarray().astype(np.float64)
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            threshold = 0.003 if frame.format.name.startswith("flt") else 100
            if rms >= threshold:
                result["received_speech_frames"] += 1
                if speech.last_turn_end is not None and speech.turn_number > measured_turn:
                    result["response_ms"].append(round((time.monotonic() - speech.last_turn_end) * 1000, 1))
                    measured_turn = speech.turn_number
    except (asyncio.CancelledError, Exception):
        return


async def call(base_url: str, workflow_id: int, token: str, audio: bytes,
               seconds: int, ordinal: int, speak_seconds: float, cycle_seconds: float,
               warmup_seconds: float) -> dict:
    result = {"client": ordinal, "workflow_id": workflow_id, "status": "failed",
              "received_audio_frames": 0, "received_speech_frames": 0, "response_ms": []}
    try:
        run = await asyncio.to_thread(
            api_json, base_url, f"/api/v1/workflow/{workflow_id}/runs", token,
            method="POST", body={"mode": "smallwebrtc", "name": f"CAP-{uuid.uuid4().hex[:12]}"},
        )
    except Exception as error:
        result["error"] = f"CreateRun:{type(error).__name__}"
        return result
    run_id = int(run["id"])
    result["run_id"] = run_id
    try:
        turn = await asyncio.to_thread(
            api_json, base_url, "/api/v1/turn/credentials", token,
        )
        if not turn.get("uris") or not turn.get("username") or not turn.get("password"):
            raise ValueError("TURN credentials are incomplete")
    except Exception as error:
        result["error"] = f"TurnCredentials:{type(error).__name__}"
        return result
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(
        urls=turn["uris"], username=turn["username"], credential=turn["password"],
    )]))
    pc_id = uuid.uuid4().hex
    speech = RepeatingSpeechTrack(
        audio, speak_seconds=speak_seconds, cycle_seconds=cycle_seconds,
        phase_seconds=(ordinal - 1) * cycle_seconds / 5,
        warmup_seconds=warmup_seconds,
    )
    pc.addTrack(speech)
    connected = asyncio.Event()
    disconnected = asyncio.Event()
    audio_tasks: list[asyncio.Task] = []

    @pc.on("connectionstatechange")
    async def state_changed():
        if pc.connectionState == "connected":
            connected.set()
        elif pc.connectionState in {"failed", "disconnected", "closed"}:
            disconnected.set()

    @pc.on("track")
    def track_received(track):
        if track.kind == "audio":
            audio_tasks.append(asyncio.create_task(observe_audio(track, result, speech)))

    async def signaling(ws) -> None:
        async for raw in ws:
            message = json.loads(raw)
            kind = message.get("type")
            payload = message.get("payload") or {}
            if kind == "answer":
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
                )
            elif kind == "ice-candidate":
                data = payload.get("candidate")
                if data:
                    candidate = candidate_from_sdp(data["candidate"].removeprefix("candidate:"))
                    candidate.sdpMid = data.get("sdpMid")
                    candidate.sdpMLineIndex = data.get("sdpMLineIndex")
                    await pc.addIceCandidate(candidate)
            elif kind == "error":
                raise RuntimeError(f"Signaling error: {payload.get('error_type') or 'unknown'}")
            elif kind == "call-ended":
                raise RuntimeError("Call ended before the planned duration")

    started: float | None = None
    try:
        async with connect(websocket_url(base_url, workflow_id, run_id, token), max_size=4 * 1024 * 1024) as ws:
            reader = asyncio.create_task(signaling(ws))
            try:
                offer = await pc.createOffer()
                await pc.setLocalDescription(offer)
                await ws.send(json.dumps({"type": "offer", "payload": {
                    "pc_id": pc_id, "sdp": pc.localDescription.sdp, "type": pc.localDescription.type,
                }}))
                deadline = time.monotonic() + 45
                while not connected.is_set():
                    if reader.done():
                        await reader
                        raise RuntimeError("Signaling closed before WebRTC connected")
                    if disconnected.is_set() or time.monotonic() >= deadline:
                        raise RuntimeError("WebRTC did not connect within 45 seconds")
                    await asyncio.sleep(0.2)
                started = time.monotonic()
                while time.monotonic() - started < seconds:
                    if reader.done():
                        await reader
                        raise RuntimeError("Signaling closed during the call")
                    if disconnected.is_set():
                        raise RuntimeError("WebRTC disconnected during the call")
                    await asyncio.sleep(0.25)
                result["status"] = "completed"
            finally:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
    except Exception as error:
        # Library exceptions can contain the WebSocket URL and bearer token.
        result["error"] = str(error) if type(error) is RuntimeError else type(error).__name__
    finally:
        result["connected_seconds"] = round(time.monotonic() - started, 1) if started else 0
        await pc.close()
        for task in audio_tasks:
            task.cancel()
        if audio_tasks:
            await asyncio.gather(*audio_tasks, return_exceptions=True)
        result["run_completed"] = False
        result["usage_info"] = None
        for _ in range(15):
            try:
                details = await asyncio.to_thread(
                    api_json, base_url, f"/api/v1/workflow/{workflow_id}/runs/{run_id}", token,
                )
                result["run_completed"] = bool(details.get("is_completed"))
                result["usage_info"] = details.get("usage_info")
                runtime = (details.get("initial_context") or {}).get("runtime_configuration") or {}
                result["runtime_model"] = runtime.get("realtime_model")
                result["runtime_provider"] = runtime.get("realtime_provider")
                if result["run_completed"]:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)
    return result


async def sample_health(base_url: str, token: str, secret: str, samples: list[dict], stop: asyncio.Event) -> None:
    while not stop.is_set():
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            data = await asyncio.to_thread(
                api_json, base_url, "/api/v1/health/active-calls", token, devops_secret=secret,
            )
            samples.append({"at": stamp, **data})
        except Exception as error:
            samples.append({"at": stamp, "error": type(error).__name__})
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            pass


async def run(args: argparse.Namespace, audio: bytes) -> dict:
    config = await asyncio.to_thread(api_json, args.base_url, "/api/v1/user/configurations/user", os.environ["DOGRAH_TEST_ACCESS_TOKEN"])
    realtime = config.get("realtime") or {}
    if realtime.get("provider") != "openai_realtime" or realtime.get("model") != args.expected_model:
        raise ValueError("Realtime configuration does not match the requested model; no calls started")
    token = os.environ["DOGRAH_TEST_ACCESS_TOKEN"]
    secret = os.environ["DOGRAH_DEVOPS_SECRET"]
    ids = [int(value) for value in args.workflow_ids.split(",")]
    if len(ids) not in {1, args.clients}:
        raise ValueError("Pass one workflow ID or one ID per client")
    workflows = ids * args.clients if len(ids) == 1 else ids
    samples: list[dict] = []
    stop = asyncio.Event()
    monitor = asyncio.create_task(sample_health(args.base_url, token, secret, samples, stop))
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        calls = await asyncio.gather(*(
            call(args.base_url, workflow_id, token, audio, args.seconds, n,
                 args.speak_seconds, args.cycle_seconds, args.warmup_seconds)
            for n, workflow_id in enumerate(workflows, 1)
        ))
    finally:
        stop.set()
        await monitor
    return {"started_at": started_at, "expected_model": args.expected_model, "configured_model": realtime["model"],
            "clients": args.clients, "planned_seconds": args.seconds,
            "calls": calls, "health_samples": samples}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Dograh origin, for example https://example.apps.dev.abera.cloud")
    parser.add_argument("--workflow-ids", required=True, help="One workflow ID or one per client, comma separated")
    parser.add_argument("--wav", required=True, type=Path, help="Mono PCM16 48-kHz Spanish speech WAV")
    parser.add_argument("--clients", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--expected-model", default="gpt-realtime-2.1-mini")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--speak-seconds", type=float, default=5.0)
    parser.add_argument("--cycle-seconds", type=float, default=20.0)
    parser.add_argument("--warmup-seconds", type=float, default=12.0,
                        help="Lead silence before the first speech burst")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.seconds < 30:
        parser.error("--seconds must be at least 30")
    if not args.base_url.startswith(("http://", "https://")):
        parser.error("--base-url must be HTTP or HTTPS")
    audio = read_wav(args.wav)
    result = asyncio.run(run(args, audio))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(item["status"] == "completed" and len(item["response_ms"]) >= max(2, math.floor((args.seconds - args.warmup_seconds) / args.cycle_seconds) - 1)
                 and item["run_completed"] and item.get("runtime_model") == args.expected_model
                 and item.get("runtime_provider") == "openai_realtime"
                 for item in result["calls"])
    print(f"{passed}/{args.clients} calls completed with received speech; result: {args.output}")
    return 0 if passed == args.clients else 1


if __name__ == "__main__":
    raise SystemExit(main())
