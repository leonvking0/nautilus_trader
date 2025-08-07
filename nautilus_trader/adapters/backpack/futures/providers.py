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
"""
Backpack Exchange futures instrument provider.
"""

from decimal import Decimal

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.parsing import parse_instrument_id
from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
from nautilus_trader.adapters.backpack.schemas.market import BackpackMarket
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


class BackpackFuturesInstrumentProvider(BackpackInstrumentProvider):
    """
    Provides futures instruments from the Backpack Exchange.
    
    Parameters
    ----------
    http_client : BackpackHttpClient
        The Backpack HTTP client.
    logger : Logger
        The logger for the provider.
    clock : LiveClock
        The clock for the provider.
    config : InstrumentProviderConfig, optional
        The instrument provider configuration.
    """
    
    def __init__(
        self,
        http_client: BackpackHttpClient,
        logger: Logger,
        clock: LiveClock,
        config: InstrumentProviderConfig | None = None,
    ) -> None:
        super().__init__(
            client=http_client,
            clock=clock,
            config=config,
        )
        
        self._log.info("BackpackFuturesInstrumentProvider initialized", LogColor.GREEN)
    
    async def load_all_async(self, filters: dict | None = None) -> None:
        """
        Load all futures instruments from the exchange.
        
        Parameters
        ----------
        filters : dict, optional
            The filters to apply to instruments.
        """
        try:
            markets = await self._http_client.fetch_markets()
            
            futures_count = 0
            for market in markets:
                # Filter for futures markets
                if market.marketType not in ["Futures", "Perpetual"]:
                    continue
                
                # Apply custom filters if provided
                if filters:
                    if "symbol" in filters and market.symbol != filters["symbol"]:
                        continue
                
                # Parse to instrument
                instrument = self._parse_futures_market(market)
                if instrument:
                    self.add(instrument)
                    futures_count += 1
            
            self._log.info(
                f"Loaded {futures_count} futures instruments from {len(markets)} total markets",
                LogColor.GREEN,
            )
            
        except Exception as e:
            self._log.error(f"Failed to load futures instruments: {e}")
    
    def _parse_futures_market(self, market: BackpackMarket) -> Instrument | None:
        """
        Parse a Backpack market to a futures instrument.
        
        Parameters
        ----------
        market : BackpackMarket
            The market data to parse.
            
        Returns
        -------
        Instrument | None
            The parsed instrument, or None if not a futures market.
        """
        # Skip non-futures markets
        if market.marketType not in ["Futures", "Perpetual"]:
            return None
        
        try:
            # Create instrument ID
            symbol = Symbol(market.symbol)
            instrument_id = InstrumentId(symbol, BACKPACK_VENUE)
            
            # Parse base and quote currencies
            if "_" in market.symbol:
                base_str, quote_str = market.symbol.split("_", 1)
                # Remove _PERP suffix if present
                if quote_str.endswith("_PERP"):
                    quote_str = quote_str[:-5]
            else:
                # Handle symbols without underscore
                base_str = market.symbol[:-4] if market.symbol.endswith("USDT") else market.symbol[:-3]
                quote_str = "USDT" if market.symbol.endswith("USDT") else "USD"
            
            # For perpetuals, use CryptoPerpetual
            if market.marketType == "Perpetual":
                return CryptoPerpetual(
                    instrument_id=instrument_id,
                    raw_symbol=symbol,
                    base_currency=base_str,
                    quote_currency=USDT,  # Assuming USDT settled
                    settlement_currency=USDT,
                    is_inverse=False,  # Assuming linear/USDT margined
                    price_precision=market.filters.price.precision,
                    size_precision=market.filters.quantity.precision,
                    price_increment=Price.from_str(market.filters.price.minPrice),
                    size_increment=Quantity.from_str(market.filters.quantity.minQuantity),
                    max_quantity=Quantity.from_str(market.filters.quantity.maxQuantity) 
                        if market.filters.quantity.maxQuantity else None,
                    min_quantity=Quantity.from_str(market.filters.quantity.minQuantity),
                    max_notional=Money(
                        Decimal(market.filters.quantity.maxQuantity) * Decimal(market.filters.price.maxPrice),
                        USDT,
                    ) if market.filters.quantity.maxQuantity and market.filters.price.maxPrice else None,
                    min_notional=Money(
                        Decimal(market.filters.quantity.minQuantity) * Decimal(market.filters.price.minPrice),
                        USDT,
                    ) if market.filters.quantity.minQuantity and market.filters.price.minPrice else None,
                    max_price=Price.from_str(market.filters.price.maxPrice) 
                        if market.filters.price.maxPrice else None,
                    min_price=Price.from_str(market.filters.price.minPrice) 
                        if market.filters.price.minPrice else None,
                    margin_init=Decimal("0.01"),  # 1% initial margin (100x max leverage)
                    margin_maint=Decimal("0.005"),  # 0.5% maintenance margin
                    maker_fee=Decimal(market.fees.maker) / 10000,  # Convert from basis points
                    taker_fee=Decimal(market.fees.taker) / 10000,  # Convert from basis points
                    ts_event=millis_to_nanos(market.created),
                    ts_init=self._clock.timestamp_ns(),
                )
            
            # For dated futures, would use CryptoFuture (not implemented yet)
            # TODO: Add support for dated futures when needed
            
            return None
            
        except Exception as e:
            self._log.error(f"Failed to parse futures market {market.symbol}: {e}")
            return None