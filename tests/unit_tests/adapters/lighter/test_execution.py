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

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.lighter.config import LighterExecClientConfig
from nautilus_trader.adapters.lighter.constants import LIGHTER_VENUE
from nautilus_trader.adapters.lighter.execution import LighterExecutionClient
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


class DummyInstrumentProvider(InstrumentProvider):
    """
    Minimal instrument provider to satisfy the execution client dependency graph.
    """

    def __init__(self, instrument: CryptoPerpetual, market_index: int = 1) -> None:
        super().__init__(config=InstrumentProviderConfig())
        self._instrument = instrument
        self._market_index = market_index
        self.add(instrument)
        self._market_index_by_instrument = {instrument.id.value: market_index}

    def market_index_for(self, instrument_id) -> int | None:
        return self._market_index if instrument_id == self._instrument.id else None


@pytest.fixture(scope="session")
def btc_instrument() -> CryptoPerpetual:
    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol("BTC-USD-PERP"), venue=LIGHTER_VENUE),
        raw_symbol=Symbol("BTC"),
        base_currency=BTC,
        quote_currency=USD,
        settlement_currency=USD,
        is_inverse=False,
        price_precision=1,
        size_precision=4,
        price_increment=Price.from_str("0.1"),
        size_increment=Quantity.from_str("0.0001"),
        max_quantity=None,
        min_quantity=Quantity.from_str("0.0010"),
        max_notional=None,
        min_notional=None,
        max_price=None,
        min_price=None,
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        ts_event=0,
        ts_init=0,
    )


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def exec_client(loop, btc_instrument):
    http = AsyncMock()
    http.next_nonce = AsyncMock(return_value={"nonce": 1})
    http.send_tx = AsyncMock(return_value={"code": 200, "message": None, "tx_hash": "hash"})
    http.account_active_orders = AsyncMock(return_value={"orders": []})

    ws = MagicMock()
    signer = MagicMock()
    signer.auth_token.return_value = "token"
    signer.sign_create_order.return_value = SimpleNamespace(tx_type=14, tx_info="{}", tx_hash="hash")
    signer.sign_cancel_order.return_value = SimpleNamespace(tx_type=15, tx_info="{}", tx_hash="hash")

    clock = LiveClock()
    msgbus = MessageBus(trader_id=TestIdStubs.trader_id(), clock=clock)
    cache = TestComponentStubs.cache()
    provider = DummyInstrumentProvider(btc_instrument)

    config = LighterExecClientConfig(account_index=1, api_key_private_key="deadbeef", testnet=True)
    client = LighterExecutionClient(
        loop=loop,
        http_client=http,
        ws_client=ws,
        signer=signer,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        instrument_provider=provider,
        config=config,
        name="TEST",
    )
    return client


@pytest.fixture
def active_orders():
    with open("tests/test_data/lighter/http/mainnet_account_active_orders_market1.json") as f:
        fixture = json.load(f)
    return fixture["response"]["body"]["orders"]


@pytest.fixture
def private_ws_messages():
    with open("tests/test_data/lighter/ws/private_mainnet_orders.json") as f:
        return json.load(f)


def test_client_order_index_hashing(exec_client: LighterExecutionClient):
    numeric = exec_client._client_order_index("12345")
    hashed = exec_client._client_order_index("client-abc")

    assert numeric == 12345
    assert hashed > 0
    assert hashed < (1 << 63)
    assert hashed == exec_client._client_order_index("client-abc")


def test_parse_active_orders_generates_reports(exec_client: LighterExecutionClient, btc_instrument, active_orders):
    reports, fills = exec_client._parse_active_orders(active_orders, instrument=btc_instrument)

    assert len(reports) == 2
    assert not fills

    report = reports[0]
    assert report.order_status == OrderStatus.ACCEPTED
    assert report.order_type == OrderType.LIMIT
    assert report.time_in_force == TimeInForce.GTC
    assert report.quantity == Quantity.from_str("0.00060")
    assert report.price == Price.from_str("83123.5")


def test_fill_price_uses_executed_quote(exec_client: LighterExecutionClient, btc_instrument):
    order = {
        "order_index": 1,
        "client_order_id": "abc",
        "initial_base_amount": "0.00060",
        "filled_base_amount": "0.00030",
        "remaining_base_amount": "0.00030",
        "filled_quote_amount": "25.0000",
        "is_ask": False,
        "price": "82000.0",
        "status": "partial",
        "time_in_force": "good-till-time",
    }

    reports, fills = exec_client._parse_active_orders([order], instrument=btc_instrument)
    assert len(reports) == 1
    assert len(fills) == 1

    fill = fills[0]
    # executed price = 25 / 0.00030 = 83333.333... -> precision 1 => 83333.3
    assert fill.last_px == Price.from_str("83333.3")


def test_private_ws_order_update(exec_client: LighterExecutionClient, private_ws_messages):
    reports: list = []
    fills: list = []
    exec_client._send_order_status_report = MagicMock(side_effect=reports.append)
    exec_client._send_fill_report = MagicMock(side_effect=fills.append)

    update = next(m for m in private_ws_messages if m["type"] == "update/account_all_orders")
    exec_client._handle_user_stream_message(update)

    assert len(reports) == 1
    assert reports[0].order_status == OrderStatus.CANCELED
    assert not fills


@pytest.fixture
def account_fixture():
    with open("tests/test_data/lighter/http/mainnet_account_index_659514.json") as f:
        fixture = json.load(f)
    return fixture["response"]["body"]


@pytest.mark.asyncio
async def test_generate_position_status_reports(exec_client: LighterExecutionClient, account_fixture):
    """
    Test that position status reports are generated from account data.
    """
    from nautilus_trader.model.enums import PositionSide

    exec_client._http_client.account_by_index = AsyncMock(return_value=account_fixture)

    class FakeCommand:
        instrument_id = None

    reports = await exec_client.generate_position_status_reports(FakeCommand())

    # The fixture has 1 position for BTC market with position=0 (should be FLAT)
    assert len(reports) == 1
    report = reports[0]
    assert report.position_side == PositionSide.FLAT
    assert report.quantity.as_decimal() == Decimal(0)


def test_position_to_report_long_position(exec_client: LighterExecutionClient, btc_instrument):
    """
    Test that a long position is correctly converted to a report.
    """
    from nautilus_trader.model.enums import PositionSide

    position = {
        "market_id": 1,
        "symbol": "BTC",
        "sign": 1,
        "position": "1.25000",
        "avg_entry_price": "95000.0",
    }

    report = exec_client._position_to_report(position, filter_instrument_id=None, ts_init=1000)

    assert report is not None
    assert report.position_side == PositionSide.LONG
    assert report.quantity.as_decimal() == Decimal("1.25")
    assert report.avg_px_open == Decimal("95000.0")


def test_position_to_report_short_position(exec_client: LighterExecutionClient, btc_instrument):
    """
    Test that a short position is correctly converted to a report.
    """
    from nautilus_trader.model.enums import PositionSide

    position = {
        "market_id": 1,
        "symbol": "BTC",
        "sign": -1,
        "position": "0.50000",
        "avg_entry_price": "92500.0",
    }

    report = exec_client._position_to_report(position, filter_instrument_id=None, ts_init=1000)

    assert report is not None
    assert report.position_side == PositionSide.SHORT
    assert report.quantity.as_decimal() == Decimal("0.5")
    assert report.avg_px_open == Decimal("92500.0")


def test_position_to_report_filters_by_instrument(exec_client: LighterExecutionClient, btc_instrument):
    """
    Test that positions are filtered by instrument ID.
    """
    from nautilus_trader.model.identifiers import InstrumentId

    position = {
        "market_id": 1,
        "symbol": "BTC",
        "sign": 1,
        "position": "1.0",
    }

    # Filter for a different instrument should return None
    other_instrument_id = InstrumentId.from_str("ETH-USD-PERP.LIGHTER")
    report = exec_client._position_to_report(position, filter_instrument_id=other_instrument_id, ts_init=1000)

    assert report is None


def test_position_to_report_unknown_market(exec_client: LighterExecutionClient):
    """
    Test that unknown market IDs return None.
    """
    position = {
        "market_id": 999,  # Unknown market
        "symbol": "UNKNOWN",
        "sign": 1,
        "position": "1.0",
    }

    report = exec_client._position_to_report(position, filter_instrument_id=None, ts_init=1000)

    assert report is None
