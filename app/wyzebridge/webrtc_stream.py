"""
WebRTC stream implementation for Wyze cameras via KVS.

This module provides WebRTC connectivity to Wyze cameras using Amazon Kinesis Video Streams,
piping video/audio to FFmpeg for RTSP output via MediaMTX.
"""

import asyncio
import contextlib
import os
import threading
import time
from subprocess import Popen, PIPE
from typing import Optional

from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder
from av import VideoFrame, AudioFrame

from wyzecam.api_models import WyzeAccount, WyzeCamera
from wyzebridge.wyze_api import WyzeApi
from wyzebridge.wyze_stream_options import WyzeStreamOptions
from wyzebridge.kvs_signaling import KvsSignalingClient
from wyzebridge.ffmpeg import get_webrtc_ffmpeg_cmd
from wyzebridge.logging import logger


# Stream states (compatible with old StreamStatus enum)
class StreamStatus:
    OFFLINE = -90
    STOPPING = -1
    DISABLED = 0
    STOPPED = 1
    CONNECTING = 2
    CONNECTED = 3
    INITIALIZING = -2


class WebRtcStream:
    """
    Manages WebRTC connection for a single camera.

    Implements the Stream protocol for compatibility with StreamManager.
    Each stream runs its own asyncio event loop in a dedicated thread.
    """

    __slots__ = (
        "api", "camera", "uri", "options", "user",
        "state", "start_time", "motion_ts",
        "loop_thread", "loop", "pc", "signaling",
        "ffmpeg_process", "video_pipe", "audio_pipe",
        "_stop_event", "_video_track", "_audio_track",
        "_reconnect_count"
    )

    def __init__(self, user: WyzeAccount, api: WyzeApi,
                 camera: WyzeCamera, options: WyzeStreamOptions):
        """
        Initialize WebRTC stream.

        Args:
            user: Wyze user account
            api: WyzeApi instance for signaling
            camera: Camera model from Wyze API
            options: Stream configuration options
        """
        self.api = api
        self.camera = camera
        self.uri = camera.name_uri
        self.options = options
        self.user = user

        # State management
        self.state = StreamStatus.STOPPED
        self.start_time = 0
        self.motion_ts = 0
        self._reconnect_count = 0

        # Asyncio management
        self.loop_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

        # WebRTC components
        self.pc: Optional[RTCPeerConnection] = None
        self.signaling: Optional[KvsSignalingClient] = None
        self._video_track = None
        self._audio_track = None

        # FFmpeg pipeline
        self.ffmpeg_process: Optional[Popen] = None
        self.video_pipe: Optional[str] = None
        self.audio_pipe: Optional[str] = None

    # Stream protocol properties

    @property
    def connected(self) -> bool:
        """Check if stream is connected."""
        return self.state == StreamStatus.CONNECTED

    @property
    def enabled(self) -> bool:
        """Check if stream is enabled (not disabled)."""
        return self.state != StreamStatus.DISABLED

    @property
    def motion(self) -> bool:
        """Check if motion detected recently (within 60s)."""
        return bool(self.motion_ts and time.time() - self.motion_ts < 60)

    # Stream protocol methods

    def init(self) -> bool:
        """
        MediaMTX Init event handler.

        Called when MediaMTX initializes the path.
        """
        logger.info(f"[{self.uri}] MediaMTX initializing WebRTC stream")
        self.state = StreamStatus.INITIALIZING
        return True

    def start(self) -> bool:
        """
        Start WebRTC connection.

        Launches asyncio event loop in dedicated thread.
        """
        if self.state not in {StreamStatus.STOPPED, StreamStatus.INITIALIZING}:
            logger.warning(f"[{self.uri}] Cannot start - already in state {self.state}")
            return False

        logger.info(f"[{self.uri}] Starting WebRTC stream")
        self.state = StreamStatus.CONNECTING
        self._stop_event.clear()

        # Start asyncio event loop in dedicated thread
        self.loop_thread = threading.Thread(
            target=self._run_event_loop,
            name=f"webrtc_{self.uri}",
            daemon=True
        )
        self.loop_thread.start()
        return True

    def stop(self) -> bool:
        """
        Stop WebRTC connection and cleanup.

        Returns:
            bool: True if stopped successfully
        """
        if self.state == StreamStatus.STOPPED:
            return True

        logger.info(f"[{self.uri}] Stopping WebRTC stream")
        self.state = StreamStatus.STOPPING
        self._stop_event.set()

        # Stop asyncio loop
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        # Wait for thread cleanup
        if self.loop_thread:
            with contextlib.suppress(ValueError, AttributeError, RuntimeError):
                self.loop_thread.join(timeout=5)
            self.loop_thread = None

        self.state = StreamStatus.STOPPED
        return True

    def enable(self) -> bool:
        """Enable stream."""
        if self.state == StreamStatus.DISABLED:
            self.state = StreamStatus.STOPPED
        return True

    def disable(self) -> bool:
        """Disable stream."""
        self.stop()
        self.state = StreamStatus.DISABLED
        return True

    def health_check(self) -> int:
        """
        Monitor connection state and reconnect if needed.

        Returns:
            int: Current stream state
        """
        if self.state == StreamStatus.CONNECTED:
            # Check if ffmpeg is still running
            if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
                logger.warning(f"[{self.uri}] FFmpeg died (exit code {self.ffmpeg_process.returncode})")
                self._handle_failure()
                return self.state

            # Check WebRTC connection state
            if self.pc and hasattr(self.pc, 'iceConnectionState'):
                ice_state = self.pc.iceConnectionState
                if ice_state in {"failed", "closed"}:
                    logger.warning(f"[{self.uri}] ICE connection {ice_state} - possible TURN credential expiration")
                    self._handle_failure()
                    return self.state
                elif ice_state == "disconnected":
                    # Allow brief disconnections but monitor
                    if time.time() - self.start_time > 300:  # If disconnected after 5+ mins
                        logger.warning(f"[{self.uri}] Extended disconnection detected")
                        # Don't fail immediately, but log for monitoring

        return self.state

    def _handle_failure(self):
        """Handle connection failure and reconnect if enabled."""
        self.stop()
        if self.options.reconnect:
            self._reconnect_count += 1
            if self._reconnect_count < 10:  # Max 10 reconnect attempts
                delay = min(2 ** self._reconnect_count, 60)  # Exponential backoff, max 60s
                logger.info(f"[{self.uri}] Reconnecting in {delay}s (attempt {self._reconnect_count})")
                time.sleep(delay)
                self.start()
            else:
                logger.error(f"[{self.uri}] Max reconnect attempts reached")

    def get_info(self, item: Optional[str] = None) -> dict:
        """
        Get stream information.

        Args:
            item: Specific info item to retrieve (optional)

        Returns:
            dict: Stream information
        """
        info = {
            "uri": self.uri,
            "nickname": self.camera.nickname,
            "state": self.state,
            "connected": self.connected,
            "enabled": self.enabled,
            "motion": self.motion,
            "uptime": int(time.time() - self.start_time) if self.start_time else 0,
            "reconnects": self._reconnect_count,
        }
        return info.get(item) if item else info

    def status(self) -> str:
        """Get status string."""
        state_map = {
            StreamStatus.OFFLINE: "offline",
            StreamStatus.STOPPING: "stopping",
            StreamStatus.DISABLED: "disabled",
            StreamStatus.STOPPED: "stopped",
            StreamStatus.CONNECTING: "connecting",
            StreamStatus.CONNECTED: "connected",
            StreamStatus.INITIALIZING: "initializing",
        }
        return state_map.get(self.state, "unknown")

    def send_cmd(self, cmd: str, payload: str | list | dict = "") -> dict:
        """
        Send command to camera.

        Note: WebRTC mode has limited command support (no TUTK connection).

        Args:
            cmd: Command name
            payload: Command payload

        Returns:
            dict: Command response
        """
        logger.warning(f"[{self.uri}] Camera commands not supported in WebRTC mode")
        return {"error": "Camera control not available in WebRTC-only mode", "command": cmd}

    # Asyncio event loop

    def _run_event_loop(self):
        """
        Thread entry point - runs asyncio event loop.

        Creates new event loop and runs WebRTC connection coroutine.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._connect_webrtc())
        except Exception as ex:
            logger.error(f"[{self.uri}] WebRTC error: {ex}", exc_info=True)
            self.state = StreamStatus.STOPPED
        finally:
            self.loop.close()
            self.loop = None

    async def _connect_webrtc(self):
        """
        Establish WebRTC connection to camera via KVS.

        Main async coroutine that coordinates signaling, peer connection,
        and media handling.
        """
        try:
            # 1. Get KVS signaling credentials
            logger.info(f"[{self.uri}] Getting KVS signaling credentials")
            signal_data = self.api.get_kvs_signal(self.uri)
            if signal_data.get("result") != "ok":
                raise Exception(f"Failed to get signaling: {signal_data.get('result')}")
            
            logger.debug(f"[{self.uri}] Signal data: signalingUrl={signal_data.get('signalingUrl', '')[:100]}...")
            logger.debug(f"[{self.uri}] Signal data: ClientId={signal_data.get('ClientId')}")

            # 2. Setup signaling client
            self.signaling = KvsSignalingClient(
                signal_data["signalingUrl"],
                signal_data["ClientId"],
                signal_data["signalToken"]
            )
            await self.signaling.connect()

            # 3. Create RTCPeerConnection with ICE servers from KVS
            ice_servers = []
            for server in signal_data.get("servers", []):
                ice_server_config = {}
                if "urls" in server:
                    ice_server_config["urls"] = server["urls"]
                if "username" in server:
                    ice_server_config["username"] = server["username"]
                if "credential" in server:
                    ice_server_config["credential"] = server["credential"]
                ice_servers.append(RTCIceServer(**ice_server_config))
                logger.debug(f"[{self.uri}] ICE server: {server.get('urls', 'no url')}")
            
            # Add Google STUN as fallback if no servers provided
            if not ice_servers:
                logger.warning(f"[{self.uri}] No ICE servers from API, using Google STUN")
                ice_servers.append(RTCIceServer(urls="stun:stun.l.google.com:19302"))
            
            logger.info(f"[{self.uri}] Configured {len(ice_servers)} ICE servers")
            configuration = RTCConfiguration(iceServers=ice_servers)
            self.pc = RTCPeerConnection(configuration=configuration)

            # 4. Add transceivers with SENDRECV direction (CRITICAL for KVS!)
            # This was the fix in commit 3f1c642 for browser client
            self.pc.addTransceiver("video", direction="sendrecv")
            self.pc.addTransceiver("audio", direction="sendrecv")

            # 5. Setup event handlers
            _media_started = False
            
            @self.pc.on("track")
            def on_track(track):
                nonlocal _media_started
                logger.info(f"[{self.uri}] Received {track.kind} track")
                if track.kind == "video":
                    self._video_track = track
                elif track.kind == "audio" and self.options.audio:
                    self._audio_track = track

                # Start media handling when we have required tracks (only once)
                if not _media_started and self._video_track and (not self.options.audio or self._audio_track):
                    _media_started = True
                    asyncio.create_task(self._handle_media_tracks())

            @self.pc.on("icecandidate")
            async def on_ice_candidate(candidate):
                if candidate:
                    logger.debug(f"[{self.uri}] Local ICE candidate: {candidate.candidate[:50]}...")
                    await self.signaling.send_ice_candidate({
                        "candidate": candidate.candidate,
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex
                    })

            @self.pc.on("iceconnectionstatechange")
            async def on_ice_state_change():
                if not self.pc:
                    return
                state = self.pc.iceConnectionState
                conn_state = self.pc.connectionState if hasattr(self.pc, 'connectionState') else 'unknown'
                logger.info(f"[{self.uri}] ICE state: {state}, Connection state: {conn_state}")
                if state == "connected":
                    self.state = StreamStatus.CONNECTED
                    self.start_time = time.time()
                    self._reconnect_count = 0  # Reset reconnect counter on success
                elif state == "checking":
                    logger.debug(f"[{self.uri}] ICE checking - negotiating connection...")
                elif state == "disconnected":
                    logger.warning(f"[{self.uri}] ICE disconnected - connection may recover")
                elif state in {"failed", "closed"}:
                    logger.error(f"[{self.uri}] ICE connection {state} - TURN credentials may have expired")
                    await self._cleanup()

            @self.pc.on("connectionstatechange")
            async def on_conn_state_change():
                if not self.pc:
                    return
                state = self.pc.connectionState
                logger.info(f"[{self.uri}] 🔗 Connection state: {state}")


            # 6. Setup signaling callbacks
            async def on_answer(sdp_str):
                logger.info(f"[{self.uri}] Received SDP answer")
                answer = RTCSessionDescription(sdp=sdp_str, type="answer")
                await self.pc.setRemoteDescription(answer)

            async def on_remote_ice_candidate(candidate_dict):
                try:
                    candidate_str = candidate_dict.get("candidate")
                    sdp_mid = candidate_dict.get("sdpMid")
                    sdp_mline_index = candidate_dict.get("sdpMLineIndex")
                    logger.info(f"[{self.uri}] Received remote ICE candidate: {candidate_str[:50] if candidate_str else 'None'}...")
                    if candidate_str:
                        from aiortc.sdp import candidate_from_sdp
                        candidate = candidate_from_sdp(candidate_str)
                        candidate.sdpMid = sdp_mid
                        candidate.sdpMLineIndex = sdp_mline_index
                        await self.pc.addIceCandidate(candidate)
                        logger.info(f"[{self.uri}] ✅ Added remote ICE candidate")
                except Exception as ex:
                    logger.error(f"[{self.uri}] Error adding ICE candidate: {ex}", exc_info=True)


            self.signaling.on_answer = on_answer
            self.signaling.on_ice_candidate = on_remote_ice_candidate

            # 7. Create and send SDP offer
            logger.info(f"[{self.uri}] Creating SDP offer")
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            await self.signaling.send_offer(self.pc.localDescription.sdp)

            # 8. Wait until stopped
            while not self._stop_event.is_set():
                await asyncio.sleep(1)

        except Exception as ex:
            logger.error(f"[{self.uri}] Connection failed: {ex}", exc_info=True)
            self.state = StreamStatus.STOPPED
        finally:
            await self._cleanup()

    async def _handle_media_tracks(self):
        """
        Handle incoming video/audio tracks.

        Starts FFmpeg and writes frames to named pipes.
        """
        try:
            # Create named pipes
            self.video_pipe = f"/tmp/{self.uri}_video.pipe"
            if self.options.audio and self._audio_track:
                self.audio_pipe = f"/tmp/{self.uri}_audio.pipe"

            # Create pipes
            with contextlib.suppress(FileExistsError):
                os.mkfifo(self.video_pipe)
            if self.audio_pipe:
                with contextlib.suppress(FileExistsError):
                    os.mkfifo(self.audio_pipe)

            # Start FFmpeg (will block waiting to read from pipes)
            self._start_ffmpeg()

            # Write tracks to pipes (this will unblock FFmpeg)
            tasks = [self._write_video_track()]
            if self.audio_pipe and self._audio_track:
                tasks.append(self._write_audio_track())

            await asyncio.gather(*tasks)

        except Exception as ex:
            logger.error(f"[{self.uri}] Media handling error: {ex}", exc_info=True)
            self._handle_failure()

    async def _write_video_track(self):
        """Write video frames to named pipe after encoding."""
        logger.info(f"[{self.uri}] Starting video track handler")

        if not self._video_track:
            logger.error(f"[{self.uri}] No video track available!")
            return

        frame_count = 0
        last_log_time = 0
        import time as time_module
        import av

        codec = None
        try:
            # Wait for first frame to get dimensions
            logger.info(f"[{self.uri}] Waiting for first video frame to initialize codec...")
            first_frame = await asyncio.wait_for(self._video_track.recv(), timeout=10.0)

            # Initialize H264 encoder
            codec = av.CodecContext.create("libx264", "w")
            codec.width = first_frame.width
            codec.height = first_frame.height
            codec.pix_fmt = "yuv420p"
            codec.bit_rate = self.options.bitrate * 1000  # Convert kbps to bps
            codec.time_base = "1/30"  # 30fps
            codec.framerate = "30/1"
            codec.gop_size = 30  # One keyframe per second at 30fps
            codec.options = {
                "preset": "ultrafast",
                "tune": "zerolatency",
                "profile": "baseline"
            }
            codec.open()

            logger.info(f"[{self.uri}] H264 encoder initialized: {first_frame.width}x{first_frame.height}, {self.options.bitrate}kbps, gop={codec.gop_size}")

            with open(self.video_pipe, "wb") as pipe:
                # Process first frame
                frame_count += 1
                packets = codec.encode(first_frame)
                for packet in packets:
                    pipe.write(bytes(packet))
                pipe.flush()

                last_log_time = time_module.time()
                logger.info(f"[{self.uri}] ✅ First video frame encoded and written")

                # Process remaining frames
                while not self._stop_event.is_set():
                    try:
                        frame = await asyncio.wait_for(self._video_track.recv(), timeout=5.0)
                        frame_count += 1

                        # Encode and write
                        packets = codec.encode(frame)
                        for packet in packets:
                            pipe.write(bytes(packet))
                        pipe.flush()

                        # Log every second
                        now = time_module.time()
                        if now - last_log_time >= 1.0:
                            logger.info(f"[{self.uri}] Video encoding: frame={frame_count}, size={frame.width}x{frame.height}")
                            last_log_time = now

                    except asyncio.TimeoutError:
                        logger.warning(f"[{self.uri}] Video frame timeout (no frames for 5s)")
                        continue
                    except Exception as ex:
                        if not self._stop_event.is_set():
                            logger.error(f"[{self.uri}] Video frame error: {ex}", exc_info=True)
                        break

                # Flush encoder
                if codec:
                    packets = codec.encode(None)
                    for packet in packets:
                        pipe.write(bytes(packet))
                    pipe.flush()

        except asyncio.TimeoutError:
            logger.error(f"[{self.uri}] Timeout waiting for first video frame")
        except Exception as ex:
            if not self._stop_event.is_set():
                logger.error(f"[{self.uri}] Video track handler error: {ex}", exc_info=True)

        logger.info(f"[{self.uri}] Video track handler stopped after {frame_count} frames")

    async def _write_audio_track(self):
        """Write audio frames to named pipe after encoding."""
        logger.info(f"[{self.uri}] Starting audio track handler")
        import av
        codec = av.CodecContext.create("aac", "w")
        # Wyze standard: 16kHz mono or 8kHz mono
        codec.sample_rate = 16000
        codec.channels = 1
        codec.layout = "mono"

        try:
            with open(self.audio_pipe, "wb") as pipe:
                while not self._stop_event.is_set():
                    try:
                        frame = await asyncio.wait_for(self._audio_track.recv(), timeout=5.0)
                        # Encode AudioFrame to packets
                        packets = codec.encode(frame)
                        for packet in packets:
                            pipe.write(packet.to_bytes())
                        pipe.flush()
                    except asyncio.TimeoutError:
                        continue
                    except Exception as ex:
                        if not self._stop_event.is_set():
                            logger.error(f"[{self.uri}] Audio frame error: {ex}")
                        break
                # Flush codec
                packets = codec.encode(None)
                for packet in packets:
                    pipe.write(packet.to_bytes())
                pipe.flush()
        except Exception as ex:
            if not self._stop_event.is_set():
                logger.error(f"[{self.uri}] Audio track write error: {ex}")

    def _start_ffmpeg(self):
        """
        Start FFmpeg subprocess.

        Reads from named pipes and outputs RTSP to MediaMTX.
        """
        cmd = get_webrtc_ffmpeg_cmd(self.uri, has_audio=bool(self.audio_pipe))
        logger.info(f"[{self.uri}] Starting FFmpeg: {' '.join(cmd)}")

        self.ffmpeg_process = Popen(cmd, stdout=PIPE, stderr=PIPE)

    async def _cleanup(self):
        """Cleanup WebRTC and FFmpeg resources."""
        logger.info(f"[{self.uri}] Cleaning up resources")

        # Close peer connection
        if self.pc:
            await self.pc.close()
            self.pc = None

        # Close signaling
        if self.signaling:
            await self.signaling.close()
            self.signaling = None

        # Kill FFmpeg
        if self.ffmpeg_process:
            self.ffmpeg_process.terminate()
            try:
                self.ffmpeg_process.wait(timeout=3)
            except:
                self.ffmpeg_process.kill()
            self.ffmpeg_process = None

        # Remove named pipes
        for pipe in [self.video_pipe, self.audio_pipe]:
            if pipe and os.path.exists(pipe):
                with contextlib.suppress(OSError):
                    os.remove(pipe)

        self.video_pipe = None
        self.audio_pipe = None
        self._video_track = None
        self._audio_track = None

        if self.state not in {StreamStatus.STOPPED, StreamStatus.STOPPING}:
            self.state = StreamStatus.STOPPED
