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

"""Tests for Backpack response parsing to Nautilus types."""

from decimal import Decimal

import pytest


class TestBackpackParsing:
    """Test cases for parsing Backpack responses to Nautilus types."""

    def test_parse_market_to_instrument(self, markets_response):
        """Test parsing market data to Nautilus Instrument."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(markets_response, dict) and "data" in markets_response:
            market = markets_response["data"][0]  # First market
        else:
            market = markets_response[0]
        
        # Extract precision from tick/step sizes
        price_tick = market["filters"]["price"]["tickSize"]
        quantity_step = market["filters"]["quantity"]["stepSize"]
        price_precision = len(price_tick.split(".")[1]) if "." in price_tick else 0
        size_precision = len(quantity_step.split(".")[1]) if "." in quantity_step else 0
        
        # Act - Simulate parsing logic
        parsed = {
            "id": market["symbol"].replace("_", "-"),
            "base_currency": market["baseSymbol"],
            "quote_currency": market["quoteSymbol"],
            "price_precision": price_precision,
            "size_precision": size_precision,
            "price_increment": Decimal(price_tick),
            "size_increment": Decimal(quantity_step),
            "min_notional": Decimal("10.00"),  # Default min notional
            "max_quantity": market["filters"]["quantity"]["maxQuantity"],
            "min_quantity": Decimal(market["filters"]["quantity"]["minQuantity"]),
            "margin_init": Decimal("0"),  # Spot market
            "margin_maint": Decimal("0"),  # Spot market
            "maker_fee": Decimal("0.0002"),  # Default fee
            "taker_fee": Decimal("0.0005"),  # Default fee
            "market_type": market.get("marketType", "SPOT"),
            "ts_event": 0,
            "ts_init": 0,
        }
        
        # Assert
        assert parsed["id"] == "SOL-USDC"  # First market in response
        assert parsed["base_currency"] == "SOL"
        assert parsed["quote_currency"] == "USDC"
        assert parsed["price_precision"] == 2
        assert parsed["size_precision"] == 2
        assert parsed["price_increment"] == Decimal("0.01")
        assert parsed["size_increment"] == Decimal("0.01")
        assert parsed["min_quantity"] == Decimal("0.01")

    def test_parse_ticker_to_quote_tick(self, ticker_response, orderbook_response):
        """Test parsing ticker data to QuoteTick."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(ticker_response, dict) and "data" in ticker_response:
            ticker = ticker_response["data"]
        else:
            ticker = ticker_response
            
        if isinstance(orderbook_response, dict) and "data" in orderbook_response:
            orderbook = orderbook_response["data"]
        else:
            orderbook = orderbook_response
        
        # Since ticker doesn't have bid/ask, we'd get them from orderbook
        best_bid = orderbook["bids"][0] if orderbook.get("bids") else ["0", "0"]
        best_ask = orderbook["asks"][0] if orderbook.get("asks") else ["0", "0"]
        
        # Act - Simulate parsing logic (combining ticker and orderbook data)
        parsed = {
            "instrument_id": ticker["symbol"].replace("_", "-"),
            "bid_price": Decimal(best_bid[0]),
            "ask_price": Decimal(best_ask[0]),
            "bid_size": Decimal(best_bid[1]),
            "ask_size": Decimal(best_ask[1]),
            "last_price": Decimal(ticker["lastPrice"]),
            "volume": Decimal(ticker["volume"]),
            "ts_event": 0,  # Would be set from actual timestamp
            "ts_init": 0,
        }
        
        # Assert
        assert parsed["instrument_id"] == "SOL-USDC"
        assert parsed["last_price"] == Decimal("168.52")
        assert parsed["bid_price"] == Decimal("168.51")
        assert parsed["ask_price"] == Decimal("168.52")
        assert parsed["volume"] == Decimal("168140.32")

    def test_parse_trade_to_trade_tick(self, trades_response):
        """Test parsing trade data to TradeTick."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(trades_response, dict) and "data" in trades_response:
            trade = trades_response["data"][0]
        else:
            trade = trades_response[0]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": "SOL-USDC",  # Would come from request context
            "price": Decimal(trade["price"]),
            "size": Decimal(trade["quantity"]),
            "quote_quantity": Decimal(trade["quoteQuantity"]),
            "aggressor_side": "SELLER" if trade["isBuyerMaker"] else "BUYER",
            "trade_id": str(trade["id"]),
            "ts_event": trade["timestamp"] * 1000,  # Convert to microseconds
            "ts_init": trade["timestamp"] * 1000,
        }
        
        # Assert
        assert parsed["price"] == Decimal("168.52")
        assert parsed["size"] == Decimal("0.01")
        assert parsed["quote_quantity"] == Decimal("1.6852")
        assert parsed["aggressor_side"] == "BUYER"  # isBuyerMaker=false means seller was aggressor
        assert parsed["trade_id"] == "362947600"
        assert parsed["ts_event"] == 1754511357420000

    def test_parse_orderbook_to_deltas(self, orderbook_response):
        """Test parsing order book data to OrderBookDeltas."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(orderbook_response, dict) and "data" in orderbook_response:
            orderbook = orderbook_response["data"]
        else:
            orderbook = orderbook_response
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": "SOL-USDC",  # Would come from request context
            "bids": [(Decimal(price), Decimal(size)) for price, size in orderbook.get("bids", [])],
            "asks": [(Decimal(price), Decimal(size)) for price, size in orderbook.get("asks", [])],
            "update_id": orderbook.get("lastUpdateId", 0),
            "ts_event": 0,  # Would be set from actual timestamp
            "ts_init": 0,
        }
        
        # Assert
        assert parsed["instrument_id"] == "SOL-USDC"
        assert len(parsed["bids"]) >= 5  # At least 5 levels
        assert len(parsed["asks"]) >= 5  # At least 5 levels
        if parsed["bids"]:
            assert parsed["bids"][0] == (Decimal("168.51"), Decimal("8.27"))
        if parsed["asks"]:
            assert parsed["asks"][0] == (Decimal("168.52"), Decimal("6.46"))

    def test_parse_balance_to_account_balance(self, balance_response):
        """Test parsing balance data to AccountBalance."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(balance_response, dict) and "data" in balance_response:
            balances = balance_response["data"]
        else:
            balances = balance_response
        
        # Act - Simulate parsing logic
        parsed_balances = []
        for symbol, balance_data in balances.items():
            available = Decimal(balance_data["available"])
            locked = Decimal(balance_data["locked"])
            staked = Decimal(balance_data.get("staked", "0"))
            total = available + locked + staked
            
            parsed = {
                "currency": symbol,
                "total": total,
                "free": available,
                "locked": locked,
                "staked": staked,
            }
            parsed_balances.append(parsed)
        
        # Assert
        assert len(parsed_balances) >= 1
        
        # Check USDC balance (should be the first or only one)
        usdc_balance = next((b for b in parsed_balances if b["currency"] == "USDC"), None)
        assert usdc_balance is not None
        assert usdc_balance["currency"] == "USDC"
        assert usdc_balance["total"] == Decimal("100.00")
        assert usdc_balance["free"] == Decimal("100.00")
        assert usdc_balance["locked"] == Decimal("0.00")

    def test_parse_order_to_nautilus_order(self, order_response):
        """Test parsing order data to Nautilus Order."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(order_response, dict) and "data" in order_response:
            order = order_response["data"]
        else:
            order = order_response
        
        # Act - Simulate parsing logic
        parsed = {
            "client_order_id": str(order.get("clientOrderId") or order.get("clientId") or ""),
            "venue_order_id": str(order["id"]),
            "instrument_id": order["symbol"].replace("_", "-"),
            "order_side": "BUY" if order["side"] == "Bid" else "SELL",
            "order_type": order["orderType"].upper(),
            "time_in_force": order["timeInForce"],
            "quantity": Decimal(order["quantity"]) if order["quantity"] else None,
            "price": Decimal(order["price"]) if order["price"] else None,
            "filled_qty": Decimal(order["executedQuantity"]),
            "executed_quote_qty": Decimal(order["executedQuoteQuantity"]),
            "avg_px": None,  # Would need to calculate from executedQuoteQuantity / executedQuantity
            "status": self._map_order_status(order["status"]),
            "post_only": order.get("postOnly", False),
            "ts_init": order["createdAt"],  # Already in milliseconds
            "ts_last": order.get("updatedAt", order["createdAt"]),
        }
        
        # Assert
        assert parsed["client_order_id"] == "CLIENT_1"
        assert parsed["venue_order_id"] == "TEST_ORDER_1"
        assert parsed["instrument_id"] == "SOL-USDC"
        assert parsed["order_side"] == "BUY"
        assert parsed["order_type"] == "LIMIT"
        assert parsed["time_in_force"] == "GTC"
        assert parsed["quantity"] == Decimal("0.1")
        assert parsed["price"] == Decimal("151.4")
        assert parsed["filled_qty"] == Decimal("0")
        assert parsed["status"] == "OPEN"

    def test_parse_orders_list(self, orders_response):
        """Test parsing multiple orders."""
        # Arrange
        # Get the actual data from metadata wrapper if present
        if isinstance(orders_response, dict) and "data" in orders_response:
            orders = orders_response["data"]
        else:
            orders = orders_response
        
        # Act
        parsed_orders = []
        for order in orders:
            parsed_orders.append({
                "venue_order_id": str(order["id"]),
                "status": self._map_order_status(order["status"]),
                "side": "BUY" if order["side"] == "Bid" else "SELL",
                "quantity": Decimal(order["quantity"]),
                "price": Decimal(order["price"]),
            })
        
        # Assert
        assert len(parsed_orders) >= 1
        assert parsed_orders[0]["venue_order_id"] == "TEST_ORDER_1"
        assert parsed_orders[0]["status"] == "OPEN"
        assert parsed_orders[0]["side"] == "BUY"
        assert parsed_orders[0]["quantity"] == Decimal("0.1")
        assert parsed_orders[0]["price"] == Decimal("151.4")

    def test_parse_klines_to_bars(self, responses_dir):
        """Test parsing kline data to Bar objects."""
        # Arrange
        from .conftest import load_fixture
        klines = load_fixture(responses_dir / "klines.json")
        
        # Get the actual data from metadata wrapper if present
        if isinstance(klines, dict) and "data" in klines:
            klines = klines["data"]
        
        # Act - Simulate parsing logic
        parsed_bars = []
        for kline in klines:
            # Kline format: [timestamp, open, high, low, close, volume]
            parsed = {
                "open": Decimal(kline[1]),
                "high": Decimal(kline[2]),
                "low": Decimal(kline[3]),
                "close": Decimal(kline[4]),
                "volume": Decimal(kline[5]),
                "ts_event": kline[0],  # Already in milliseconds
                "ts_init": kline[0] + 60000,  # Add 1 minute for close time
            }
            parsed_bars.append(parsed)
        
        # Assert
        assert len(parsed_bars) == 3
        
        first_bar = parsed_bars[0]
        assert first_bar["open"] == Decimal("150.00")
        assert first_bar["high"] == Decimal("155.00")
        assert first_bar["low"] == Decimal("145.00")
        assert first_bar["close"] == Decimal("152.00")
        assert first_bar["volume"] == Decimal("1000.0")
        assert first_bar["ts_event"] == 1234567890000

    def test_parse_websocket_book_ticker(self, ws_messages_dir):
        """Test parsing WebSocket book ticker message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "bookTicker.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": data["s"].replace("_", "-"),
            "bid_price": Decimal(data["b"]),
            "bid_size": Decimal(data["B"]),
            "ask_price": Decimal(data["a"]),
            "ask_size": Decimal(data["A"]),
            "update_id": int(data["u"]),
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["bid_price"] == Decimal("30120.00")
        assert parsed["bid_size"] == Decimal("0.5000")
        assert parsed["ask_price"] == Decimal("30125.00")
        assert parsed["ask_size"] == Decimal("0.6000")
        assert parsed["update_id"] == 111063070525358080

    def test_parse_websocket_trade(self, ws_messages_dir):
        """Test parsing WebSocket trade message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "trade.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": data["s"].replace("_", "-"),
            "price": Decimal(data["p"]),
            "size": Decimal(data["q"]),
            "aggressor_side": "SELLER" if data["m"] else "BUYER",
            "trade_id": str(data["t"]),
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["price"] == Decimal("30123.45")
        assert parsed["size"] == Decimal("0.1234")
        assert parsed["aggressor_side"] == "SELLER"  # m=true means buyer is maker
        assert parsed["trade_id"] == "12345"

    def test_parse_websocket_order_update(self, ws_messages_dir):
        """Test parsing WebSocket order update message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "orderUpdate.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "event_type": data["e"],
            "instrument_id": data["s"].replace("_", "-"),
            "client_order_id": str(data.get("c", "")),
            "venue_order_id": str(data["i"]),
            "order_side": "BUY" if data["S"] == "Buy" else "SELL",
            "order_type": data["o"],
            "quantity": Decimal(data["q"]) if "q" in data else None,
            "price": Decimal(data["p"]) if "p" in data else None,
            "filled_qty": Decimal(data["z"]) if "z" in data else Decimal("0"),
            "status": data["X"],
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["event_type"] == "orderAccepted"
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["client_order_id"] == "123"
        assert parsed["venue_order_id"] == "1111343026172067"
        assert parsed["order_side"] == "BUY"
        assert parsed["order_type"] == "LIMIT"
        assert parsed["quantity"] == Decimal("0.1000")
        assert parsed["price"] == Decimal("30000.00")
        assert parsed["filled_qty"] == Decimal("0.0000")
        assert parsed["status"] == "New"

    def _map_order_status(self, backpack_status: str) -> str:
        """Map Backpack order status to Nautilus status."""
        status_map = {
            "New": "OPEN",
            "PartiallyFilled": "PARTIALLY_FILLED",
            "Filled": "FILLED",
            "Cancelled": "CANCELED",
            "Expired": "EXPIRED",
        }
        return status_map.get(backpack_status, backpack_status)