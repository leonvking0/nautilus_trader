# Market Making Strategy Backtesting with OrderBook Data

## Table of Contents
1. [Introduction](#introduction)
2. [Understanding Order Matching in NautilusTrader](#understanding-order-matching)
3. [Data Collection](#data-collection)
4. [Strategy Design](#strategy-design)
5. [Backtesting Setup](#backtesting-setup)
6. [Performance Analysis](#performance-analysis)
7. [Advanced Topics](#advanced-topics)
8. [Complete Example](#complete-example)

## Introduction

This tutorial demonstrates how to backtest a market making strategy using orderbook data in NautilusTrader. Market making is a trading strategy where you continuously provide liquidity to the market by placing limit orders on both sides of the orderbook, profiting from the bid-ask spread while managing inventory risk.

### Prerequisites

- Python 3.11+ installed
- NautilusTrader installed (`pip install -U nautilus_trader`)
- Basic understanding of market making concepts
- Familiarity with orderbook dynamics

### Key Concepts

**Market Making Components:**
- **Spread**: The difference between bid and ask prices
- **Inventory Risk**: Risk from holding positions
- **Queue Position**: Your order's position in the orderbook queue
- **Fill Probability**: Likelihood of your order being executed

## Understanding Order Matching

NautilusTrader's backtesting engine simulates realistic order matching through several components:

### OrderMatchingEngine

The `OrderMatchingEngine` is the core component that simulates how orders are filled:

```python
# Located in nautilus_trader/backtest/matching_engine.pyx
class OrderMatchingEngine:
    def __init__(
        self,
        instrument: Instrument,
        fill_model: FillModel,
        book_type: BookType,
        ...
    ):
        # Maintains internal orderbook
        self._book = OrderBook(instrument_id, book_type)
        
        # Core matching logic
        self._core = MatchingCore(
            instrument_id=instrument.id,
            trigger_stop_order=self.trigger_stop_order,
            fill_market_order=self.fill_market_order,
            fill_limit_order=self.fill_limit_order,
        )
```

### FillModel

The `FillModel` provides probabilistic fill dynamics:

```python
class FillModel:
    def __init__(
        self,
        prob_fill_on_limit=1.0,  # Probability of limit order fill
        prob_fill_on_stop=1.0,   # Probability of stop order fill
        prob_slippage=0.0,       # Probability of slippage
    ):
        ...
```

For market making, realistic fill probabilities are crucial:
- **prob_fill_on_limit**: 0.7-0.9 (not all limit orders at the touch get filled)
- **prob_slippage**: 0.05-0.15 (occasional slippage during volatile conditions)

### Order Matching Process

1. **Market Data Arrival**: Trade tick, quote, or orderbook delta arrives
2. **Orderbook Update**: Internal orderbook is updated
3. **Order Evaluation**: Check if any orders should be triggered or filled
4. **Fill Simulation**: Use FillModel to determine if order fills
5. **Execution**: Generate fill events with realistic prices

## Data Collection

### Collecting Live OrderBook Data

The data collection script (`examples/backtest/collect_backpack_mm_data.py`) demonstrates how to collect orderbook and trade data:

```python
#!/usr/bin/env python3
import asyncio
from nautilus_trader.persistence.catalog import ParquetDataCatalog

class BackpackDataCollector:
    def __init__(self, symbol="SOL_USDC", duration_mins=20):
        self.symbol = symbol
        self.duration_mins = duration_mins
        self.orderbook_deltas = []
        self.trade_ticks = []
    
    async def collect_data(self):
        # Connect to WebSocket
        await self.connect_websocket()
        
        # Subscribe to streams
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [
                f"depth.{self.symbol}",    # Orderbook updates
                f"trades.{self.symbol}",   # Trade stream
            ],
        }
        
        # Collect for specified duration
        end_time = datetime.now() + timedelta(minutes=self.duration_mins)
        while datetime.now() < end_time:
            msg = await self.ws.receive()
            await self.process_ws_message(msg)
    
    def save_to_catalog(self):
        catalog = ParquetDataCatalog(self.catalog_path)
        catalog.write_data(self.orderbook_deltas)
        catalog.write_data(self.trade_ticks)
```

### Running Data Collection

```bash
# Collect 20 minutes of SOL-USDC data
python examples/backtest/collect_backpack_mm_data.py

# With custom parameters
BACKPACK_SYMBOL=BTC_USDC COLLECTION_DURATION_MINS=30 python collect_backpack_mm_data.py
```

### Data Types

**OrderBookDelta**: Represents changes to the orderbook
```python
OrderBookDelta(
    instrument_id=instrument_id,
    action=BookAction.UPDATE,  # ADD, UPDATE, DELETE, CLEAR
    order=BookOrder(
        side=OrderSide.BUY,
        price=Price.from_str("123.45"),
        size=Quantity.from_str("10.0"),
    ),
    ts_event=timestamp_ns,
)
```

**TradeTick**: Represents executed trades
```python
TradeTick(
    instrument_id=instrument_id,
    price=Price.from_str("123.45"),
    size=Quantity.from_str("1.5"),
    aggressor_side=AggressorSide.BUYER,
    ts_event=timestamp_ns,
)
```

## Strategy Design

### Simple Market Making Strategy

The strategy (`examples/strategies/simple_mm_backtest.py`) implements core market making logic:

```python
class SimpleMMBacktest(Strategy):
    def __init__(self, config: SimpleMMBacktestConfig):
        # Core parameters
        self.base_spread_bps = config.base_spread_bps
        self.max_position = config.max_position
        self.inventory_skew_factor = config.inventory_skew_factor
        
        # Maintain local orderbook
        self.orderbook = OrderBook(
            instrument_id=self.instrument_id,
            book_type=BookType.L2_MBP,
        )
    
    def on_order_book_deltas(self, deltas: OrderBookDeltas):
        """Handle orderbook updates."""
        # Update local orderbook
        self.orderbook.apply_deltas(deltas)
        
        # Calculate orderbook imbalance
        imbalance = self._calculate_orderbook_imbalance()
        
        # Update orders based on new market state
        if self._should_update_orders():
            self._update_orders()
```

### Key Strategy Components

#### 1. Dynamic Spread Adjustment

```python
def _calculate_dynamic_spread(self):
    """Adjust spread based on market conditions."""
    base_spread = self.base_spread_bps
    
    # Volatility adjustment using ATR
    if self.atr and self.atr.initialized:
        volatility_ratio = self.atr.value / self.mid_price
        volatility_multiplier = 1 + (volatility_ratio * 10)
        base_spread = int(base_spread * volatility_multiplier)
    
    # Apply limits
    self.current_spread_bps = max(
        self.min_spread_bps,
        min(base_spread, self.max_spread_bps)
    )
```

#### 2. Inventory Management

```python
def _calculate_inventory_adjusted_spreads(self, position_qty, imbalance):
    """Adjust spreads based on inventory."""
    # If long, widen bid spread and tighten ask spread
    inventory_adjustment = position_qty * self.inventory_skew_factor
    
    # Orderbook imbalance adjustment
    imbalance_adjustment = imbalance * 0.25 * base_spread
    
    bid_spread = base_spread + inventory_adjustment + imbalance_adjustment
    ask_spread = base_spread - inventory_adjustment - imbalance_adjustment
    
    return bid_spread, ask_spread
```

#### 3. OrderBook Imbalance

```python
def _calculate_orderbook_imbalance(self) -> Decimal:
    """Calculate orderbook imbalance for directional bias."""
    bid_volume = sum(level.size for level in self.orderbook.bids[:5])
    ask_volume = sum(level.size for level in self.orderbook.asks[:5])
    
    total_volume = bid_volume + ask_volume
    if total_volume == 0:
        return Decimal("0")
    
    # Positive = more bids (bullish), Negative = more asks (bearish)
    return (bid_volume - ask_volume) / total_volume
```

#### 4. Risk Management

```python
def _check_risk_limits(self):
    """Monitor and enforce risk limits."""
    position = self.portfolio.net_position(self.instrument_id)
    
    # Position limits
    if abs(position.quantity) >= self.max_position:
        self._reduce_position()
    
    # Stop loss
    pnl_pct = position.unrealized_pnl / position.notional_value
    if pnl_pct < -self.stop_loss_pct:
        self._close_position()
```

## Backtesting Setup

### Running the Backtest

The backtest runner (`examples/backtest/run_mm_backtest.py`) configures and executes the backtest:

```python
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.models import FillModel

# Configure realistic fill model for market making
fill_model = FillModel(
    prob_fill_on_limit=0.8,   # 80% fill probability at touch
    prob_fill_on_stop=0.95,   # 95% for stop orders
    prob_slippage=0.1,        # 10% chance of slippage
    random_seed=42,
)

# Configure venue
venues_configs = [
    BacktestVenueConfig(
        name="BACKPACK",
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=["10000 USDC", "100 SOL"],
        book_type=BookType.L2_MBP,
        fill_model=fill_model,
        latency_model=LatencyModel(
            base_latency_nanos=10_000_000,  # 10ms base latency
        ),
    ),
]

# Run backtest
node = BacktestNode(configs=[config])
results = node.run()
```

### Configuration Parameters

```python
config = SimpleMMBacktestConfig(
    instrument_id="SOL_USDC.BACKPACK",
    
    # Spread parameters
    base_spread_bps=20,        # 0.20% base spread
    min_spread_bps=10,         # 0.10% minimum
    max_spread_bps=100,        # 1.00% maximum
    
    # Risk parameters
    max_position=Decimal("5.0"),     # Max 5 SOL
    inventory_skew_factor=Decimal("0.1"),
    stop_loss_pct=Decimal("0.02"),   # 2% stop loss
    
    # Execution
    update_interval_seconds=5,  # Update orders every 5 seconds
    order_levels=1,             # Number of price levels
)
```

### Running the Complete Pipeline

```bash
# Step 1: Collect data
python examples/backtest/collect_backpack_mm_data.py

# Step 2: Run backtest
python examples/backtest/run_mm_backtest.py

# Step 3: Analyze results (optional)
python -c "from examples.analysis.mm_performance import analyze_backtest_results; analyze_backtest_results()"
```

## Performance Analysis

### Market Making Metrics

The performance analyzer (`examples/analysis/mm_performance.py`) calculates specialized metrics:

```python
class MarketMakingAnalyzer:
    def calculate_spread_metrics(self):
        """Calculate spread capture metrics."""
        # Realized spread
        realized_spread_bps = (avg_sell_price - avg_buy_price) / avg_buy_price * 10000
        
        # Match trades within time windows
        for buy in buy_fills:
            matched_sells = find_sells_within_window(buy.timestamp, window=1_minute)
            spread_bps = (sell.price - buy.price) / buy.price * 10000
        
        return {
            'realized_spread_bps': realized_spread_bps,
            'median_spread_bps': np.median(spreads),
        }
    
    def calculate_inventory_metrics(self):
        """Calculate inventory risk metrics."""
        return {
            'max_position': positions['peak_qty'].max(),
            'inventory_turnover': total_volume / avg_inventory,
            'sharpe_per_unit': returns.mean() / returns.std(),
        }
```

### Key Performance Indicators

1. **Spread Metrics**
   - Realized spread vs quoted spread
   - Spread capture rate
   - Average spread in basis points

2. **Inventory Metrics**
   - Maximum position size
   - Inventory turnover ratio
   - Average holding time

3. **Execution Quality**
   - Fill rate by side
   - Order cancellation rate
   - Time to fill

4. **PnL Attribution**
   - Spread capture PnL
   - Directional PnL
   - Risk-adjusted returns

### Visualization

```python
analyzer = MarketMakingAnalyzer(engine, venue)

# Generate comprehensive plot
analyzer.plot_performance()

# Save metrics to CSV
analyzer.save_metrics_to_csv("mm_metrics.csv")
```

The visualization includes:
- Cumulative PnL curve
- Inventory evolution
- Spread distribution
- Fill rates by side
- PnL attribution pie chart
- Hourly trading activity

## Advanced Topics

### Custom Fill Models

Create custom fill models for more sophisticated queue position modeling:

```python
class QueuePositionFillModel(FillModel):
    def get_orderbook_for_fill_simulation(self, instrument, order, best_bid, best_ask):
        """Simulate orderbook with queue position logic."""
        # Create synthetic orderbook
        book = OrderBook(instrument.id, BookType.L3_MBO)
        
        # Add orders representing queue ahead
        queue_size = self._estimate_queue_size(order.price, best_bid, best_ask)
        
        for i in range(queue_size):
            book.add(BookOrder(
                side=order.side,
                price=order.price,
                size=Quantity.from_int(100),
                order_id=i,
            ))
        
        return book
```

### OrderBook Imbalance Signals

Use orderbook imbalance for predictive signals:

```python
def calculate_advanced_imbalance(orderbook):
    """Calculate weighted orderbook imbalance."""
    weighted_bid_volume = 0
    weighted_ask_volume = 0
    
    for i, level in enumerate(orderbook.bids[:10]):
        # Weight decreases with distance from mid
        weight = 1 / (i + 1)
        weighted_bid_volume += level.size * weight
    
    for i, level in enumerate(orderbook.asks[:10]):
        weight = 1 / (i + 1)
        weighted_ask_volume += level.size * weight
    
    return (weighted_bid_volume - weighted_ask_volume) / (weighted_bid_volume + weighted_ask_volume)
```

### Multi-Level Order Placement

Place orders at multiple price levels:

```python
def place_ladder_orders(self, side, base_spread, levels=3):
    """Place multiple orders at increasing spreads."""
    for level in range(levels):
        # Wider spread for further levels
        level_spread = base_spread * (1 + level * 0.1)
        
        # Smaller size for further levels
        level_size = self.base_size * (1 - level * 0.2)
        
        price = self.calculate_price(side, level_spread)
        self.submit_limit_order(side, price, level_size)
```

### Adaptive Parameter Tuning

Dynamically adjust parameters based on market conditions:

```python
def adapt_parameters(self):
    """Adapt strategy parameters to market regime."""
    recent_volatility = self.calculate_recent_volatility()
    recent_volume = self.calculate_recent_volume()
    
    # High volatility -> wider spreads
    if recent_volatility > self.high_vol_threshold:
        self.current_spread_multiplier = 1.5
    
    # Low volume -> reduce position limits
    if recent_volume < self.low_volume_threshold:
        self.current_max_position = self.max_position * 0.5
```

## Complete Example

Here's a complete example workflow:

```python
#!/usr/bin/env python3
"""Complete market making backtest example."""

import asyncio
from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.persistence.catalog import ParquetDataCatalog

async def main():
    # Step 1: Collect Data
    print("Step 1: Collecting live data...")
    from examples.backtest.collect_backpack_mm_data import BackpackDataCollector
    
    collector = BackpackDataCollector(
        symbol="SOL_USDC",
        duration_mins=20,
        catalog_path="mm_catalog",
    )
    await collector.collect_data()
    collector.save_to_catalog()
    print(f"Collected {len(collector.trade_ticks)} trades")
    
    # Step 2: Run Backtest
    print("\nStep 2: Running backtest...")
    from examples.backtest.run_mm_backtest import run_backtest
    
    results = run_backtest(
        catalog_path="mm_catalog",
        symbol="SOL_USDC",
        starting_balance_quote="10000",
        starting_balance_base="100",
    )
    
    # Step 3: Analyze Results
    print("\nStep 3: Analyzing performance...")
    from examples.analysis.mm_performance import analyze_backtest_results
    from nautilus_trader.model.identifiers import Venue
    
    engine = results['engine']
    analyzer = analyze_backtest_results(
        engine=engine,
        venue=Venue("BACKPACK"),
        output_dir=Path("backtest_results"),
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("Backtest Summary")
    print("=" * 60)
    
    metrics = analyzer.calculate_spread_metrics()
    print(f"Realized Spread: {metrics.get('realized_spread_bps', 0):.1f} bps")
    
    inventory = analyzer.calculate_inventory_metrics()
    print(f"Max Position: {inventory.get('max_position', 0):.2f}")
    print(f"Inventory Turnover: {inventory.get('inventory_turnover', 0):.1f}x")
    
    fills = analyzer.calculate_fill_metrics()
    print(f"Fill Rate: {fills.get('fill_rate', 0):.1f}%")
    
    attribution = analyzer.calculate_pnl_attribution()
    print(f"Total PnL: ${attribution.get('total_pnl', 0):.2f}")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
```

## Best Practices

### 1. Data Quality
- Ensure orderbook data is complete and time-ordered
- Handle missing data gracefully
- Validate timestamps are monotonically increasing

### 2. Realistic Simulation
- Use appropriate fill probabilities (not 100%)
- Include latency modeling
- Consider partial fills

### 3. Risk Management
- Always implement position limits
- Use stop losses for tail risk
- Monitor inventory imbalance

### 4. Performance Optimization
- Cache frequently accessed data
- Use vectorized operations where possible
- Profile code for bottlenecks

### 5. Strategy Validation
- Test on multiple market conditions
- Validate against known edge cases
- Compare with theoretical expectations

## Troubleshooting

### Common Issues

**No fills executed:**
- Check if spread is too wide
- Verify orderbook data is being received
- Ensure fill probability is not too low

**Excessive position buildup:**
- Inventory skew factor may be too small
- Position limits not properly enforced
- Check order cancellation logic

**Poor performance:**
- Spread may be too tight for market conditions
- Transaction costs not properly accounted
- Adverse selection from orderbook imbalance

## Conclusion

This tutorial demonstrated how to:
1. Collect live orderbook and trade data
2. Implement a market making strategy with inventory management
3. Run realistic backtests with probabilistic fill models
4. Analyze performance with specialized metrics

Market making in backtesting requires careful attention to:
- Order matching mechanics
- Queue position modeling
- Inventory risk management
- Realistic fill probabilities

The provided code examples can be extended for more sophisticated strategies including:
- Multi-asset market making
- Cross-exchange arbitrage
- Options market making
- Statistical arbitrage

## References

- [NautilusTrader Documentation](https://nautilustrader.io/docs/)
- [Market Making: Theory and Practice](https://arxiv.org/abs/1708.03098)
- [Optimal Market Making](https://arxiv.org/abs/1210.5781)

## Next Steps

1. Experiment with different `FillModel` configurations
2. Implement more sophisticated orderbook signals
3. Add machine learning for parameter optimization
4. Test on different market conditions and instruments
5. Integrate with live trading after successful backtesting