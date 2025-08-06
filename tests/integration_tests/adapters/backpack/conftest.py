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

import json
from pathlib import Path

import pytest


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