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
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._reconnect_task: asyncio.Task | None = None
        
        # Subscription management
        self._subscriptions: set[str] = set()
        self._authenticated = False
        
        # Heartbeat
        self._heartbeat_task: asyncio.Task | None = None
        self._last_pong: int = 0

    async def connect(self) -> None:
        """Connect to the WebSocket server."""
        if self._running:
            self._log.warning("WebSocket client already running")
            return
            
        self._running = True
        self._session = aiohttp.ClientSession()
        
        try:
            await self._connect_ws()
            
            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Authenticate if credentials provided
            if self._api_key and self._api_secret:
                await self._authenticate()
                
            # Restore subscriptions
            if self._subscriptions:
                await self._restore_subscriptions()
                
        except Exception as e:
            self._log.error(f"Failed to connect WebSocket: {e}")
            await self._reconnect()

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._running = False
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
            
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        
        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None
            
        # Close session
        if self._session:
            await self._session.close()
            self._session = None
            
        self._log.info("WebSocket disconnected")

    async def _connect_ws(self) -> None:
        """Establish WebSocket connection."""
        if not self._session:
            raise RuntimeError("Session not initialized")
            
        self._ws = await self._session.ws_connect(
            self._base_url,
            heartbeat=30,
            receive_timeout=60,
        )
        
        self._log.info(f"WebSocket connected to {self._base_url}")
        
        # Start message handler
        asyncio.create_task(self._handle_messages())

    async def _reconnect(self) -> None:
        """Reconnect to the WebSocket server."""
        if not self._running:
            return
            
        self._log.info("Attempting to reconnect WebSocket...")
        
        # Close existing connection
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        # Exponential backoff
        delay = 1
        max_delay = 60
        
        while self._running:
            try:
                await asyncio.sleep(delay)
                await self._connect_ws()
                
                # Re-authenticate if needed
                if self._api_key and self._api_secret:
                    await self._authenticate()
                    
                # Restore subscriptions
                if self._subscriptions:
                    await self._restore_subscriptions()
                    
                self._log.info("WebSocket reconnected successfully")
                break
                
            except Exception as e:
                self._log.error(f"Reconnection failed: {e}")
                delay = min(delay * 2, max_delay)

    async def _authenticate(self) -> None:
        """Authenticate the WebSocket connection."""
        if not self._api_key or not self._api_secret:
            return
            
        # Generate signature
        timestamp = int(asyncio.get_event_loop().time() * 1000)
        window = 5000
        
        signature = sign_request(
            api_secret=self._api_secret,
            method="subscribe",
            params={},
            timestamp=timestamp,
            window=window,
        )
        
        auth_message = {
            "method": "auth",
            "params": {
                "apiKey": self._api_key,
                "signature": signature,
                "timestamp": timestamp,
                "window": window,
            },
        }
        
        await self._send_message(auth_message)
        self._log.info("Authentication message sent")

    async def _handle_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        if not self._ws:
            return
            
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_message(data)
                    except json.JSONDecodeError as e:
                        self._log.error(f"Failed to parse message: {e}")
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self._log.error(f"WebSocket error: {self._ws.exception()}")
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self._log.warning("WebSocket connection closed")
                    break
                    
        except Exception as e:
            self._log.error(f"Error handling messages: {e}")
            
        # Reconnect if still running
        if self._running:
            await self._reconnect()

    async def _process_message(self, data: dict) -> None:
        """Process a WebSocket message."""
        # Handle different message types
        if "stream" in data:
            # Market data stream
            await self._handle_stream_message(data)
            
        elif "method" in data:
            # Response to method call
            await self._handle_method_response(data)
            
        elif "error" in data:
            # Error message
            self._log.error(f"WebSocket error: {data['error']}")
            
        elif "pong" in data:
            # Pong response
            self._last_pong = int(asyncio.get_event_loop().time() * 1000)
            
        else:
            # Unknown message type
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

    async def _send_message(self, message: dict) -> None:
        """Send a message to the WebSocket server."""
        if not self._ws:
            self._log.warning("WebSocket not connected")
            return
            
        try:
            await self._ws.send_str(json.dumps(message))
        except Exception as e:
            self._log.error(f"Failed to send message: {e}")
            await self._reconnect()

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while self._running:
            try:
                await asyncio.sleep(30)
                
                # Send ping
                await self._send_message({"ping": int(asyncio.get_event_loop().time() * 1000)})
                
                # Check for stale connection
                if self._last_pong > 0:
                    elapsed = int(asyncio.get_event_loop().time() * 1000) - self._last_pong
                    if elapsed > 90000:  # 90 seconds
                        self._log.warning("Connection appears stale, reconnecting...")
                        await self._reconnect()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Heartbeat error: {e}")

    async def _restore_subscriptions(self) -> None:
        """Restore subscriptions after reconnection."""
        for stream in self._subscriptions.copy():
            await self.subscribe(stream)

    async def subscribe(self, stream: str, **params) -> None:
        """
        Subscribe to a data stream.
        
        Parameters
        ----------
        stream : str
            The stream name (e.g., "ticker", "trades", "depth").
        **params
            Additional parameters for the subscription.
            
        """
        self._subscriptions.add(stream)
        
        message = {
            "method": "subscribe",
            "params": {
                "stream": stream,
                **params,
            },
        }
        
        await self._send_message(message)

    async def unsubscribe(self, stream: str) -> None:
        """
        Unsubscribe from a data stream.
        
        Parameters
        ----------
        stream : str
            The stream name.
            
        """
        self._subscriptions.discard(stream)
        
        message = {
            "method": "unsubscribe",
            "params": {
                "stream": stream,
            },
        }
        
        await self._send_message(message)

    async def subscribe_ticker(self, symbol: str) -> None:
        """Subscribe to ticker updates for a symbol."""
        await self.subscribe(f"{symbol.lower()}@ticker")

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to trade updates for a symbol."""
        await self.subscribe(f"{symbol.lower()}@trades")

    async def subscribe_depth(self, symbol: str, depth: int = 20) -> None:
        """Subscribe to order book depth updates for a symbol."""
        await self.subscribe(f"{symbol.lower()}@depth{depth}")

    async def subscribe_account(self) -> None:
        """Subscribe to account updates (requires authentication)."""
        if not self._authenticated:
            self._log.warning("Cannot subscribe to account updates without authentication")
            return
            
        await self.subscribe("account")