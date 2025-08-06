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

"""Backpack instrument provider implementation."""

from decimal import Decimal

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.account import BackpackAccount
from nautilus_trader.adapters.backpack.schemas.market import BackpackMarket
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.instruments.currency_pair import CurrencyPair
from nautilus_trader.model.objects import PRICE_MAX
from nautilus_trader.model.objects import PRICE_MIN
from nautilus_trader.model.objects import QUANTITY_MAX
from nautilus_trader.model.objects import QUANTITY_MIN
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


class BackpackInstrumentProvider(InstrumentProvider):
    """
    Provides a means of loading instruments from the Backpack exchange.

    Parameters
    ----------
    client : BackpackHttpClient
        The client for the provider.
    clock : LiveClock
        The clock for the provider.
    testnet : bool, default False
        If the provider is for the testnet.
    config : InstrumentProviderConfig, optional
        The configuration for the provider.
    venue : Venue, optional
        The venue for the provider.

    """

    def __init__(
        self,
        client: BackpackHttpClient,
        clock: LiveClock,
        testnet: bool = False,
        config: InstrumentProviderConfig | None = None,
        venue: Venue = BACKPACK_VENUE,
    ) -> None:
        super().__init__(config=config)

        self._clock = clock
        self._client = client
        self._testnet = testnet
        self._venue = venue

        self._log_warnings = config.log_warnings if config else True

        self._decoder = msgspec.json.Decoder(list[BackpackMarket])
        self._encoder = msgspec.json.Encoder()

    async def load_all_async(self, filters: dict | None = None) -> None:
        """Load all instruments from the exchange."""
        filters_str = "..." if not filters else f" with filters {filters}..."
        self._log.info(f"Loading all instruments{filters_str}")

        # Get account info for fees if authenticated
        fees = {}
        try:
            account_data = await self._client.get("/api/account")
            if account_data:
                # Backpack returns account-wide fees in the account endpoint
                # For now, we'll use the default fees from market data
                pass
        except Exception as e:
            self._log.debug(f"Could not fetch account fees: {e}")

        # Get all markets
        markets_data = await self._client.get("/api/markets")
        markets = self._decoder.decode(
            self._encoder.encode(markets_data)
        )

        for market in markets:
            if market.status != "active":
                continue

            if filters:
                # Apply filters if provided
                if "base" in filters and market.base_currency != filters["base"]:
                    continue
                if "quote" in filters and market.quote_currency != filters["quote"]:
                    continue

            self._parse_instrument(
                market=market,
                ts_event=self._clock.timestamp_ns(),
            )

    async def load_ids_async(
        self,
        instrument_ids: list[InstrumentId],
        filters: dict | None = None,
    ) -> None:
        """Load specific instruments by ID."""
        if not instrument_ids:
            self._log.info("No instrument IDs given for loading.")
            return

        # Check all instrument IDs
        for instrument_id in instrument_ids:
            PyCondition.equal(
                instrument_id.venue,
                self._venue,
                "instrument_id.venue",
                str(self._venue),
            )

        # Get all markets (Backpack doesn't have a single market endpoint)
        markets_data = await self._client.get("/api/markets")
        markets = self._decoder.decode(
            self._encoder.encode(markets_data)
        )

        # Create lookup dict
        markets_dict = {market.symbol: market for market in markets}

        for instrument_id in instrument_ids:
            symbol = instrument_id.symbol.value
            if symbol in markets_dict:
                self._parse_instrument(
                    market=markets_dict[symbol],
                    ts_event=self._clock.timestamp_ns(),
                )
            else:
                self._log.warning(f"Instrument {instrument_id} not found on exchange")

    async def load_async(
        self,
        instrument_id: InstrumentId,
        filters: dict | None = None,
    ) -> None:
        """Load a single instrument."""
        PyCondition.not_none(instrument_id, "instrument_id")
        PyCondition.equal(
            instrument_id.venue,
            self._venue,
            "instrument_id.venue",
            str(self._venue),
        )

        filters_str = "..." if not filters else f" with filters {filters}..."
        self._log.debug(f"Loading instrument {instrument_id}{filters_str}.")

        # Get all markets (Backpack doesn't have a single market endpoint)
        markets_data = await self._client.get("/api/markets")
        markets = self._decoder.decode(
            self._encoder.encode(markets_data)
        )

        symbol = instrument_id.symbol.value
        for market in markets:
            if market.symbol == symbol:
                self._parse_instrument(
                    market=market,
                    ts_event=self._clock.timestamp_ns(),
                )
                return

        self._log.warning(f"Instrument {instrument_id} not found on exchange")

    def _parse_instrument(
        self,
        market: BackpackMarket,
        ts_event: int,
    ) -> None:
        """Parse a market into an instrument."""
        # Create instrument ID
        instrument_id = InstrumentId(
            symbol=Symbol(market.symbol),
            venue=self._venue,
        )

        # Parse fees
        maker_fee = Decimal(market.maker_fee)
        taker_fee = Decimal(market.taker_fee)

        # Parse price and quantity bounds
        price_increment = Price.from_str(market.tick_size)
        size_increment = Quantity.from_str(market.lot_size)

        min_price = Price.from_str(market.min_price) if market.min_price else PRICE_MIN
        max_price = Price.from_str(market.max_price) if market.max_price else PRICE_MAX
        min_quantity = Quantity.from_str(market.min_quantity) if market.min_quantity else QUANTITY_MIN
        max_quantity = Quantity.from_str(market.max_quantity) if market.max_quantity else QUANTITY_MAX

        # Create instrument based on market type
        if market.market_type in ["spot", None]:  # Default to spot if not specified
            instrument = CurrencyPair(
                instrument_id=instrument_id,
                raw_symbol=Symbol(market.symbol),
                base_currency=Currency.from_str(market.base_currency),
                quote_currency=Currency.from_str(market.quote_currency),
                price_precision=market.price_decimals,
                size_precision=market.quantity_decimals,
                price_increment=price_increment,
                size_increment=size_increment,
                lot_size=size_increment,
                max_quantity=max_quantity,
                min_quantity=min_quantity,
                max_price=max_price,
                min_price=min_price,
                maker_fee=maker_fee,
                taker_fee=taker_fee,
                ts_event=ts_event,
                ts_init=self._clock.timestamp_ns(),
                info={"market_type": market.market_type or "spot"},
            )
        else:
            # For futures/perps, would need to create appropriate instrument type
            self._log.warning(f"Market type {market.market_type} not yet supported for {market.symbol}")
            return

        self.add(instrument)