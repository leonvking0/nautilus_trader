# Backpack Exchange Perpetuals Integration Guide

## Overview

This guide covers the complete integration of Backpack Exchange perpetual futures trading in NautilusTrader. The integration provides full support for perpetual contracts, including advanced order types, position management, margin calculations, and funding mechanisms.

## Features

### Core Functionality
- ✅ **Perpetual Instruments**: Full CryptoPerpetual instrument support
- ✅ **Real-time Market Data**: Mark price, funding rate, open interest streams
- ✅ **Position Management**: Comprehensive position tracking and P&L calculations
- ✅ **Margin System**: Tiered margin, leverage control, liquidation monitoring
- ✅ **Funding Mechanism**: Automatic funding payment tracking and calculations
- ✅ **Advanced Orders**: Reduce-only, post-only, stop-loss, take-profit
- ✅ **Risk Management**: Pre-trade checks, liquidation monitoring, ADL handling

### Data Streams
- Order book updates (depth snapshots and deltas)
- Trade ticks
- Mark price updates
- Funding rate changes
- Position updates
- Open interest data
- Liquidation events

## Getting Started

### Prerequisites

1. **Backpack Account**: Create an account at [backpack.exchange](https://backpack.exchange)
2. **API Credentials**: Generate API key and secret from the Backpack dashboard
3. **Environment Setup**: Configure your environment variables

```bash
export BACKPACK_API_KEY="your_api_key"
export BACKPACK_API_SECRET="your_api_secret"
```

### Installation

Ensure you have the latest version of NautilusTrader with Backpack support:

```bash
# Install with all dependencies
uv sync --all-groups --all-extras

# Build the project
make build-debug
```

## Configuration

### Basic Configuration

```python
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import TradingNodeConfig

config = TradingNodeConfig(
    trader_id="TRADER-001",
    data_clients={
        "BACKPACK": BackpackDataClientConfig(
            api_key=os.getenv("BACKPACK_API_KEY"),
            api_secret=os.getenv("BACKPACK_API_SECRET"),
            base_url_http="https://api.backpack.exchange",
            base_url_ws="wss://ws.backpack.exchange",
            testnet=False,  # Use True for testnet
            instrument_provider=InstrumentProviderConfig(
                load_all=True,  # Load all instruments including perpetuals
            ),
        ),
    },
    exec_clients={
        "BACKPACK": BackpackExecClientConfig(
            api_key=os.getenv("BACKPACK_API_KEY"),
            api_secret=os.getenv("BACKPACK_API_SECRET"),
            base_url_http="https://api.backpack.exchange",
            base_url_ws="wss://ws.backpack.exchange",
            testnet=False,
            instrument_provider=InstrumentProviderConfig(
                load_all=True,
            ),
        ),
    },
)
```

## Trading Perpetuals

### Basic Trading Example

```python
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

class PerpetualTradingStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.instrument_id = InstrumentId.from_str("SOL_USDC_PERP.BACKPACK")
    
    def on_start(self):
        # Subscribe to perpetual market data
        self.subscribe_quote_ticks(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        
        # Subscribe to perpetual-specific data
        self.subscribe_data(
            data_type=DataType(CustomData, metadata={"type": "mark_price"}),
            client_id=ClientId("BACKPACK"),
        )
    
    def place_perpetual_order(self):
        # Get instrument for precision
        instrument = self.cache.instrument(self.instrument_id)
        
        # Create order with leverage consideration
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(0.1, instrument.size_precision),
            price=Price(100.50, instrument.price_precision),
            time_in_force=TimeInForce.GTC,
            reduce_only=False,  # False to open position
        )
        
        self.submit_order(order)
```

### Advanced Order Types

#### Reduce-Only Orders
Used to only reduce existing positions without opening new ones:

```python
# Close a long position
close_order = self.order_factory.limit(
    instrument_id=self.instrument_id,
    order_side=OrderSide.SELL,
    quantity=position_size,
    price=exit_price,
    reduce_only=True,  # Only reduces position
)
```

#### Stop-Loss and Take-Profit
Attach SL/TP to orders:

```python
# Order with stop-loss and take-profit
order = self.order_factory.limit_with_stop_loss_take_profit(
    instrument_id=self.instrument_id,
    order_side=OrderSide.BUY,
    quantity=quantity,
    price=entry_price,
    stop_loss=Price(95.00, precision),  # Stop at $95
    take_profit=Price(110.00, precision),  # Take profit at $110
)
```

## Position Management

### Monitoring Positions

The integration provides comprehensive position tracking:

```python
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager

class PositionMonitorStrategy(Strategy):
    def on_position_update(self, position):
        # Access position details
        print(f"Symbol: {position.symbol}")
        print(f"Side: {position.side}")
        print(f"Size: {position.quantity}")
        print(f"Entry Price: {position.entry_price}")
        print(f"Mark Price: {position.mark_price}")
        print(f"Unrealized PnL: {position.unrealized_pnl}")
        print(f"Margin Ratio: {position.margin_ratio}")
        print(f"Liquidation Price: {position.liquidation_price}")
```

### Position Metrics

Key metrics available for each position:
- **Unrealized P&L**: Current profit/loss based on mark price
- **Realized P&L**: Locked-in profit/loss from partial closes
- **Margin Ratio**: Current margin utilization
- **Liquidation Price**: Price at which position will be liquidated
- **Funding Payments**: Accumulated funding paid/received

## Margin and Leverage

### Setting Leverage

```python
from nautilus_trader.adapters.backpack.futures.http.position import BackpackFuturesPositionHttpAPI

async def set_leverage(client, symbol: str, leverage: int):
    """Set leverage for a symbol (1-125x)."""
    position_api = BackpackFuturesPositionHttpAPI(client)
    await position_api.modify_leverage(symbol, leverage)
```

### Margin Calculations

The integration includes a comprehensive margin calculator:

```python
from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator

calculator = BackpackFuturesMarginCalculator()

# Calculate initial margin requirement
initial_margin = calculator.calculate_initial_margin(
    notional_value=Decimal("10000"),  # $10,000 position
    leverage=Decimal("10"),  # 10x leverage
)

# Calculate maintenance margin
maint_margin = calculator.calculate_maintenance_margin(
    notional_value=Decimal("10000"),
    symbol="SOL_USDC_PERP",
)

# Calculate liquidation price
liq_price = calculator.calculate_liquidation_price(
    entry_price=Decimal("100"),
    position_size=Decimal("10"),
    side="LONG",
    leverage=Decimal("10"),
    balance=Decimal("1000"),
)
```

### Margin Types

Backpack supports two margin types:
- **Cross Margin**: Shares margin across all positions
- **Isolated Margin**: Margin isolated to specific position

```python
# Modify margin type
await position_api.modify_margin_type("SOL_USDC_PERP", "ISOLATED")

# Add margin to isolated position
await position_api.add_margin("SOL_USDC_PERP", "100.0")  # Add $100
```

## Funding Mechanism

### Understanding Funding

Perpetual contracts use a funding mechanism to keep prices aligned with spot:
- **Positive Funding Rate**: Longs pay shorts
- **Negative Funding Rate**: Shorts pay longs
- **Payment Frequency**: Every 8 hours (00:00, 08:00, 16:00 UTC)

### Tracking Funding

```python
from nautilus_trader.adapters.backpack.futures.funding import BackpackFundingManager

class FundingStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.funding_manager = None
    
    def on_start(self):
        # Initialize funding manager
        self.funding_manager = BackpackFundingManager(
            client=self.client,
            msgbus=self.msgbus,
            clock=self.clock,
        )
    
    def on_funding_update(self, data):
        # Update funding rate
        self.funding_manager.update_funding_rate(
            symbol=data.symbol,
            funding_rate=data.funding_rate,
            next_funding_time=data.next_funding_time,
        )
        
        # Calculate expected payment
        payment = self.funding_manager.calculate_funding_payment(
            symbol=data.symbol,
            mark_price=data.mark_price,
        )
        
        if payment:
            self.log.info(f"Expected funding: {payment.payment}")
```

## Risk Management

### Liquidation Monitoring

The integration includes comprehensive liquidation monitoring:

```python
from nautilus_trader.adapters.backpack.futures.risk import BackpackLiquidationMonitor

monitor = BackpackLiquidationMonitor(msgbus, clock, cache)

# Check position health
risk_level = monitor.check_position_health(position, mark_price)
# Returns: RiskLevel.SAFE, WARNING, DANGER, or CRITICAL

# Monitor all positions
monitor.start_monitoring(check_interval_ms=1000)
```

### Risk Levels

- **SAFE**: Margin ratio < 50%
- **WARNING**: Margin ratio 50-70%
- **DANGER**: Margin ratio 70-90%
- **CRITICAL**: Margin ratio > 90% (near liquidation)

### Pre-Trade Risk Checks

```python
def validate_order_risk(self, order):
    """Validate order against risk parameters."""
    # Check leverage limits
    if self.calculate_leverage(order) > self.max_leverage:
        return False
    
    # Check position limits
    if self.get_position_count() >= self.max_positions:
        return False
    
    # Check notional limits
    notional = order.quantity * order.price
    if notional > self.max_notional:
        return False
    
    return True
```

## Example Strategies

### 1. Market Making

See `examples/live/backpack/perpetual_market_maker.py`:
- Maintains bid/ask spreads
- Manages inventory risk
- Uses reduce-only orders for position management

### 2. Funding Arbitrage

See `examples/live/backpack/funding_arbitrage.py`:
- Monitors funding rates across instruments
- Enters positions to capture funding
- Manages funding payment timing

### 3. Basis Trading

See `examples/live/backpack/basis_trading.py`:
- Trades spot-perpetual basis
- Maintains delta-neutral positions
- Captures basis convergence

## Testing

### Unit Tests

Run perpetuals-specific unit tests:

```bash
# Test margin calculations
uv run pytest tests/unit_tests/adapters/backpack/futures/test_margin.py -v

# Test position management
uv run pytest tests/unit_tests/adapters/backpack/futures/test_position_manager.py -v

# Test risk monitoring
uv run pytest tests/unit_tests/adapters/backpack/futures/test_risk.py -v
```

### Integration Tests

```bash
# Test complete workflows
uv run pytest tests/integration_tests/adapters/backpack/futures/ -v
```

### Live Testing

Test with minimal order sizes:

```bash
# Test perpetuals with 0.01 SOL orders
python examples/live/backpack/test_perpetuals_live.py

# Advanced testing with WebSocket streams
python examples/live/backpack/test_advanced_perpetuals.py
```

## Performance Optimization

### Best Practices

1. **Cache Management**
   - Cache frequently accessed data (positions, margin requirements)
   - Use position manager's built-in caching

2. **WebSocket Optimization**
   - Subscribe only to required streams
   - Use stream filtering where possible

3. **Order Management**
   - Batch order operations when possible
   - Use reduce-only for closing positions

4. **Margin Efficiency**
   - Monitor margin ratio continuously
   - Maintain buffer above maintenance margin
   - Use isolated margin for high-risk positions

## Troubleshooting

### Common Issues

#### Position Sync Issues
```python
# Force position reconciliation
await execution_client._reconcile_positions()
```

#### Funding Rate Not Updating
```python
# Check WebSocket subscription
self.subscribe_data(
    data_type=DataType(CustomData, metadata={"type": "funding_rate"}),
    client_id=ClientId("BACKPACK"),
)
```

#### Liquidation Price Calculation
```python
# Verify calculation inputs
print(f"Entry Price: {entry_price}")
print(f"Position Size: {position_size}")
print(f"Leverage: {leverage}")
print(f"Account Balance: {balance}")
```

### Debug Mode

Enable debug logging for detailed information:

```python
config = TradingNodeConfig(
    logging=LoggingConfig(
        log_level="DEBUG",
        log_colors=True,
    ),
)
```

## API Reference

### Data Types

```python
# Mark price update
class MarkPriceUpdate:
    symbol: str
    mark_price: Decimal
    index_price: Decimal
    funding_rate: Decimal
    next_funding_time: int

# Position update
class PositionUpdate:
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    margin_ratio: Decimal
```

### WebSocket Streams

```python
# Available streams
"account.positionUpdate"  # Position updates
"markPrice.<symbol>"      # Mark price updates
"fundingRate.<symbol>"    # Funding rate updates
"liquidation"            # Liquidation events
"openInterest.<symbol>"  # Open interest updates
```

## Safety Guidelines

### Production Deployment

1. **Start Small**: Begin with minimum position sizes
2. **Monitor Closely**: Set up alerts for margin ratio changes
3. **Use Stop Losses**: Always set stop-loss orders
4. **Test Thoroughly**: Run 24-hour tests before production
5. **Have Contingency**: Prepare manual intervention procedures

### Risk Parameters

Recommended initial settings:
- Maximum leverage: 5x
- Maximum position size: 1% of account
- Stop loss: 2% from entry
- Margin buffer: 50% above maintenance

## Conclusion

The Backpack perpetuals integration provides comprehensive support for trading perpetual futures contracts. With proper risk management and testing, it enables sophisticated trading strategies while maintaining safety and reliability.

For additional support:
- GitHub Issues: [nautilus_trader/issues](https://github.com/nautechsystems/nautilus_trader/issues)
- Documentation: [docs.nautilustrader.io](https://docs.nautilustrader.io)
- Backpack API Docs: [docs.backpack.exchange](https://docs.backpack.exchange)