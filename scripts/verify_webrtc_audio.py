"""Local WebRTC audio round trip using Dograh's Pipecat transport; no AI APIs.

Run in the production image on an isolated Docker network with no external route.
The two peers, their ICE candidates, and their synthetic audio stay in one process.
"""

import asyncio
import fractions
import importlib.util
import json

import numpy as np
from aiortc import (
    AudioStreamTrack,
    RTCConfiguration,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from av import AudioFrame
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import RawAudioTrack


class ToneTrack(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.samples_sent = 0
        self.start_time = None

    async def recv(self):
        loop = asyncio.get_running_loop()
        if self.start_time is None:
            self.start_time = loop.time()
        await asyncio.sleep(max(0, self.start_time + self.samples_sent / 48000 - loop.time()))
        samples = np.arange(self.samples_sent, self.samples_sent + 960)
        pcm = (9000 * np.sin(2 * np.pi * 440 * samples / 48000)).astype(np.int16)
        frame = AudioFrame.from_ndarray(pcm[np.newaxis, :], layout="mono")
        frame.sample_rate = 48000
        frame.pts = self.samples_sent
        frame.time_base = fractions.Fraction(1, 48000)
        self.samples_sent += 960
        return frame


async def main():
    assert importlib.util.find_spec("cv2") is None
    client = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    server = SmallWebRTCConnection(ice_servers=[], connection_timeout_secs=15)
    incoming = asyncio.get_running_loop().create_future()
    data_received = asyncio.Event()
    channel = client.createDataChannel("voice-check")

    @client.on("track")
    def on_track(track):
        assert track.kind == "audio"
        if not incoming.done():
            incoming.set_result(track)

    @server.event_handler("app-message")
    async def on_message(connection, message):
        if message == {"type": "voice-check"}:
            data_received.set()

    tone = ToneTrack()
    client.addTrack(tone)
    opus = [codec for codec in RTCRtpSender.getCapabilities("audio").codecs if codec.mimeType == "audio/opus"]
    assert opus, "Opus codec is required for browser voice calls"
    client.getTransceivers()[0].setCodecPreferences(opus)
    server_audio = RawAudioTrack(sample_rate=16000)
    pcm = (9000 * np.sin(2 * np.pi * 660 * np.arange(32000) / 16000)).astype(np.int16)
    server_audio.add_audio_bytes(pcm.tobytes())
    source = None
    try:
        await client.setLocalDescription(await client.createOffer())
        assert "m=video " not in client.localDescription.sdp
        await server.initialize(client.localDescription.sdp, "offer")
        server.replace_audio_track(server_audio)
        answer = server.get_answer()
        assert "m=video " not in answer["sdp"]
        await client.setRemoteDescription(RTCSessionDescription(answer["sdp"], answer["type"]))
        await server.connect()
        destination = await asyncio.wait_for(incoming, 15)
        source = server.audio_input_track()
        assert source is not None

        async def receive_audible(track):
            peaks = []
            for _ in range(12):
                frame = await track.recv()
                assert frame.sample_rate > 0
                peaks.append(np.abs(frame.to_ndarray().astype(np.float32)).max())
            assert max(peaks) > 100, "Audio decoded to silence"

        await asyncio.wait_for(asyncio.gather(receive_audible(source), receive_audible(destination)), 15)
        for _ in range(100):
            if channel.readyState == "open":
                break
            await asyncio.sleep(0.05)
        assert channel.readyState == "open"
        channel.send(json.dumps({"type": "voice-check"}))
        await asyncio.wait_for(data_received.wait(), 5)
        assert all(t.kind == "audio" for t in client.getTransceivers())
        print("WebRTC passed without OpenCV: audible audio both directions, Opus, data channel, no video")
    finally:
        if source:
            source.stop()
        server_audio.mark_pending_futures_done()
        tone.stop()
        server_audio.stop()
        await server.disconnect()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
