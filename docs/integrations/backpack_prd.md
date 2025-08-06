# Backpack Exchange Integration - Product Requirements Document (PRD)

## Executive Summary

This document outlines the requirements for integrating Backpack Exchange into the NautilusTrader platform, providing comprehensive support for spot and perpetual futures trading with market data and order execution capabilities.

## Business Objectives

- **Expand Trading Venues**: Add Backpack Exchange to the list of supported exchanges in NautilusTrader
- **Enable Algorithmic Trading**: Support automated trading strategies on Backpack's spot and perpetual futures markets
- **Feature Parity**: Ensure the integration matches the quality and capabilities of existing exchange adapters
- **Unique Features**: Leverage Backpack's distinctive features including ED25519 authentication, RFQ system, and borrow/lend capabilities

## Stakeholders

- **Primary Users**: Algorithmic traders using NautilusTrader
- **Development Team**: NautilusTrader maintainers and contributors
- **Exchange**: Backpack Exchange API team
- **Community**: Open-source contributors and users

## Functional Requirements

### 1. Authentication & Security

#### 1.1 ED25519 Signature Authentication
- Implement ED25519 keypair signing (distinct from typical HMAC-SHA256)
- Support base64 encoding for keys and signatures
- Handle signature generation for all authenticated endpoints

#### 1.2 Request Signing Protocol
- Generate proper signing strings with alphabetically ordered parameters
- Include instruction types in signatures (e.g., `orderExecute`, `accountQuery`)
- Add required headers: `X-Timestamp`, `X-Window`, `X-API-Key`, `X-Signature`
- Support batch order signing with concatenated instruction strings

#### 1.3 Credential Management
- Support API keys from environment variables (`BACKPACK_API_KEY`, `BACKPACK_API_SECRET`)
- Secure storage and handling of ED25519 private keys
- Support for testnet credentials separately

### 2. Market Data Features

#### 2.1 Real-time Data Streams
- **Order Book Data**
  - Depth updates (realtime, 200ms, and 1000ms aggregation options)
  - Book ticker (best bid/ask)
  - Incremental order book updates with sequence validation
  
- **Trade Data**
  - Public trade stream
  - Aggregated trade ticks
  - Sequential trade IDs
  
- **Price Data**
  - Quote ticks
  - Mark price (futures)
  - Index price
  - Funding rates
  
- **Market Statistics**
  - 24hr ticker statistics
  - Kline/candlestick data (multiple timeframes)
  - Open interest (futures)
  - Liquidation events

#### 2.2 Historical Data Requests
- Fetch historical klines/bars
- Query historical trades
- Request order book snapshots
- Support pagination for large datasets

#### 2.3 Instrument Management
- Fetch all available instruments
- Parse spot and perpetual futures specifications
- Handle instrument updates
- Cache instrument metadata
- Support periodic instrument refresh (configurable interval)

### 3. Order Execution Features

#### 3.1 Order Types
- **Basic Orders**
  - Market orders
  - Limit orders
  - Support for post-only orders
  
- **Advanced Orders**
  - Stop-loss orders
  - Take-profit orders
  - Reduce-only orders (futures)
  - Trigger orders

#### 3.2 Order Management
- Submit single orders
- Batch order submission (up to limits)
- Modify existing orders
- Cancel individual orders
- Cancel all orders
- Cancel by symbol
- Query open orders
- Query order history

#### 3.3 Order Lifecycle
- Handle order acceptance
- Process partial fills
- Track order expiration
- Handle order rejection with reasons
- Support self-trade prevention modes

### 4. Account Management

#### 4.1 Balance Management
- Query account balances
- Track available and locked balances
- Handle multi-asset collateral
- Monitor margin requirements

#### 4.2 Position Management (Futures)
- Track open positions
- Calculate unrealized PnL
- Monitor liquidation prices
- Handle position updates
- Support position mode (one-way/hedge)

#### 4.3 Transaction History
- Fetch deposit history
- Query withdrawal history
- Retrieve fill history
- Access funding payment history (futures)
- PnL history

### 5. Risk Management

#### 5.1 Pre-trade Checks
- Validate order parameters
- Check available balance
- Verify position limits
- Validate price bands

#### 5.2 Real-time Monitoring
- Track exposure limits
- Monitor margin levels
- Handle liquidation warnings
- Process ADL events

### 6. Advanced Features (Phase 2)

#### 6.1 RFQ System
- Submit RFQs
- Receive and respond to quotes
- Handle RFQ lifecycle events
- Support maker and taker roles

#### 6.2 Borrow/Lend Integration
- Query lending markets
- Submit borrow/lend orders
- Track interest payments
- Monitor collateral positions

#### 6.3 Strategy Orders
- Support Backpack's native strategy orders
- Handle strategy lifecycle
- Track strategy performance

## Non-Functional Requirements

### 1. Performance
- **Latency**: < 10ms for order submission (excluding network)
- **Throughput**: Handle 1000+ messages/second
- **Order Book Updates**: Process 100+ updates/second per symbol
- **Memory Usage**: Efficient memory management for large order books

### 2. Reliability
- **Uptime**: 99.9% availability
- **Reconnection**: Automatic WebSocket reconnection with exponential backoff
- **State Recovery**: Restore subscriptions after reconnection
- **Error Handling**: Graceful degradation on failures

### 3. Scalability
- Support 200 subscriptions per WebSocket connection
- Handle multiple concurrent connections (up to 20)
- Efficient message parsing and routing
- Horizontal scaling capability

### 4. Security
- Secure key storage
- No logging of sensitive data
- Input validation on all parameters
- Protection against replay attacks

### 5. Compatibility
- Python 3.10+ support
- Compatible with NautilusTrader architecture
- Follow existing adapter patterns
- Support both async and sync operations where applicable

### 6. Observability
- Comprehensive logging
- Performance metrics
- Error tracking
- Health checks

## Constraints & Limitations

### API Limitations
- Rate limits: 6000 req/min (spot), 2400 req/min (futures)
- WebSocket: 200 subscriptions per connection
- Order batch size limits
- Message size limits

### Technical Constraints
- ED25519 signature requirement (not HMAC)
- Microsecond timestamp precision
- Sequential order ID validation
- Specific instruction types for each operation

## Success Criteria

### Functional Success
- All core features implemented and tested
- Pass all unit tests (>90% coverage)
- Pass all integration tests
- Successfully trade on testnet for 24 hours

### Performance Success
- Meet all latency requirements
- Handle target throughput
- No memory leaks under load
- Stable operation under stress

### Quality Success
- Code follows NautilusTrader standards
- Comprehensive documentation
- Example strategies provided
- Peer review approved

## Risk Assessment

### Technical Risks
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| API changes | High | Medium | Version checking, monitoring changelog |
| ED25519 implementation issues | High | Low | Use established cryptography libraries |
| Rate limiting | Medium | High | Implement proper throttling and queuing |
| WebSocket instability | Medium | Medium | Robust reconnection logic |

### Business Risks
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Exchange downtime | High | Low | Graceful degradation, user notifications |
| Incomplete documentation | Medium | Medium | Direct communication with Backpack team |
| Low adoption | Low | Medium | Marketing, example strategies |

## Dependencies

### External Dependencies
- Backpack Exchange API
- `cryptography` library for ED25519
- `msgspec` for JSON parsing
- `nautilus_trader` core components

### Internal Dependencies
- WebSocketClient from nautilus_core
- LiveDataClient base classes
- LiveExecutionClient base classes
- Common nautilus types and enums

## Timeline & Milestones

### Phase 1: Foundation (Weeks 1-2)
- Project setup and structure
- Authentication implementation
- Basic HTTP client

### Phase 2: Market Data (Weeks 3-4)
- WebSocket client
- Data stream handlers
- Instrument provider

### Phase 3: Execution (Weeks 5-6)
- Order management
- Account management
- Position tracking

### Phase 4: Testing & Polish (Weeks 7-8)
- Comprehensive testing
- Documentation
- Performance optimization

## Acceptance Criteria

### Minimum Viable Product (MVP)
- [ ] Authenticate with ED25519
- [ ] Subscribe to market data
- [ ] Submit and cancel orders
- [ ] Track positions and balances
- [ ] Handle WebSocket reconnections

### Full Release
- [ ] All functional requirements met
- [ ] Performance targets achieved
- [ ] Documentation complete
- [ ] Example strategies working
- [ ] Community feedback incorporated

## Appendix

### A. API Endpoints Used
- Market Data: `/markets`, `/depth`, `/trades`, `/klines`
- Account: `/account`, `/balances`, `/positions`
- Trading: `/order`, `/orders`, `/fills`
- WebSocket: `wss://ws.backpack.exchange`

### B. Message Types
- Order updates: `orderAccepted`, `orderFilled`, `orderCancelled`
- Position updates: `positionOpened`, `positionClosed`, `positionAdjusted`
- Market data: `depth`, `trade`, `kline`, `ticker`

### C. References
- [Backpack API Documentation](https://docs.backpack.exchange)
- [NautilusTrader Documentation](https://nautilustrader.io)
- [ED25519 Specification](https://ed25519.cr.yp.to)