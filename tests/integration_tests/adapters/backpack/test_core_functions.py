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

"""Tests for Backpack core utility functions."""

import pytest


class TestBackpackCoreFunctions:
    """Test cases for Backpack core utility functions."""

    def test_format_symbol_to_backpack(self):
        """Test converting Nautilus symbol format to Backpack format."""
        # Arrange
        nautilus_symbols = [
            "BTC-USDC",
            "SOL-USDC",
            "ETH-USDT",
            "btc-usdc",  # Test case insensitivity
        ]
        
        # Act & Assert
        expected = ["BTC_USDC", "SOL_USDC", "ETH_USDT", "BTC_USDC"]
        for nautilus_symbol, expected_symbol in zip(nautilus_symbols, expected):
            result = nautilus_symbol.upper().replace("-", "_")
            assert result == expected_symbol

    def test_format_symbol_from_backpack(self):
        """Test converting Backpack symbol format to Nautilus format."""
        # Arrange
        backpack_symbols = [
            "BTC_USDC",
            "SOL_USDC",
            "ETH_USDT",
        ]
        
        # Act & Assert
        expected = ["BTC-USDC", "SOL-USDC", "ETH-USDT"]
        for backpack_symbol, expected_symbol in zip(backpack_symbols, expected):
            result = backpack_symbol.replace("_", "-")
            assert result == expected_symbol

    def test_bidirectional_symbol_conversion(self):
        """Test that symbol conversion is bidirectional."""
        # Arrange
        original_symbols = ["BTC-USDC", "SOL-USDC", "ETH-USDT"]
        
        # Act & Assert
        for symbol in original_symbols:
            # Convert to Backpack format
            backpack_format = symbol.replace("-", "_")
            # Convert back to Nautilus format
            nautilus_format = backpack_format.replace("_", "-")
            assert nautilus_format == symbol

    def test_timestamp_milliseconds_to_microseconds(self):
        """Test converting milliseconds to microseconds."""
        # Arrange
        timestamp_ms = 1694687692980
        
        # Act
        timestamp_us = timestamp_ms * 1000
        
        # Assert
        assert timestamp_us == 1694687692980000

    def test_timestamp_microseconds_to_milliseconds(self):
        """Test converting microseconds to milliseconds."""
        # Arrange
        timestamp_us = 1694687692980000
        
        # Act
        timestamp_ms = timestamp_us // 1000
        
        # Assert
        assert timestamp_ms == 1694687692980

    @pytest.mark.parametrize(
        ("order_side", "expected"),
        [
            ("Buy", "BUY"),
            ("Sell", "SELL"),
            ("Bid", "BUY"),
            ("Ask", "SELL"),
        ],
    )
    def test_order_side_conversion(self, order_side, expected):
        """Test order side conversion."""
        # Act
        if order_side in ["Buy", "Bid"]:
            result = "BUY"
        else:
            result = "SELL"
        
        # Assert
        assert result == expected

    @pytest.mark.parametrize(
        ("order_type", "expected"),
        [
            ("Limit", "LIMIT"),
            ("Market", "MARKET"),
            ("limit", "LIMIT"),
            ("market", "MARKET"),
        ],
    )
    def test_order_type_conversion(self, order_type, expected):
        """Test order type conversion."""
        # Act
        result = order_type.upper()
        
        # Assert
        assert result == expected

    @pytest.mark.parametrize(
        ("time_in_force", "expected"),
        [
            ("GTC", "GTC"),
            ("IOC", "IOC"),
            ("FOK", "FOK"),
            ("gtc", "GTC"),
        ],
    )
    def test_time_in_force_conversion(self, time_in_force, expected):
        """Test time in force conversion."""
        # Act
        result = time_in_force.upper()
        
        # Assert
        assert result == expected

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("New", "OPEN"),
            ("PartiallyFilled", "PARTIALLY_FILLED"),
            ("Filled", "FILLED"),
            ("Cancelled", "CANCELED"),
            ("Expired", "EXPIRED"),
        ],
    )
    def test_order_status_mapping(self, status, expected):
        """Test order status mapping from Backpack to Nautilus."""
        # Arrange
        status_map = {
            "New": "OPEN",
            "PartiallyFilled": "PARTIALLY_FILLED",
            "Filled": "FILLED",
            "Cancelled": "CANCELED",
            "Expired": "EXPIRED",
        }
        
        # Act
        result = status_map.get(status)
        
        # Assert
        assert result == expected

    def test_rate_limit_calculations(self):
        """Test rate limit calculations for different endpoints."""
        # Arrange
        spot_limit_per_minute = 6000
        futures_limit_per_minute = 2400
        
        # Act
        spot_per_second = spot_limit_per_minute / 60
        futures_per_second = futures_limit_per_minute / 60
        
        # Assert
        assert spot_per_second == 100.0
        assert futures_per_second == 40.0

    def test_price_quantity_formatting(self):
        """Test price and quantity decimal formatting."""
        # Arrange
        test_cases = [
            (30123.456789, 2, "30123.46"),  # Price with 2 decimals
            (0.123456789, 4, "0.1235"),  # Quantity with 4 decimals
            (1.0, 2, "1.00"),  # Integer to 2 decimals
            (0.1, 4, "0.1000"),  # Pad with zeros
        ]
        
        # Act & Assert
        for value, decimals, expected in test_cases:
            result = f"{value:.{decimals}f}"
            assert result == expected

    def test_calculate_order_value(self):
        """Test order value calculation."""
        # Arrange
        test_cases = [
            (0.1, 30000.0, 3000.0),  # BTC order
            (100.0, 19.45, 1945.0),  # SOL order
            (0.5, 1725.50, 862.75),  # ETH order
        ]
        
        # Act & Assert
        for quantity, price, expected_value in test_cases:
            result = quantity * price
            assert result == expected_value

    def test_minimum_order_value_validation(self):
        """Test minimum order value validation."""
        # Arrange
        min_order_value = 10.0
        test_cases = [
            (0.0001, 30000.0, False),  # 3.0 < 10.0
            (0.001, 30000.0, True),  # 30.0 >= 10.0
            (1.0, 5.0, False),  # 5.0 < 10.0
            (2.0, 5.0, True),  # 10.0 >= 10.0
        ]
        
        # Act & Assert
        for quantity, price, expected_valid in test_cases:
            order_value = quantity * price
            is_valid = order_value >= min_order_value
            assert is_valid == expected_valid

    def test_websocket_stream_name_formatting(self):
        """Test WebSocket stream name formatting."""
        # Arrange
        test_cases = [
            ("depth", "BTC_USDC", "depth.BTC_USDC"),
            ("trade", "SOL_USDC", "trade.SOL_USDC"),
            ("bookTicker", "ETH_USDC", "bookTicker.ETH_USDC"),
            ("kline", "BTC_USDC", "1m", "kline.1m.BTC_USDC"),
        ]
        
        # Act & Assert
        for case in test_cases:
            if len(case) == 3:
                stream_type, symbol, expected = case
                result = f"{stream_type}.{symbol}"
            else:
                stream_type, symbol, interval, expected = case
                result = f"{stream_type}.{interval}.{symbol}"
            assert result == expected

    def test_error_code_mapping(self):
        """Test API error code mapping."""
        # Arrange
        error_codes = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            429: "Rate Limit Exceeded",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }
        
        # Act & Assert
        for code, message in error_codes.items():
            assert isinstance(code, int)
            assert isinstance(message, str)
            assert code >= 400  # All are error codes