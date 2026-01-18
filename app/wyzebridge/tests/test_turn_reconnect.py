import asyncio
import pytest
from unittest import mock

# Import the class under test
from wyzebridge.webrtc_stream import WebRtcStream, StreamStatus

# Minimal dummy objects
class DummyApi:
    def get_kvs_signal(self, uri):
        return {"result": "ok", "signalingUrl": "ws://example", "ClientId": "id", "signalToken": "token", "servers": []}

class DummyCamera:
    def __init__(self):
        self.name_uri = "testcam"
        self.nickname = "TestCam"
        self.product_model = "model"
        self.webrtc_support = True

class DummyUser:
    pass

class DummyOptions:
    def __init__(self):
        self.audio = True
        self.bitrate = 180
        self.quality = "hd180"
        self.reconnect = True

@pytest.mark.asyncio
async def test_restart_stream_calls_cleanup_and_start(monkeypatch):
    # Create a WebRtcStream instance with dummy dependencies
    stream = WebRtcStream(user=DummyUser(), api=DummyApi(), camera=DummyCamera(), options=DummyOptions())
    # Mock internal methods
    cleanup_mock = mock.AsyncMock()
    start_mock = mock.Mock()
    monkeypatch.setattr(stream, "_cleanup", cleanup_mock)
    monkeypatch.setattr(stream, "start", start_mock)
    # Call the restart method
    await stream._restart_stream()
    # Verify that cleanup was awaited and start was called
    cleanup_mock.assert_awaited_once()
    start_mock.assert_called_once()
    # Ensure state was set to STOPPED
    assert stream.state == StreamStatus.STOPPED
