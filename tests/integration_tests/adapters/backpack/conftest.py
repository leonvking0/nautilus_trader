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

"""Configuration and fixtures for Backpack adapter tests."""

import asyncio
import json
import os
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


class TestMode(Enum):
    """Test execution mode."""
    MOCK = "mock"  # Use mock data only
    LIVE = "live"  # Use live API only
    HYBRID = "hybrid"  # Use mock by default, live when specified


# Get test mode from environment variable
TEST_MODE = TestMode(os.getenv("BACKPACK_TEST_MODE", "mock"))


@pytest.fixture(scope="session")
def test_mode() -> TestMode:
    """Return the current test mode."""
    return TEST_MODE


@pytest.fixture(scope="session")
def loop():
    return asyncio.get_event_loop()


@pytest.fixture(scope="session")
def live_clock():
    return LiveClock()


@pytest.fixture(scope="session")
def live_logger():
    return Logger("TEST_LOGGER")


@pytest.fixture(scope="session")
def responses_dir() -> Path:
    """Return the path to the HTTP responses directory."""
    return Path(__file__).parent / "resources" / "http_responses"


@pytest.fixture(scope="session")
def ws_messages_dir() -> Path:
    """Return the path to the WebSocket messages directory."""
    return Path(__file__).parent / "resources" / "ws_messages"


def load_fixture(fixture_path: Path) -> dict:
    """Load a JSON fixture file."""
    with open(fixture_path, "r") as f:
        return json.load(f)


@pytest.fixture
def markets_response(responses_dir):
    """Load markets endpoint response fixture."""
    return load_fixture(responses_dir / "markets.json")


@pytest.fixture
def ticker_response(responses_dir):
    """Load ticker endpoint response fixture."""
    return load_fixture(responses_dir / "ticker.json")


@pytest.fixture
def orderbook_response(responses_dir):
    """Load orderbook endpoint response fixture."""
    return load_fixture(responses_dir / "orderbook.json")


@pytest.fixture
def trades_response(responses_dir):
    """Load trades endpoint response fixture."""
    return load_fixture(responses_dir / "trades.json")


@pytest.fixture
def balance_response(responses_dir):
    """Load balance endpoint response fixture."""
    return load_fixture(responses_dir / "balance.json")


@pytest.fixture
def order_response(responses_dir):
    """Load order endpoint response fixture."""
    return load_fixture(responses_dir / "order.json")


@pytest.fixture
def orders_response(responses_dir):
    """Load orders endpoint response fixture."""
    return load_fixture(responses_dir / "orders.json")


@pytest.fixture()
def venue() -> Venue:
    """Return the Backpack venue."""
    return BACKPACK_VENUE


@pytest.fixture()
def data_client():
    """Data client fixture for Backpack."""
    # Will be implemented when BackpackDataClient is created
    pass


@pytest.fixture()
def exec_client():
    """Execution client fixture for Backpack."""
    # Will be implemented when BackpackExecutionClient is created
    pass


@pytest.fixture()
def instrument() -> CurrencyPair:
    """Return a sample Backpack instrument."""
    return CurrencyPair(
        instrument_id=InstrumentId(
            symbol=Symbol("BTC_USDC"),
            venue=BACKPACK_VENUE,
        ),
        raw_symbol=Symbol("BTC_USDC"),
        base_currency=BTC,
        quote_currency=USDC,
        price_precision=2,
        size_precision=6,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.000001"),
        lot_size=Quantity.from_str("0.000001"),
        max_quantity=Quantity.from_str("10000.000000"),
        min_quantity=Quantity.from_str("0.000001"),
        max_notional=Money.from_str("1000000.00 USDC"),
        min_notional=Money.from_str("10.00 USDC"),
        max_price=Price.from_str("1000000.00"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        ts_event=0,
        ts_init=0,
    )


@pytest.fixture()
def account_state() -> AccountState:
    """Return a sample Backpack account state."""
    from nautilus_trader.core.uuid import UUID4
    
    return AccountState(
        account_id=AccountId("BACKPACK-SPOT-001"),
        account_type=AccountType.CASH,
        base_currency=USDT,
        reported=True,
        balances=[
            AccountBalance(
                total=Money.from_str("10000.00 USDT"),
                locked=Money.from_str("1000.00 USDT"),
                free=Money.from_str("9000.00 USDT"),
            ),
            AccountBalance(
                total=Money.from_str("1.00 BTC"),
                locked=Money.from_str("0.00 BTC"),
                free=Money.from_str("1.00 BTC"),
            ),
        ],
        margins=[],
        info={},
        event_id=UUID4(),
        ts_event=0,
        ts_init=0,
    )