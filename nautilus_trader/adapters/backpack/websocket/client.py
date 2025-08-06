# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""Backpack WebSocket client implementation."""

import asyncio
import json
import time
from collections import deque
from typing import Any, Callable

import aiohttp

from nautilus_trader.adapters.backpack.common.auth import sign_request
from nautilus_trader.adapters.backpack.common.constants import (
    BACKPACK_WS_URL_PROD,
    BACKPACK_WS_URL_TESTNET,
)
from nautilus_trader.common.component import Logger
from nautilus_trader.core.datetime import millis_to_nanos


class BackpackWebSocketClient:
    """
    Provides a WebSocket client for the Backpack exchange.

    Parameters
    ----------
    api_key : str, optional
        The API key for authentication.
    api_secret : str, optional
        The API secret for authentication.
    testnet : bool, default False
        Whether to use the testnet environment.
    handler : Callable, optional
        The message handler callback.
    logger : Logger, optional
        The logger instance.

    """

    MAX_SUBSCRIPTIONS_PER_CONNECTION = 200  # Backpack limit

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        handler: Callable[[dict], None] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = BACKPACK_WS_URL_TESTNET if testnet else BACKPACK_WS_URL_PROD
        self._handler = handler
        self._log = logger or Logger(name=self.__class__.__name__)
        
        # WebSocket state
        self._session: aiohttp.ClientSession | None = None
        self._connections: dict[int, aiohttp.ClientWebSocketResponse] = {}  # Connection pool
        self._running = False
        self._reconnect_tasks: dict[int, asyncio.Task] = {}
        
        # Subscription management
        self._subscriptions: dict[int, set[str]] = {}  # Connection ID -> subscriptions
        self._stream_to_connection: dict[str, int] = {}  # Stream -> connection ID
        self._authenticated = False
        self._next_connection_id = 0
        
        # Message sequence tracking
        self._last_update_ids: dict[str, int] = {}  # Stream -> last update ID
        
        # Heartbeat
        self._heartbeat_task: asyncio.Task | None = None
        self._last_pong: int = 0
        
        # Latency monitoring and metrics
        self._latency_buffer: deque[float] = deque(maxlen=1000)  # Rolling window of latencies
        self._message_count: int = 0
        self._bytes_received: int = 0
        self._bytes_sent: int = 0
        self._error_count: int = 0
        self._reconnect_count: int = 0
        self._last_metrics_log_time: float = time.time()
        self._message_timestamps: dict[str, float] = {}  # For tracking round-trip times

    async def connect(self) -> None:
        """Connect to the WebSocket server."""
        if self._running:
            self._log.warning("WebSocket client already running")
            return
            
        self._running = True
        self._session = aiohttp.ClientSession()
        
        # Create initial connection
        await self._create_connection(0)

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._running = False
        
        # Cancel all tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
            
        for task in self._reconnect_tasks.values():
            task.cancel()
        self._reconnect_tasks.clear()
        
        # Close all WebSocket connections
        for conn_id, ws in self._connections.items():
            await ws.close()
        self._connections.clear()
        
        # Close session
        if self._session:
            await self._session.close()
            self._session = None
            
        self._log.info("All WebSocket connections disconnected")

    async def _create_connection(self, conn_id: int) -> None:
        """Create a new WebSocket connection."""
        if not self._session:
            self._session = aiohttp.ClientSession()
            
        try:
            ws = await self._session.ws_connect(
                self._base_url,
                heartbeat=30,
                receive_timeout=60,
            )
            
            self._connections[conn_id] = ws
            self._subscriptions[conn_id] = set()
            
            self._log.info(f"WebSocket connection {conn_id} established to {self._base_url}")
            
            # Start message handler for this connection
            asyncio.create_task(self._handle_messages(conn_id))
            
            # Start heartbeat if this is the first connection
            if conn_id == 0 and not hasattr(self, '_heartbeat_task'):
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Authenticate if credentials provided
            if self._api_key and self._api_secret:
                await self._authenticate_connection(conn_id)
                
        except Exception as e:
            self._log.error(f"Failed to create connection {conn_id}: {e}")
            self._reconnect_tasks[conn_id] = asyncio.create_task(self._reconnect_connection(conn_id))

    async def _reconnect_connection(self, conn_id: int) -> None:
        """Reconnect a specific WebSocket connection."""
        if not self._running:
            return
            
        self._log.info(f"Attempting to reconnect connection {conn_id}...")
        self._reconnect_count += 1
        
        # Close existing connection
        if conn_id in self._connections:
            await self._connections[conn_id].close()
            del self._connections[conn_id]
        
        # Save subscriptions for restoration
        saved_subs = self._subscriptions.get(conn_id, set()).copy()
        
        # Exponential backoff
        delay = 1
        max_delay = 60
        
        while self._running:
            try:
                await asyncio.sleep(delay)
                await self._create_connection(conn_id)
                
                # Restore subscriptions for this connection
                for stream in saved_subs:
                    await self._subscribe_on_connection(conn_id, stream)
                    
                self._log.info(f"Connection {conn_id} reconnected successfully")
                break
                
            except Exception as e:
                self._log.error(f"Reconnection {conn_id} failed: {e}")
                delay = min(delay * 2, max_delay)

    async def _authenticate_connection(self, conn_id: int) -> None:
        """Authenticate a specific WebSocket connection."""
        if not self._api_key or not self._api_secret:
            return
            
        # Generate signature
        timestamp = int(asyncio.get_event_loop().time() * 1000)
        window = 5000
        
        signature_str = f"instruction=subscribe&timestamp={timestamp}&window={window}"
        signature = sign_request(
            api_secret=self._api_secret,
            signature_str=signature_str,
        )
        
        # Per Backpack docs, authentication uses subscription format
        auth_message = {
            "method": "SUBSCRIBE",
            "params": ["account.orderUpdate"],
            "signature": [self._api_key, signature, str(timestamp), str(window)],
        }
        
        await self._send_message_on_connection(conn_id, auth_message)
        self._log.info(f"Authentication sent on connection {conn_id}")

    async def _handle_messages(self, conn_id: int) -> None:
        """Handle incoming WebSocket messages for a specific connection."""
        ws = self._connections.get(conn_id)
        if not ws:
            return
            
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        # Track metrics
                        receive_time = time.time()
                        self._message_count += 1
                        self._bytes_received += len(msg.data)
                        
                        data = json.loads(msg.data)
                        
                        # Track latency for responses to our requests
                        if "id" in data and data["id"] in self._message_timestamps:
                            latency = (receive_time - self._message_timestamps[data["id"]]) * 1000  # ms
                            self._latency_buffer.append(latency)
                            del self._message_timestamps[data["id"]]
                        
                        await self._process_message(conn_id, data)
                        
                        # Log metrics periodically
                        await self._log_metrics_if_needed()
                        
                    except json.JSONDecodeError as e:
                        self._error_count += 1
                        self._log.error(f"Failed to parse message on connection {conn_id}: {e}")
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self._error_count += 1
                    self._log.error(f"WebSocket error on connection {conn_id}: {ws.exception()}")
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self._log.warning(f"WebSocket connection {conn_id} closed")
                    break
                    
        except Exception as e:
            self._error_count += 1
            self._log.error(f"Error handling messages on connection {conn_id}: {e}")
            
        # Reconnect if still running
        if self._running:
            self._reconnect_tasks[conn_id] = asyncio.create_task(self._reconnect_connection(conn_id))

    async def _process_message(self, conn_id: int, data: dict) -> None:
        """Process a WebSocket message from a specific connection."""
        # Handle different message types
        if "stream" in data:
            # Market data stream - validate sequence if applicable
            stream = data.get("stream", "")
            if await self._validate_sequence(stream, data):
                await self._handle_stream_message(data)
            
        elif "result" in data:
            # Response to subscription
            self._log.debug(f"Subscription response on connection {conn_id}: {data}")
            
        elif "error" in data:
            # Error message
            self._log.error(f"WebSocket error on connection {conn_id}: {data}")
            
        elif "pong" in data:
            # Pong response
            self._last_pong = int(asyncio.get_event_loop().time() * 1000)
            
        else:
            # Pass to handler
            if self._handler:
                self._handler(data)

    async def _handle_stream_message(self, data: dict) -> None:
        """Handle a stream message."""
        stream = data.get("stream", "")
        payload = data.get("data", {})
        
        # Add timestamp if not present
        if "timestamp" not in payload:
            payload["timestamp"] = int(asyncio.get_event_loop().time() * 1000)
        
        # Convert to nanoseconds
        if "timestamp" in payload:
            payload["ts_event"] = millis_to_nanos(payload["timestamp"])
        
        # Add stream type
        payload["stream"] = stream
        
        # Call handler
        if self._handler:
            self._handler(payload)

    async def _handle_method_response(self, data: dict) -> None:
        """Handle a method response."""
        method = data.get("method", "")
        result = data.get("result", {})
        
        if method == "auth":
            if result.get("status") == "success":
                self._authenticated = True
                self._log.info("WebSocket authenticated successfully")
            else:
                self._log.error(f"Authentication failed: {result}")
                
        elif method == "subscribe":
            if result.get("status") == "success":
                self._log.info(f"Subscribed to {result.get('stream')}")
            else:
                self._log.error(f"Subscription failed: {result}")
                
        elif method == "unsubscribe":
            if result.get("status") == "success":
                self._log.info(f"Unsubscribed from {result.get('stream')}")
            else:
                self._log.error(f"Unsubscription failed: {result}")

    async def _send_message_on_connection(self, conn_id: int, message: dict) -> None:
        """Send a message on a specific WebSocket connection."""
        ws = self._connections.get(conn_id)
        if not ws:
            self._log.warning(f"Connection {conn_id} not available")
            return
            
        try:
            # Add message ID for latency tracking if not present
            if "id" not in message:
                message["id"] = str(int(time.time() * 1000000))  # microsecond precision
            
            # Track send time for latency measurement
            self._message_timestamps[message["id"]] = time.time()
            
            msg_str = json.dumps(message)
            self._bytes_sent += len(msg_str)
            await ws.send_str(msg_str)
        except Exception as e:
            self._error_count += 1
            self._log.error(f"Failed to send message on connection {conn_id}: {e}")
            self._reconnect_tasks[conn_id] = asyncio.create_task(self._reconnect_connection(conn_id))

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages to all connections."""
        while self._running:
            try:
                await asyncio.sleep(30)
                
                # Send ping to all connections
                ping_msg = {"ping": int(asyncio.get_event_loop().time() * 1000)}
                for conn_id in list(self._connections.keys()):
                    await self._send_message_on_connection(conn_id, ping_msg)
                
                # Check for stale connection
                if self._last_pong > 0:
                    elapsed = int(asyncio.get_event_loop().time() * 1000) - self._last_pong
                    if elapsed > 90000:  # 90 seconds
                        self._log.warning("Connections appear stale, checking all...")
                        for conn_id in list(self._connections.keys()):
                            if conn_id not in self._reconnect_tasks:
                                self._reconnect_tasks[conn_id] = asyncio.create_task(
                                    self._reconnect_connection(conn_id)
                                )
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Heartbeat error: {e}")

    async def _validate_sequence(self, stream: str, data: dict) -> bool:
        """Validate message sequence for depth updates."""
        if "depth" not in stream:
            return True  # Only validate depth streams
            
        # Get update IDs from the message
        first_update = data.get("data", {}).get("U")
        last_update = data.get("data", {}).get("u")
        
        if first_update is None or last_update is None:
            return True  # No sequence info
            
        # Check sequence
        if stream in self._last_update_ids:
            expected = self._last_update_ids[stream] + 1
            if first_update != expected:
                self._log.warning(
                    f"Sequence gap detected in {stream}: expected {expected}, got {first_update}"
                )
                # Could trigger a snapshot request here
                return False
                
        self._last_update_ids[stream] = last_update
        return True

    async def subscribe(self, stream: str) -> None:
        """
        Subscribe to a data stream.
        
        Parameters
        ----------
        stream : str
            The stream name in Backpack format (e.g., "ticker.SOL_USDC").
            
        """
        # Find or create a connection with capacity
        conn_id = await self._get_available_connection()
        
        # Subscribe on the selected connection
        await self._subscribe_on_connection(conn_id, stream)
    
    async def _get_available_connection(self) -> int:
        """Get a connection with available subscription capacity."""
        # Find existing connection with capacity
        for conn_id, subs in self._subscriptions.items():
            if len(subs) < self.MAX_SUBSCRIPTIONS_PER_CONNECTION:
                return conn_id
                
        # Need to create a new connection
        conn_id = self._next_connection_id
        self._next_connection_id += 1
        await self._create_connection(conn_id)
        return conn_id
    
    async def _subscribe_on_connection(self, conn_id: int, stream: str) -> None:
        """Subscribe to a stream on a specific connection."""
        if conn_id not in self._connections:
            self._log.warning(f"Connection {conn_id} not available for subscription")
            return
            
        # Track subscription
        self._subscriptions[conn_id].add(stream)
        self._stream_to_connection[stream] = conn_id
        
        # Send subscription message (Backpack format)
        message = {
            "method": "SUBSCRIBE",
            "params": [stream],
        }
        
        # Add signature for private streams
        if stream.startswith("account."):
            if self._api_key and self._api_secret:
                timestamp = int(asyncio.get_event_loop().time() * 1000)
                window = 5000
                signature_str = f"instruction=subscribe&timestamp={timestamp}&window={window}"
                signature = sign_request(
                    api_secret=self._api_secret,
                    signature_str=signature_str,
                )
                message["signature"] = [self._api_key, signature, str(timestamp), str(window)]
        
        await self._send_message_on_connection(conn_id, message)

    async def unsubscribe(self, stream: str) -> None:
        """
        Unsubscribe from a data stream.
        
        Parameters
        ----------
        stream : str
            The stream name.
            
        """
        # Find the connection for this stream
        conn_id = self._stream_to_connection.get(stream)
        if conn_id is None:
            self._log.warning(f"Stream {stream} not found in subscriptions")
            return
            
        # Remove from tracking
        if conn_id in self._subscriptions:
            self._subscriptions[conn_id].discard(stream)
        del self._stream_to_connection[stream]
        
        # Send unsubscribe message
        message = {
            "method": "UNSUBSCRIBE",
            "params": [stream],
        }
        
        await self._send_message_on_connection(conn_id, message)
    
    async def _log_metrics_if_needed(self) -> None:
        """Log metrics periodically."""
        current_time = time.time()
        if current_time - self._last_metrics_log_time >= 60:  # Log every 60 seconds
            self._last_metrics_log_time = current_time
            
            # Calculate statistics
            avg_latency = sum(self._latency_buffer) / len(self._latency_buffer) if self._latency_buffer else 0
            min_latency = min(self._latency_buffer) if self._latency_buffer else 0
            max_latency = max(self._latency_buffer) if self._latency_buffer else 0
            
            # Calculate message rate
            elapsed = current_time - (current_time - 60)
            msg_rate = self._message_count / elapsed if elapsed > 0 else 0
            
            self._log.info(
                f"WebSocket Metrics: "
                f"Messages={self._message_count}, "
                f"Rate={msg_rate:.1f}/s, "
                f"Latency(ms): avg={avg_latency:.2f}, min={min_latency:.2f}, max={max_latency:.2f}, "
                f"Bytes: rx={self._bytes_received:,}, tx={self._bytes_sent:,}, "
                f"Errors={self._error_count}, "
                f"Reconnects={self._reconnect_count}, "
                f"Connections={len(self._connections)}"
            )
    
    def get_metrics(self) -> dict[str, Any]:
        """
        Get current WebSocket metrics.
        
        Returns
        -------
        dict[str, Any]
            Dictionary containing current metrics.
            
        """
        latencies = list(self._latency_buffer)
        return {
            "message_count": self._message_count,
            "bytes_received": self._bytes_received,
            "bytes_sent": self._bytes_sent,
            "error_count": self._error_count,
            "reconnect_count": self._reconnect_count,
            "connection_count": len(self._connections),
            "subscription_count": sum(len(subs) for subs in self._subscriptions.values()),
            "latency_ms": {
                "avg": sum(latencies) / len(latencies) if latencies else 0,
                "min": min(latencies) if latencies else 0,
                "max": max(latencies) if latencies else 0,
                "samples": len(latencies),
            },
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self._latency_buffer.clear()
        self._message_count = 0
        self._bytes_received = 0
        self._bytes_sent = 0
        self._error_count = 0
        self._reconnect_count = 0
        self._message_timestamps.clear()

    async def subscribe_ticker(self, symbol: str) -> None:
        """Subscribe to ticker updates for a symbol."""
        await self.subscribe(f"ticker.{symbol}")

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to trade updates for a symbol."""
        await self.subscribe(f"trade.{symbol}")

    async def subscribe_depth(self, symbol: str, aggregation: str = "") -> None:
        """Subscribe to order book depth updates for a symbol."""
        # Backpack supports depth, depth.200ms, depth.1000ms
        if aggregation:
            await self.subscribe(f"depth.{aggregation}.{symbol}")
        else:
            await self.subscribe(f"depth.{symbol}")

    async def subscribe_kline(self, symbol: str, interval: str) -> None:
        """Subscribe to kline/candlestick updates for a symbol."""
        await self.subscribe(f"kline.{interval}.{symbol}")

    async def subscribe_book_ticker(self, symbol: str) -> None:
        """Subscribe to best bid/ask updates for a symbol."""
        await self.subscribe(f"bookTicker.{symbol}")

    async def subscribe_order_update(self, symbol: str | None = None) -> None:
        """Subscribe to order updates (requires authentication)."""
        if symbol:
            await self.subscribe(f"account.orderUpdate.{symbol}")
        else:
            await self.subscribe("account.orderUpdate")

    async def subscribe_position_update(self, symbol: str | None = None) -> None:
        """Subscribe to position updates (requires authentication)."""
        if symbol:
            await self.subscribe(f"account.positionUpdate.{symbol}")
        else:
            await self.subscribe("account.positionUpdate")