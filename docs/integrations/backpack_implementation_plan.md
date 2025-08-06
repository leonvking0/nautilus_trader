# Backpack Exchange Integration - Implementation Plan

## Overview

This document provides a detailed implementation plan for integrating Backpack Exchange into NautilusTrader. The implementation follows a phased approach to ensure systematic development, testing, and deployment.

## Implementation Phases

### Phase 1: Foundation & Infrastructure (Weeks 1-2)

#### Week 1: Project Setup and Core Components

##### 1.1 Directory Structure Creation
```
nautilus_trader/adapters/backpack/
├── __init__.py
├── common/
│   ├── __init__.py
│   ├── constants.py         # Exchange constants, URLs, limits
│   ├── credentials.py       # Credential management
│   ├── enums.py            # Backpack-specific enums
│   ├── parsing.py          # Message parsing utilities
│   ├── signing.py          # ED25519 signature implementation
│   ├── symbol.py           # Symbol parsing and conversion
│   ├── types.py            # Type definitions
│   └── urls.py             # URL management
├── config.py               # Configuration classes
├── data.py                 # Data client implementation
├── execution.py            # Execution client implementation
├── factories.py            # Factory methods
├── providers.py            # Instrument provider
├── http/
│   ├── __init__.py
│   ├── client.py           # Base HTTP client
│   ├── endpoint.py         # Endpoint definitions
│   ├── errors.py           # Error handling
│   ├── market.py           # Market data endpoints
│   ├── account.py          # Account endpoints
│   └── trading.py          # Trading endpoints
├── websocket/
│   ├── __init__.py
│   ├── client.py           # WebSocket client
│   ├── handlers.py         # Message handlers
│   └── types.py            # WebSocket types
└── schemas/
    ├── __init__.py
    ├── account.py          # Account data schemas
    ├── market.py           # Market data schemas
    ├── order.py            # Order schemas
    └── ws.py               # WebSocket message schemas
```

##### 1.2 Core Constants and Enums

```python
# common/constants.py
BACKPACK_VENUE = Venue("BACKPACK")
BACKPACK_BASE_URL_HTTP = "https://api.backpack.exchange"
BACKPACK_BASE_URL_WS = "wss://ws.backpack.exchange"
BACKPACK_TESTNET_URL_HTTP = "https://api.testnet.backpack.exchange"
BACKPACK_TESTNET_URL_WS = "wss://ws.testnet.backpack.exchange"

MAX_SUBSCRIPTIONS_PER_CONNECTION = 200
MAX_WEBSOCKET_CONNECTIONS = 20
DEFAULT_REQUEST_WINDOW = 5000  # milliseconds
MAX_REQUEST_WINDOW = 60000     # milliseconds

# Rate limits
SPOT_RATE_LIMIT = 6000  # per minute
FUTURES_RATE_LIMIT = 2400  # per minute
ORDER_RATE_LIMIT_SPOT = 3000  # per minute
ORDER_RATE_LIMIT_FUTURES = 1200  # per minute

# common/enums.py
class BackpackAccountType(Enum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"

class BackpackOrderSide(Enum):
    BID = "Bid"
    ASK = "Ask"

class BackpackOrderType(Enum):
    LIMIT = "Limit"
    MARKET = "Market"

class BackpackTimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    POST_ONLY = "PostOnly"

class BackpackOrderStatus(Enum):
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"

class BackpackInstructionType(Enum):
    ACCOUNT_QUERY = "accountQuery"
    BALANCE_QUERY = "balanceQuery"
    ORDER_EXECUTE = "orderExecute"
    ORDER_CANCEL = "orderCancel"
    ORDER_CANCEL_ALL = "orderCancelAll"
    ORDER_QUERY = "orderQuery"
    ORDER_QUERY_ALL = "orderQueryAll"
    SUBSCRIBE = "subscribe"
```

##### 1.3 ED25519 Signing Implementation

```python
# common/signing.py
import base64
from typing import Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

class BackpackSigner:
    """Handles ED25519 signature generation for Backpack API."""
    
    def __init__(self, private_key_base64: str):
        """Initialize with base64 encoded private key."""
        self._private_key = self._load_private_key(private_key_base64)
        self._public_key = self._private_key.public_key()
        self._public_key_base64 = self._encode_public_key()
    
    def _load_private_key(self, private_key_base64: str) -> ed25519.Ed25519PrivateKey:
        """Load ED25519 private key from base64."""
        private_bytes = base64.b64decode(private_key_base64)
        return ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    
    def _encode_public_key(self) -> str:
        """Get base64 encoded public key."""
        public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(public_bytes).decode('utf-8')
    
    def sign_request(
        self,
        instruction: str,
        params: dict,
        timestamp: int,
        window: int = 5000,
    ) -> tuple[str, dict]:
        """
        Sign a request and return signature with headers.
        
        Returns
        -------
        tuple[str, dict]
            Signature and headers dict
        """
        # Build signing string
        signing_string = self._build_signing_string(
            instruction, params, timestamp, window
        )
        
        # Generate signature
        signature = self._private_key.sign(signing_string.encode('utf-8'))
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        
        # Build headers
        headers = {
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": self._public_key_base64,
            "X-Signature": signature_base64,
        }
        
        return signature_base64, headers
    
    def _build_signing_string(
        self,
        instruction: str,
        params: dict,
        timestamp: int,
        window: int,
    ) -> str:
        """Build the string to be signed."""
        # Sort parameters alphabetically
        sorted_params = sorted(params.items())
        param_string = "&".join(f"{k}={v}" for k, v in sorted_params)
        
        # Build complete signing string
        if param_string:
            signing_string = f"instruction={instruction}&{param_string}"
        else:
            signing_string = f"instruction={instruction}"
        
        signing_string += f"&timestamp={timestamp}&window={window}"
        return signing_string
    
    def sign_batch_orders(
        self,
        orders: list[dict],
        timestamp: int,
        window: int = 5000,
    ) -> tuple[str, dict]:
        """Sign a batch order request."""
        signing_parts = []
        
        for order in orders:
            sorted_params = sorted(order.items())
            param_string = "&".join(f"{k}={v}" for k, v in sorted_params)
            signing_parts.append(f"instruction=orderExecute&{param_string}")
        
        signing_string = "&".join(signing_parts)
        signing_string += f"&timestamp={timestamp}&window={window}"
        
        signature = self._private_key.sign(signing_string.encode('utf-8'))
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        
        headers = {
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": self._public_key_base64,
            "X-Signature": signature_base64,
        }
        
        return signature_base64, headers
```

#### Week 2: HTTP Client and Basic Endpoints

##### 2.1 Base HTTP Client

```python
# http/client.py
import asyncio
from typing import Any, Optional
import aiohttp
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.core.nautilus_pyo3 import HttpClient as RustHttpClient
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.core.nautilus_pyo3 import HttpResponse
from nautilus_trader.core.nautilus_pyo3 import Quota

class BackpackHttpClient:
    """HTTP client for Backpack Exchange API."""
    
    def __init__(
        self,
        clock: LiveClock,
        signer: BackpackSigner,
        base_url: str,
        account_type: BackpackAccountType,
        ratelimiter_quotas: list[tuple[str, Quota]],
        ratelimiter_default_quota: Quota,
    ):
        self._clock = clock
        self._log = Logger(type(self).__name__)
        self._signer = signer
        self._base_url = base_url
        self._account_type = account_type
        
        # Initialize Rust HTTP client
        self._client = RustHttpClient(
            base_url=base_url,
            ratelimiter_quotas=ratelimiter_quotas,
            ratelimiter_default_quota=ratelimiter_default_quota,
        )
    
    async def _request(
        self,
        method: HttpMethod,
        endpoint: str,
        instruction: Optional[str] = None,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        auth_required: bool = False,
    ) -> HttpResponse:
        """Execute HTTP request."""
        url = f"{self._base_url}{endpoint}"
        headers = {}
        
        if auth_required:
            timestamp = self._clock.timestamp_ms()
            window = 5000
            
            # Determine parameters for signing
            sign_params = params or body or {}
            
            if instruction:
                _, auth_headers = self._signer.sign_request(
                    instruction=instruction,
                    params=sign_params,
                    timestamp=timestamp,
                    window=window,
                )
                headers.update(auth_headers)
        
        # Make request
        response = await self._client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
        )
        
        return response
    
    async def get_markets(self) -> list[dict]:
        """Get all markets."""
        response = await self._request(
            method=HttpMethod.GET,
            endpoint="/api/v1/markets",
        )
        return response.json()
    
    async def get_depth(self, symbol: str) -> dict:
        """Get order book depth."""
        response = await self._request(
            method=HttpMethod.GET,
            endpoint="/api/v1/depth",
            params={"symbol": symbol},
        )
        return response.json()
    
    async def get_account(self) -> dict:
        """Get account information."""
        response = await self._request(
            method=HttpMethod.GET,
            endpoint="/api/v1/account",
            instruction="accountQuery",
            auth_required=True,
        )
        return response.json()
```

### Phase 2: WebSocket Infrastructure (Weeks 3-4)

#### Week 3: WebSocket Client Base

##### 3.1 WebSocket Client Implementation

```python
# websocket/client.py
import asyncio
import json
from typing import Callable, Optional
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.core.nautilus_pyo3 import WebSocketClient
from nautilus_trader.core.nautilus_pyo3 import WebSocketConfig

class BackpackWebSocketClient:
    """WebSocket client for Backpack Exchange."""
    
    MAX_SUBSCRIPTIONS_PER_CLIENT = 200
    MAX_CLIENTS = 20
    
    def __init__(
        self,
        clock: LiveClock,
        base_url: str,
        handler: Callable[[bytes], None],
        handler_reconnect: Optional[Callable] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        signer: Optional[BackpackSigner] = None,
    ):
        self._clock = clock
        self._log = Logger(type(self).__name__)
        self._base_url = base_url
        self._handler = handler
        self._handler_reconnect = handler_reconnect
        self._loop = loop or asyncio.get_event_loop()
        self._signer = signer
        
        self._clients: dict[int, WebSocketClient] = {}
        self._client_streams: dict[int, list[str]] = {}
        self._is_connected = False
        self._msg_id = 0
    
    async def connect(self):
        """Connect to WebSocket."""
        if self._is_connected:
            return
        
        # Create initial client
        client = await self._create_client(0)
        self._clients[0] = client
        self._client_streams[0] = []
        self._is_connected = True
        
        self._log.info("WebSocket connected")
    
    async def disconnect(self):
        """Disconnect all WebSocket clients."""
        for client_id, client in self._clients.items():
            if client:
                await client.disconnect()
        
        self._clients.clear()
        self._client_streams.clear()
        self._is_connected = False
        
        self._log.info("WebSocket disconnected")
    
    async def subscribe(self, streams: list[str], auth_required: bool = False):
        """Subscribe to streams."""
        if not self._is_connected:
            await self.connect()
        
        # Find or create client for subscriptions
        client_id = self._get_available_client_id(len(streams))
        client = self._clients.get(client_id)
        
        if not client:
            client = await self._create_client(client_id)
            self._clients[client_id] = client
            self._client_streams[client_id] = []
        
        # Build subscription message
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
        }
        
        # Add authentication if required
        if auth_required and self._signer:
            timestamp = self._clock.timestamp_ms()
            window = 5000
            signature, _ = self._signer.sign_request(
                instruction="subscribe",
                params={},
                timestamp=timestamp,
                window=window,
            )
            msg["signature"] = [
                self._signer._public_key_base64,
                signature,
                str(timestamp),
                str(window),
            ]
        
        # Send subscription
        await client.send(json.dumps(msg).encode())
        
        # Track streams
        self._client_streams[client_id].extend(streams)
        
        self._log.info(f"Subscribed to {streams}")
    
    async def unsubscribe(self, streams: list[str]):
        """Unsubscribe from streams."""
        for stream in streams:
            client_id = self._get_client_for_stream(stream)
            if client_id == -1:
                continue
            
            client = self._clients.get(client_id)
            if not client:
                continue
            
            # Send unsubscribe message
            msg = {
                "method": "UNSUBSCRIBE",
                "params": [stream],
            }
            await client.send(json.dumps(msg).encode())
            
            # Remove from tracking
            if stream in self._client_streams[client_id]:
                self._client_streams[client_id].remove(stream)
        
        self._log.info(f"Unsubscribed from {streams}")
    
    def _get_available_client_id(self, num_subscriptions: int) -> int:
        """Find available client ID for new subscriptions."""
        # Try to find existing client with room
        for client_id, streams in self._client_streams.items():
            if len(streams) + num_subscriptions <= self.MAX_SUBSCRIPTIONS_PER_CLIENT:
                return client_id
        
        # Create new client if under limit
        if len(self._clients) < self.MAX_CLIENTS:
            return len(self._clients)
        
        raise RuntimeError("Maximum WebSocket connections exceeded")
    
    def _get_client_for_stream(self, stream: str) -> int:
        """Get client ID for a stream."""
        for client_id, streams in self._client_streams.items():
            if stream in streams:
                return client_id
        return -1
    
    async def _create_client(self, client_id: int) -> WebSocketClient:
        """Create new WebSocket client."""
        config = WebSocketConfig(
            url=self._base_url,
            handler=self._handler,
            heartbeat=60,
            heartbeat_msg=None,
            ping_handler=None,
        )
        
        client = WebSocketClient(
            config=config,
            loop=self._loop,
        )
        
        await client.connect()
        return client
```

#### Week 4: Stream Handlers and Parsing

##### 4.1 Message Handlers

```python
# websocket/handlers.py
import json
from decimal import Decimal
from typing import Optional
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.core.datetime import millis_to_nanos

class BackpackMessageHandler:
    """Handles WebSocket messages from Backpack."""
    
    def __init__(self, instrument_provider):
        self._instrument_provider = instrument_provider
        self._update_ids = {}  # Track update IDs for sequence validation
    
    def parse_message(self, raw: bytes) -> Optional[object]:
        """Parse WebSocket message."""
        try:
            msg = json.loads(raw)
            stream = msg.get("stream", "")
            data = msg.get("data", {})
            
            # Route to appropriate handler
            if stream.startswith("depth"):
                return self._handle_depth(stream, data)
            elif stream.startswith("trade"):
                return self._handle_trade(stream, data)
            elif stream.startswith("bookTicker"):
                return self._handle_book_ticker(stream, data)
            elif stream.startswith("kline"):
                return self._handle_kline(stream, data)
            elif stream.startswith("account.orderUpdate"):
                return self._handle_order_update(data)
            elif stream.startswith("account.positionUpdate"):
                return self._handle_position_update(data)
            else:
                return None
                
        except Exception as e:
            self._log.error(f"Error parsing message: {e}")
            return None
    
    def _handle_depth(self, stream: str, data: dict) -> Optional[OrderBookDeltas]:
        """Handle depth update message."""
        symbol = self._extract_symbol(stream)
        instrument_id = self._get_instrument_id(symbol)
        
        if not instrument_id:
            return None
        
        # Check sequence
        first_update = data.get("U")
        last_update = data.get("u")
        
        if symbol in self._update_ids:
            expected = self._update_ids[symbol] + 1
            if first_update != expected:
                self._log.warning(
                    f"Sequence gap detected for {symbol}: "
                    f"expected {expected}, got {first_update}"
                )
                # Should trigger snapshot request
                return None
        
        self._update_ids[symbol] = last_update
        
        # Parse deltas
        deltas = []
        ts_event = millis_to_nanos(data.get("E", 0) // 1000)
        ts_init = self._clock.timestamp_ns()
        
        # Process bids
        for bid in data.get("b", []):
            price = Price.from_str(bid[0])
            size = Quantity.from_str(bid[1])
            
            delta = OrderBookDelta(
                instrument_id=instrument_id,
                action=BookAction.UPDATE,
                order=BookOrder(
                    side=OrderSide.BUY,
                    price=price,
                    size=size,
                    order_id=0,  # Backpack doesn't provide order IDs
                ),
                flags=0,
                sequence=last_update,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            deltas.append(delta)
        
        # Process asks
        for ask in data.get("a", []):
            price = Price.from_str(ask[0])
            size = Quantity.from_str(ask[1])
            
            delta = OrderBookDelta(
                instrument_id=instrument_id,
                action=BookAction.UPDATE,
                order=BookOrder(
                    side=OrderSide.SELL,
                    price=price,
                    size=size,
                    order_id=0,
                ),
                flags=0,
                sequence=last_update,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            deltas.append(delta)
        
        if deltas:
            return OrderBookDeltas(
                instrument_id=instrument_id,
                deltas=deltas,
            )
        
        return None
    
    def _handle_trade(self, stream: str, data: dict) -> Optional[TradeTick]:
        """Handle trade message."""
        symbol = self._extract_symbol(stream)
        instrument_id = self._get_instrument_id(symbol)
        
        if not instrument_id:
            return None
        
        # Determine aggressor side
        is_buyer_maker = data.get("m", False)
        aggressor_side = AggressorSide.SELLER if is_buyer_maker else AggressorSide.BUYER
        
        return TradeTick(
            instrument_id=instrument_id,
            price=Price.from_str(data["p"]),
            size=Quantity.from_str(data["q"]),
            aggressor_side=aggressor_side,
            trade_id=TradeId(str(data["t"])),
            ts_event=millis_to_nanos(data.get("T", 0) // 1000),
            ts_init=self._clock.timestamp_ns(),
        )
    
    def _handle_book_ticker(self, stream: str, data: dict) -> Optional[QuoteTick]:
        """Handle book ticker message."""
        symbol = self._extract_symbol(stream)
        instrument_id = self._get_instrument_id(symbol)
        
        if not instrument_id:
            return None
        
        return QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price.from_str(data["b"]),
            ask_price=Price.from_str(data["a"]),
            bid_size=Quantity.from_str(data["B"]),
            ask_size=Quantity.from_str(data["A"]),
            ts_event=millis_to_nanos(data.get("T", 0) // 1000),
            ts_init=self._clock.timestamp_ns(),
        )
    
    def _extract_symbol(self, stream: str) -> str:
        """Extract symbol from stream name."""
        parts = stream.split(".")
        if len(parts) >= 2:
            return parts[-1]
        return ""
    
    def _get_instrument_id(self, symbol: str) -> Optional[InstrumentId]:
        """Get instrument ID from symbol."""
        instrument = self._instrument_provider.find(symbol)
        if instrument:
            return instrument.id
        return None
```

### Phase 3: Data Client Implementation (Week 5)

##### 5.1 Data Client

```python
# data.py
from typing import Optional
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.adapters.backpack.websocket.handlers import BackpackMessageHandler
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.identifiers import InstrumentId

class BackpackDataClient(LiveMarketDataClient):
    """
    Provides a data client for Backpack Exchange.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: BackpackHttpClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: BackpackInstrumentProvider,
        config: BackpackDataClientConfig,
    ):
        super().__init__(
            loop=loop,
            client=client,
            venue=BACKPACK_VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
        )
        
        self._config = config
        self._http_client = client
        self._instrument_provider = instrument_provider
        
        # WebSocket setup
        self._ws_client = BackpackWebSocketClient(
            clock=clock,
            base_url=config.base_url_ws or BACKPACK_BASE_URL_WS,
            handler=self._handle_ws_message,
            handler_reconnect=self._on_ws_reconnect,
            loop=loop,
        )
        
        # Message handler
        self._message_handler = BackpackMessageHandler(instrument_provider)
        
        # Subscription tracking
        self._subscriptions: dict[str, list[InstrumentId]] = {}
    
    async def _connect(self) -> None:
        """Connect to Backpack Exchange."""
        self._log.info("Connecting to Backpack Exchange...")
        
        # Connect WebSocket
        await self._ws_client.connect()
        
        # Load instruments
        await self._instrument_provider.load_all_async()
        
        self._log.info("Connected to Backpack Exchange")
    
    async def _disconnect(self) -> None:
        """Disconnect from Backpack Exchange."""
        self._log.info("Disconnecting from Backpack Exchange...")
        
        await self._ws_client.disconnect()
        
        self._log.info("Disconnected from Backpack Exchange")
    
    async def _subscribe_order_book_deltas(
        self,
        instrument_id: InstrumentId,
        book_type: BookType,
        depth: Optional[int] = None,
        kwargs: dict = None,
    ) -> None:
        """Subscribe to order book deltas."""
        symbol = self._get_backpack_symbol(instrument_id)
        
        # Choose aggregation based on kwargs
        aggregation = kwargs.get("aggregation", "realtime") if kwargs else "realtime"
        
        if aggregation == "200ms":
            stream = f"depth.200ms.{symbol}"
        elif aggregation == "1000ms":
            stream = f"depth.1000ms.{symbol}"
        else:
            stream = f"depth.{symbol}"
        
        await self._ws_client.subscribe([stream])
        
        # Track subscription
        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append(instrument_id)
    
    async def _subscribe_quote_ticks(
        self,
        instrument_id: InstrumentId,
    ) -> None:
        """Subscribe to quote ticks."""
        symbol = self._get_backpack_symbol(instrument_id)
        stream = f"bookTicker.{symbol}"
        
        await self._ws_client.subscribe([stream])
        
        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append(instrument_id)
    
    async def _subscribe_trade_ticks(
        self,
        instrument_id: InstrumentId,
    ) -> None:
        """Subscribe to trade ticks."""
        symbol = self._get_backpack_symbol(instrument_id)
        stream = f"trade.{symbol}"
        
        await self._ws_client.subscribe([stream])
        
        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append(instrument_id)
    
    async def _subscribe_bars(
        self,
        bar_type: BarType,
    ) -> None:
        """Subscribe to bar data."""
        instrument_id = bar_type.instrument_id
        symbol = self._get_backpack_symbol(instrument_id)
        
        # Convert bar specification to interval
        interval = self._get_kline_interval(bar_type.spec)
        stream = f"kline.{interval}.{symbol}"
        
        await self._ws_client.subscribe([stream])
        
        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append(instrument_id)
    
    def _handle_ws_message(self, raw: bytes) -> None:
        """Handle WebSocket message."""
        try:
            data = self._message_handler.parse_message(raw)
            if data:
                self._handle_data(data)
        except Exception as e:
            self._log.error(f"Error handling WebSocket message: {e}")
    
    async def _on_ws_reconnect(self) -> None:
        """Handle WebSocket reconnection."""
        self._log.info("WebSocket reconnected, resubscribing...")
        
        # Resubscribe to all streams
        all_streams = list(self._subscriptions.keys())
        if all_streams:
            await self._ws_client.subscribe(all_streams)
    
    def _get_backpack_symbol(self, instrument_id: InstrumentId) -> str:
        """Convert instrument ID to Backpack symbol."""
        # Implementation depends on symbol format
        # e.g., "BTC-USDC" -> "BTC_USDC"
        return instrument_id.symbol.value.replace("-", "_")
    
    def _get_kline_interval(self, bar_spec) -> str:
        """Convert bar specification to kline interval."""
        # Map bar spec to Backpack intervals
        # e.g., 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
        # Implementation depends on bar spec format
        pass
```

### Phase 4: Execution Client Implementation (Week 6)

##### 6.1 Execution Client

```python
# execution.py
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.execution.reports import FillReport
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.orders import Order

class BackpackExecutionClient(LiveExecutionClient):
    """
    Provides an execution client for Backpack Exchange.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: BackpackHttpClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: BackpackInstrumentProvider,
        config: BackpackExecClientConfig,
    ):
        super().__init__(
            loop=loop,
            client=client,
            venue=BACKPACK_VENUE,
            oms_type=config.oms_type,
            account_type=config.account_type,
            base_currency=config.base_currency,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        
        self._config = config
        self._http_client = client
        self._instrument_provider = instrument_provider
        
        # WebSocket for private streams
        self._ws_client = BackpackWebSocketClient(
            clock=clock,
            base_url=config.base_url_ws or BACKPACK_BASE_URL_WS,
            handler=self._handle_ws_message,
            handler_reconnect=self._on_ws_reconnect,
            loop=loop,
            signer=self._http_client._signer,
        )
        
        # Order tracking
        self._pending_orders: dict[ClientOrderId, Order] = {}
        self._open_orders: dict[ClientOrderId, Order] = {}
    
    async def _connect(self) -> None:
        """Connect to Backpack Exchange."""
        self._log.info("Connecting execution client...")
        
        # Connect WebSocket
        await self._ws_client.connect()
        
        # Subscribe to private streams
        await self._ws_client.subscribe(
            ["account.orderUpdate", "account.positionUpdate"],
            auth_required=True,
        )
        
        # Generate initial reports
        await self.generate_order_status_reports()
        await self.generate_position_status_reports()
        
        self._log.info("Execution client connected")
    
    async def _disconnect(self) -> None:
        """Disconnect from Backpack Exchange."""
        await self._ws_client.disconnect()
    
    async def _submit_order(self, command: SubmitOrder) -> None:
        """Submit order to exchange."""
        order = command.order
        
        # Track pending order
        self._pending_orders[order.client_order_id] = order
        
        # Build order request
        params = {
            "symbol": self._get_backpack_symbol(order.instrument_id),
            "side": self._get_order_side(order.side),
            "orderType": self._get_order_type(order.order_type),
            "quantity": str(order.quantity),
        }
        
        # Add price for limit orders
        if order.order_type == OrderType.LIMIT:
            params["price"] = str(order.price)
        
        # Add time in force
        params["timeInForce"] = self._get_time_in_force(order.time_in_force)
        
        # Add client order ID if specified
        if order.client_order_id:
            params["clientId"] = str(order.client_order_id)
        
        # Add reduce only for futures
        if hasattr(order, "reduce_only") and order.reduce_only:
            params["reduceOnly"] = "true"
        
        # Submit order
        try:
            response = await self._http_client._request(
                method=HttpMethod.POST,
                endpoint="/api/v1/order",
                instruction="orderExecute",
                body=params,
                auth_required=True,
            )
            
            # Handle response
            data = response.json()
            self._handle_order_response(order, data)
            
        except Exception as e:
            self._log.error(f"Failed to submit order: {e}")
            self._generate_order_rejected(order, str(e))
    
    async def _cancel_order(self, command: CancelOrder) -> None:
        """Cancel order on exchange."""
        params = {
            "symbol": self._get_backpack_symbol(command.instrument_id),
            "orderId": str(command.venue_order_id) if command.venue_order_id else "",
        }
        
        if command.client_order_id:
            params["clientId"] = str(command.client_order_id)
        
        try:
            response = await self._http_client._request(
                method=HttpMethod.DELETE,
                endpoint="/api/v1/order",
                instruction="orderCancel",
                body=params,
                auth_required=True,
            )
            
            # Order cancel confirmation handled via WebSocket
            
        except Exception as e:
            self._log.error(f"Failed to cancel order: {e}")
    
    async def _modify_order(self, command: ModifyOrder) -> None:
        """Modify order on exchange."""
        # Backpack doesn't support direct order modification
        # Need to cancel and replace
        await self._cancel_order(
            CancelOrder(
                trader_id=command.trader_id,
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=command.venue_order_id,
            )
        )
        
        # Submit new order with modifications
        # Implementation depends on order tracking
    
    async def generate_order_status_reports(
        self,
        instrument_id: Optional[InstrumentId] = None,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        open_only: bool = False,
    ) -> list[OrderStatusReport]:
        """Generate order status reports."""
        reports = []
        
        # Query open orders
        response = await self._http_client._request(
            method=HttpMethod.GET,
            endpoint="/api/v1/orders",
            instruction="orderQueryAll",
            auth_required=True,
        )
        
        orders = response.json()
        
        for order_data in orders:
            report = self._parse_order_status_report(order_data)
            if report:
                reports.append(report)
        
        return reports
    
    async def generate_fill_reports(
        self,
        instrument_id: Optional[InstrumentId] = None,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
    ) -> list[FillReport]:
        """Generate fill reports."""
        reports = []
        
        params = {}
        if start:
            params["from"] = int(start.timestamp() * 1000)
        if end:
            params["to"] = int(end.timestamp() * 1000)
        
        response = await self._http_client._request(
            method=HttpMethod.GET,
            endpoint="/api/v1/fills",
            instruction="fillHistoryQueryAll",
            params=params,
            auth_required=True,
        )
        
        fills = response.json()
        
        for fill_data in fills:
            report = self._parse_fill_report(fill_data)
            if report:
                reports.append(report)
        
        return reports
```

### Phase 5: Testing & Documentation (Weeks 7-8)

#### Week 7: Testing Implementation

##### 7.1 Test Structure
```
tests/unit_tests/adapters/backpack/
├── test_backpack_common.py
├── test_backpack_data.py
├── test_backpack_execution.py
├── test_backpack_factories.py
├── test_backpack_http.py
├── test_backpack_parsing.py
├── test_backpack_providers.py
├── test_backpack_signing.py
└── test_backpack_websocket.py

tests/integration_tests/adapters/
└── test_backpack_integration.py
```

#### Week 8: Documentation and Examples

##### 8.1 Documentation Structure
```
docs/integrations/
├── backpack.md              # Main documentation
├── backpack_prd.md          # Product requirements
├── backpack_implementation_plan.md  # This document
└── backpack_test_plan.md    # Test plan

examples/live/backpack/
├── backpack_data_tester.py  # Test data connections
├── backpack_ema_cross.py    # Example strategy
├── backpack_market_maker.py # Market making example
└── backpack_sandbox.py      # Sandbox for testing
```

## Development Guidelines

### Code Quality Standards
- Follow PEP 8 and NautilusTrader coding standards
- Use type hints for all function signatures
- Document all public methods and classes
- Maintain >90% test coverage

### Git Workflow
1. Create feature branch: `feature/backpack-integration`
2. Regular commits with descriptive messages
3. Pull request with comprehensive description
4. Code review by maintainers
5. Merge to develop branch

### Testing Strategy
- Unit tests for all components
- Integration tests with testnet
- Performance benchmarks
- Memory leak detection
- 24-hour stability test

## Risk Management

### Technical Risks
- **ED25519 Implementation**: Use established cryptography library
- **WebSocket Stability**: Implement robust reconnection logic
- **Rate Limiting**: Proper throttling and queue management
- **Sequence Validation**: Handle gaps and request snapshots

### Mitigation Strategies
- Comprehensive error handling
- Circuit breaker patterns
- Graceful degradation
- Clear error messages and logging

## Monitoring & Maintenance

### Logging
- Debug logs for development
- Info logs for normal operation
- Warning logs for recoverable issues
- Error logs for failures

### Metrics
- Message processing latency
- Order submission latency
- WebSocket reconnection count
- API request success rate

### Health Checks
- WebSocket connection status
- Authentication validity
- Rate limit usage
- Memory usage

## Deployment Checklist

### Pre-deployment
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Code review approved
- [ ] Performance benchmarks met
- [ ] Security audit passed

### Deployment
- [ ] Deploy to test environment
- [ ] Run integration tests
- [ ] Monitor for 24 hours
- [ ] Deploy to production
- [ ] Monitor metrics

### Post-deployment
- [ ] Announce release
- [ ] Monitor user feedback
- [ ] Address any issues
- [ ] Plan improvements

## Conclusion

This implementation plan provides a structured approach to integrating Backpack Exchange with NautilusTrader. Following this plan ensures systematic development, comprehensive testing, and successful deployment of a production-ready adapter.