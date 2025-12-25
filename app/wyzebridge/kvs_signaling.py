"""
Wyze KVS WebSocket signaling client.

This module handles WebSocket-based signaling with Wyze's Amazon Kinesis Video Streams
(KVS) service for WebRTC connections.
"""

import asyncio
import base64
import json
from typing import Callable, Optional
from urllib.parse import quote

import websockets
from websockets.client import WebSocketClientProtocol

from wyzebridge.logging import logger


class KvsSignalingClient:
    """
    Manages WebSocket signaling with Wyze KVS.

    Handles SDP offer/answer exchange and ICE candidate trickle for WebRTC connections.
    """

    __slots__ = "url", "client_id", "ws", "on_answer", "on_ice_candidate", "_receive_task"

    def __init__(self, signaling_url: str, client_id: str, token: str):
        """
        Initialize KVS signaling client.

        Args:
            signaling_url: WebSocket URL from Wyze API
            client_id: Client ID (phone_id) for authentication
            token: Signal token for authentication
        """
        self.client_id = client_id  # Store for use in messages
        
        # The signalingUrl from Wyze is a pre-signed AWS KVS URL that already contains
        # all necessary authentication. Don't add ClientId/signalToken as they may break it.
        # If the URL doesn't contain auth params, add them.
        if "X-Amz-" in signaling_url:
            # AWS pre-signed URL - use as-is
            self.url = signaling_url
            logger.info(f"[KVS] Using AWS pre-signed URL")
        else:
            # Wyze custom signaling - add auth params
            sep = "&" if "?" in signaling_url else "?"
            self.url = f"{signaling_url}{sep}ClientId={quote(client_id, safe='')}&signalToken={quote(token, safe='')}"
            logger.info(f"[KVS] Using Wyze signaling with params")
        self.ws: Optional[WebSocketClientProtocol] = None
        self.on_answer: Optional[Callable] = None
        self.on_ice_candidate: Optional[Callable] = None
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Establish WebSocket connection to KVS."""
        logger.info(f"[KVS] Connecting to signaling server")
        logger.debug(f"[KVS] URL: {self.url}")
        self.ws = await websockets.connect(
            self.url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5
        )
        logger.info("[KVS] WebSocket connected")

        # Start receiving messages in background
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def send_offer(self, sdp: str):
        """
        Send SDP offer to KVS.

        Args:
            sdp: SDP offer string from RTCPeerConnection
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Wyze KVS expects the payload to be a base64-encoded JSON object
        payload = {"type": "offer", "sdp": sdp}
        encoded_payload = base64.b64encode(json.dumps(payload).encode()).decode()
        
        msg = {
            "action": "SDP_OFFER",
            "messagePayload": encoded_payload,
            "recipientClientId": self.client_id
        }
        logger.info(f"[KVS] Sending SDP offer to {self.client_id}")
        await self.ws.send(json.dumps(msg))

    async def send_ice_candidate(self, candidate: dict):
        """
        Send ICE candidate to KVS.

        Args:
            candidate: ICE candidate dictionary from RTCPeerConnection
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        # Wyze KVS expects the payload to be a base64-encoded JSON object
        encoded_payload = base64.b64encode(json.dumps(candidate).encode()).decode()
        
        msg = {
            "action": "ICE_CANDIDATE",
            "messagePayload": encoded_payload,
            "recipientClientId": self.client_id
        }
        logger.debug(f"[KVS] Sending ICE candidate: {candidate.get('candidate', '')[:50]}...")
        await self.ws.send(json.dumps(msg))

    async def _receive_loop(self):
        """Process incoming signaling messages."""
        try:
            async for message in self.ws:
                try:
                    # Message can be string (JSON) or bytes
                    if isinstance(message, bytes):
                        message = message.decode('utf-8')
                    
                    # Skip empty messages (ping/pong frames, etc.)
                    if not message or not message.strip():
                        logger.debug("[KVS] Received empty message, skipping")
                        continue
                    
                    logger.debug(f"[KVS] Raw message received: {message[:200]}...")
                    
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = message  # Already a dict
                    await self._handle_message(data)
                except json.JSONDecodeError as ex:
                    logger.warning(f"[KVS] Failed to parse message: {ex}")
                    logger.warning(f"[KVS] Raw message content: '{message[:200] if message else 'None'}'")
                except Exception as ex:
                    logger.error(f"[KVS] Error handling message: {ex}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("[KVS] WebSocket connection closed")
        except Exception as ex:
            logger.error(f"[KVS] Receive loop error: {ex}")

    async def _handle_message(self, data: dict):
        """
        Handle incoming WebSocket message.

        Args:
            data: Parsed JSON message from KVS
        """
        msg_type = data.get("messageType")
        logger.debug(f"[KVS] Received message type: {msg_type}")

        if msg_type == "SDP_ANSWER":
            logger.info("[KVS] Received SDP answer")
            if self.on_answer:
                # Extract and decode SDP from messagePayload (base64 encoded JSON)
                try:
                    encoded_payload = data.get("messagePayload")
                    if encoded_payload:
                        decoded = base64.b64decode(encoded_payload).decode('utf-8')
                        payload = json.loads(decoded)
                        sdp = payload.get("sdp") if isinstance(payload, dict) else decoded
                        await self.on_answer(sdp)
                    else:
                        logger.error("[KVS] SDP answer missing messagePayload")
                except Exception as ex:
                    logger.error(f"[KVS] Error decoding SDP answer: {ex}")

        elif msg_type == "ICE_CANDIDATE":
            logger.debug("[KVS] Received ICE candidate")
            if self.on_ice_candidate:
                # Parse candidate from messagePayload (base64 encoded JSON)
                try:
                    encoded_payload = data.get("messagePayload")
                    if encoded_payload:
                        decoded = base64.b64decode(encoded_payload).decode('utf-8')
                        candidate = json.loads(decoded)
                        await self.on_ice_candidate(candidate)
                except Exception as ex:
                    logger.error(f"[KVS] Failed to parse ICE candidate: {ex}")

        elif msg_type == "STATUS_RESPONSE":
            # Status acknowledgments from KVS
            logger.debug(f"[KVS] Status: {data.get('statusResponse', 'unknown')}")

        else:
            logger.warning(f"[KVS] Unknown message type: {msg_type}")

    async def close(self):
        """Close WebSocket connection and cleanup."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None
            logger.info("[KVS] WebSocket closed")
