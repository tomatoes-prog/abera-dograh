"""Video must never negotiate media or reserve call resources in the voice image."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.webrtc_signaling import SignalingManager
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.transport_setup import create_webrtc_transport


@pytest.mark.parametrize("separator", ["\r\n", "\n"])
@pytest.mark.parametrize("port", ["9", "0"])
async def test_video_offer_is_rejected_before_paid_resources(separator, port):
    manager = SignalingManager()
    ws = AsyncMock()
    payload = {
        "pc_id": "video-peer",
        "sdp": separator.join(
            [
                "v=0",
                "m=audio 9 UDP/TLS/RTP/SAVPF 111",
                f"m=video {port} UDP/TLS/RTP/SAVPF 96",
                "",
            ]
        ),
        "type": "offer",
    }
    with (
        patch(
            "api.routes.webrtc_signaling.authorize_workflow_run_start",
            new_callable=AsyncMock,
        ) as quota,
        patch("api.routes.webrtc_signaling.call_concurrency") as concurrency,
        patch("api.routes.webrtc_signaling.SmallWebRTCConnection") as pc,
    ):
        await manager._handle_offer(
            ws,
            payload,
            1,
            2,
            SimpleNamespace(id=3),
            organization_id=4,
            connection_key="1:2:3:4",
            enforce_call_concurrency=True,
        )
        quota.assert_not_awaited()
        concurrency.acquire_org_slot.assert_not_called()
        pc.assert_not_called()
    assert (
        ws.send_json.await_args.args[0]["payload"]["error_type"]
        == "video_not_supported"
    )
    assert not manager._pipeline_tasks


async def test_existing_peer_cannot_add_video_through_renegotiation():
    manager = SignalingManager()
    ws = AsyncMock()
    peer = MagicMock()
    peer.renegotiate = AsyncMock()
    manager._peer_connections["peer"] = peer
    manager._peer_connection_owners["peer"] = "owner"
    await manager._handle_renegotiation(
        ws,
        {
            "pc_id": "peer",
            "sdp": "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n",
            "type": "offer",
        },
        "owner",
    )
    peer.renegotiate.assert_not_awaited()
    assert (
        ws.send_json.await_args.args[0]["payload"]["error_type"]
        == "video_not_supported"
    )


async def test_audio_and_data_channel_offer_is_accepted_by_media_guard():
    ws = AsyncMock()
    assert not await SignalingManager._reject_video_offer(
        ws,
        "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n",
    )
    ws.send_json.assert_not_awaited()


async def test_webrtc_transport_explicitly_disables_video():
    with patch(
        "api.services.pipecat.transport_setup.build_audio_out_mixer",
        AsyncMock(return_value=None),
    ):
        transport = await create_webrtc_transport(
            MagicMock(),
            1,
            AudioConfig(16000, 16000),
            is_realtime=True,
        )
    assert transport._params.audio_in_enabled
    assert transport._params.audio_out_enabled
    assert not transport._params.video_in_enabled
    assert not transport._params.video_out_enabled
