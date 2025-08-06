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

"""Backpack spot instrument provider implementation."""

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
from nautilus_trader.common.component import LiveClock
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.identifiers import Venue


class BackpackSpotInstrumentProvider(BackpackInstrumentProvider):
    """
    Provides a means of loading spot instruments from the Backpack exchange.

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
        super().__init__(
            client=client,
            clock=clock,
            testnet=testnet,
            config=config,
            venue=venue,
        )

    async def load_all_async(self, filters: dict | None = None) -> None:
        """Load all spot instruments from the exchange."""
        # Add spot-specific filter
        if filters is None:
            filters = {}
        filters["market_type"] = "spot"
        
        await super().load_all_async(filters=filters)