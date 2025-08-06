# Backpack Exchange Integration - Phase 1: Foundation & Setup

## Overview

This document outlines the integration process of Backpack Exchange into NautilusTrader. Phase 1 focuses on establishing the foundational architecture including ED25519 authentication, API mappings, and initial test infrastructure.

## Status: NOT STARTED

**Start Date**: TBD
**Target Completion**: 1 week
**Final Progress**: 0%

---

## Phase 1 Objectives

* [ ] Setup test infrastructure (TDD-first approach)
* [ ] Create base adapter implementation structure
* [ ] Implement ED25519 authentication logic
* [ ] Define all API endpoints (REST public and private)
* [ ] Implement helper methods (signature, payload, sorting)
* [ ] Validate with unit and integration tests

---

## 1. Test Infrastructure Setup

### 1.1 Static Test Data

* [ ] `tests/integration_tests/adapters/backpack/fixtures/responses/`
  * [ ] `markets.json` - Sample market data responses
  * [ ] `ticker.json` - Sample ticker responses
  * [ ] `orderbook.json` - Sample order book responses
  * [ ] `trades.json` - Sample trade responses
  * [ ] `balance.json` - Sample balance responses
  * [ ] `order.json` - Sample order responses

### 1.2 Unit Test Files

* [ ] `tests/unit_tests/adapters/backpack/test_backpack_common.py`
  * ED25519 signature validation
  * Parameter sorting tests
  * Timestamp window tests

* [ ] `tests/unit_tests/adapters/backpack/test_backpack_parsing.py`
  * Market/ticker/trade/order parsing
  * Balance calculation
  * Symbol conversion (BTC_USDT ↔ BTC-USDT)

* [ ] `tests/integration_tests/adapters/backpack/test_backpack_data.py`
  * Data client integration tests

---

## 2. Base Adapter Structure

### 2.1 Python Implementation

* [ ] `nautilus_trader/adapters/backpack/__init__.py`
* [ ] `nautilus_trader/adapters/backpack/common/__init__.py`
* [ ] `nautilus_trader/adapters/backpack/common/constants.py`
  * Exchange metadata
  * API endpoints
  * Rate limits
  * Error codes

* [ ] `nautilus_trader/adapters/backpack/common/enums.py`
  * Order types
  * Order sides
  * Time in force
  * Order status mappings

### 2.2 Rust Core Components

* [ ] `crates/adapters/backpack/src/lib.rs`
* [ ] `crates/adapters/backpack/src/types.rs`
  * Backpack-specific types
  * Response structures

* [ ] `crates/adapters/backpack/Cargo.toml`
  * Dependencies setup
  * Ed25519 crypto dependency

---

## 3. Authentication Implementation

### 3.1 Core Sign Logic

* [ ] `nautilus_trader/adapters/backpack/common/auth.py`
  * [ ] `sign_request()` method
    * Timestamp generation (milliseconds)
    * 5-second time window
    * Parameter sorting (alphabetical)
    * Base64 encoding
    * ED25519 signature generation

### 3.2 Helper Methods

* [ ] `build_signature_payload()`
  * Instruction format: `instruction=<method>&<sorted_params>&timestamp=<ms>&window=5000`
* [ ] `sort_parameters()`
  * Alphabetical parameter sorting
* [ ] `encode_signature()`
  * Base64 encoding for headers

### 3.3 Integration with Existing Crypto

* [ ] Utilize `nautilus_core::cryptography::Ed25519` 
* [ ] Create Python bindings for Ed25519 operations

---

## 4. HTTP Client Implementation

* [ ] `nautilus_trader/adapters/backpack/http/client.py`
  * [ ] Base HTTP client with authentication
  * [ ] Request/response handling
  * [ ] Rate limiting (6000/min spot, 2400/min futures)
  * [ ] Error handling and retries

---

## 5. Core Public Methods

* [ ] `fetch_markets()` - GET /api/v1/markets
* [ ] `fetch_ticker()` - GET /api/v1/ticker
* [ ] `fetch_tickers()` - GET /api/v1/tickers
* [ ] `fetch_order_book()` - GET /api/v1/depth
* [ ] `fetch_trades()` - GET /api/v1/trades
* [ ] `fetch_klines()` - GET /api/v1/klines

---

## 6. Core Private Methods

* [ ] `fetch_balance()` - GET /api/v1/capital
* [ ] `create_order()` - POST /api/v1/order
* [ ] `cancel_order()` - DELETE /api/v1/order
* [ ] `fetch_order()` - GET /api/v1/order
* [ ] `fetch_open_orders()` - GET /api/v1/orders
* [ ] `fetch_order_history()` - GET /api/v1/orderHistory

---

## 7. Parsing Methods

* [ ] `nautilus_trader/adapters/backpack/parsing.py`
  * [ ] `parse_market()` - Convert to Nautilus Instrument
  * [ ] `parse_ticker()` - Convert to QuoteTick
  * [ ] `parse_trade()` - Convert to TradeTick
  * [ ] `parse_order_book()` - Convert to OrderBookDeltas
  * [ ] `parse_balance()` - Convert to AccountBalance
  * [ ] `parse_order()` - Convert to Order

---

## 8. Error Handling

* [ ] `nautilus_trader/adapters/backpack/common/exceptions.py`
  * [ ] Define Backpack-specific exceptions
  * [ ] Map API error codes to exceptions
  * [ ] Implement retry logic for recoverable errors

---

## 9. Build & Testing

### 9.1 Build Commands

```bash
# Build Rust components in debug mode
make build-debug

# Run Python tests
make pytest-unit-backpack

# Run integration tests
make pytest-integration-backpack

# Lint and format
make ruff
make format
```

### 9.2 Environment Setup

```bash
# Test environment variables
export BACKPACK_API_KEY="..."
export BACKPACK_API_SECRET="..."
export BACKPACK_TESTNET=true
```

---

## 10. Testing Commands

```bash
# Unit tests
uv run pytest tests/unit_tests/adapters/backpack/ -v

# Integration tests (requires API keys)
uv run pytest tests/integration_tests/adapters/backpack/ -v

# Specific test
uv run pytest tests/unit_tests/adapters/backpack/test_backpack_common.py::TestBackpackAuth::test_ed25519_signature -v
```

---

## 11. Success Criteria Checklist

### Unit Tests
* [ ] ED25519 signature generation matches expected values
* [ ] Parameter sorting works correctly
* [ ] All parsing methods handle edge cases
* [ ] Symbol conversion bidirectional (BTC_USDT ↔ BTC-USDT)
* [ ] 90% code coverage achieved

### Integration Tests
* [ ] Can fetch public market data without auth
* [ ] Can authenticate with ED25519 keys
* [ ] Can fetch private account data
* [ ] Rate limiting works correctly
* [ ] Error handling recovers gracefully

---

## 12. Known Issues / Considerations

### Authentication Challenges
* ED25519 requires specific parameter ordering
* Base64 encoding must match exactly
* Timestamp precision (milliseconds) critical
* 5-second window strict enforcement

### API Specifics
* Symbol format: `BTC_USDT` (underscore separator)
* Different rate limits for spot vs futures
* Batch operations have special signing requirements
* No sandbox environment (use testnet)

### Integration Points
* Must integrate with existing NautilusTrader MessageBus
* Reuse existing ED25519 crypto from nautilus_core
* Follow adapter patterns from Binance/Bybit implementations
* Ensure compatibility with Cache and DataEngine

---

## 13. Dependencies

### External
* [ ] Backpack API Documentation
* [ ] ED25519 cryptography library (already in nautilus_core)
* [ ] HTTP client (aiohttp)
* [ ] Rate limiting (existing nautilus implementation)

### Internal References
* [ ] `nautilus_core::cryptography` - ED25519 implementation
* [ ] `nautilus_trader/adapters/binance/` - Reference implementation
* [ ] `nautilus_trader/adapters/bybit/` - Reference implementation
* [ ] Test fixtures from existing adapters

---

## 14. Progress Log

### Day 1 - [TBD]
* [ ] Setup project structure
* [ ] Create test fixtures
* [ ] Implement authentication logic
* [ ] Initial unit tests for auth

### Day 2 - [TBD]
* [ ] HTTP client implementation
* [ ] Public endpoints implementation
* [ ] Parsing methods for public data

### Day 3 - [TBD]
* [ ] Private endpoints implementation
* [ ] Account data parsing
* [ ] Order management methods

### Day 4 - [TBD]
* [ ] Error handling implementation
* [ ] Rate limiting logic
* [ ] Integration test suite

### Day 5 - [TBD]
* [ ] Performance testing
* [ ] Documentation
* [ ] Code review and cleanup
* [ ] Achieve coverage targets

---

## 15. Next Steps

* [ ] **Phase 2** – WebSocket Implementation (Week 2)
  * Real-time market data
  * Order updates stream
  * Connection pooling for 200 sub limit
  
* [ ] **Phase 3** – Advanced Features (Week 3)
  * Futures support
  * Margin trading
  * Batch operations
  
* [ ] **Phase 4** – Production Readiness (Week 4)
  * Performance optimization
  * Comprehensive testing
  * Documentation completion

---

## Technical Decisions

### Architecture
* **Hybrid Python/Rust**: Performance-critical parsing in Rust
* **Async/await**: All I/O operations async
* **Caching**: Leverage NautilusTrader Cache for state

### Testing Strategy
* **TDD First**: Write tests before implementation
* **Mock Responses**: Use fixtures for deterministic testing
* **Coverage Goals**: 90% unit, 80% integration

### Code Quality
* **Type Hints**: Full type annotations
* **Docstrings**: Comprehensive documentation
* **Linting**: Ruff for Python, Clippy for Rust

---

## Notes

* Follow NautilusTrader adapter conventions strictly
* Coordinate with team on API key access for testing
* Document any deviations from standard patterns
* Keep PRD updated with implementation discoveries
* Use existing Binance/Bybit adapters as reference

---

*Last Updated*: 2025-08-06
*Owner*: Development Team
*PRD Reference*: `docs/integrations/backpack_prd.md`