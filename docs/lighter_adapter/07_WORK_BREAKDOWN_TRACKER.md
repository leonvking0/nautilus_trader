
# 07_WORK_BREAKDOWN_TRACKER.md

## Work Breakdown & Tracker

### Milestone 1: Data Foundation (Week 1)

**Definition of Done**: Can load all instruments and subscribe to market data

- [x] **PR0: Scaffolding**
  - [x] Create package structure
  - [x] Implement config classes
  - [x] Define enums and constants
  - [x] Add credential utilities
  - [x] Unit tests for config

- [x] **PR1: Instruments**
  - [x] HTTP client with auth
  - [x] orderBooks endpoint
  - [x] Parse to CryptoPerpetual
  - [x] InstrumentProvider implementation
  - [x] Integration test: load instruments
  - [x] Python unit tests executed (aligned venv + pytest-asyncio)

### Milestone 2: Market Data (Week 2)

**Definition of Done**: Live order book and trade feeds working (public)

- [x] **PR2: WebSocket + Data Client**
  - [x] WebSocket client with reconnect
  - [x] Order book subscription
  - [x] Trade subscription
  - [x] Market stats subscription
  - [x] Offset sequencing
  - [x] Snapshot fetch + delta sync
  - [x] Data client implementation
  - [x] Integration test: order book sync (fixture-backed)

### Milestone 2.5: Validation Spike (Week 2)

**Definition of Done**: Signing/auth/WS schema questions answered with real captures

- [x] Capture successful `sendTx` request/response (hashing + signing recipe)
- [x] Confirm whether auth token is required for private REST + WS
- [x] Record WS payloads to lock channel names and snapshot/delta semantics
- [x] Store redacted fixtures under `tests/test_data/lighter/{http,ws}/`
- [x] Write doc update summarizing validated behaviors

### Milestone 3: Execution (Week 3)

**Definition of Done**: Can place and cancel orders (gated on Validation Spike)

- [x] **PR3: Execution Client**
  - [x] Nonce manager (HTTP `/nextNonce` wrapper + Python bindings)
  - [x] Order submission (sendTx) via signer-generated tx_info
  - [x] Order cancellation (sendTx cancel) via signer-generated tx_info
  - [x] User order stream (WS)
  - [x] Status/fill mapping via REST reconciliation
  - [x] Execution client implementation (retries, token refresh, reconciliation)
  - [x] Integration test: order lifecycle
  - [x] Follow mainnet validation runbook in `PR_NOTES_AUTH_VALIDATION.md` for BTC/ETH place-and-cancel sanity checks

### Milestone 4: Account (Week 4)

**Definition of Done**: Position and balance tracking complete

- [x] **PR4: Account Management**
  - [x] Account/Position models in Rust (`LighterPosition`, `LighterAccount`, `AccountDetailsResponse`)
  - [x] Account endpoint methods (`account_details`, `account_by_index` HTTP methods)
  - [x] Position reports (`generate_position_status_reports` in execution client)
  - [x] Fill reports (via `_build_reports` in execution client - completed in PR3)
  - [x] Unit tests for position report generation (5 new tests)
  - [x] Position updates from fills (Lighter has no dedicated WS position channel)
  - [x] Position reconciliation on reconnect
  - [x] Unit tests for position updates and reconciliation (4 new tests)
  - [ ] Balance fetching (AccountState updates) - deferred to PR5

**PR4 Implementation Notes**:
- Branch: `pr3` (merged with previous work)
- Commits:
  - `587242363` lighter: add account/position models and position status reports
  - (current) lighter: add position updates from fills and reconnect reconciliation
- Files modified:
  - `crates/adapters/lighter/src/http/models.rs` - Added typed position/account structs
  - `crates/adapters/lighter/src/http/client.rs` - Added `account_details` endpoint
  - `nautilus_trader/adapters/lighter/execution.py`:
    - `generate_position_status_reports()` method
    - `_position_to_report()` helper method
    - `_reconcile_positions()` method for REST-based reconciliation
    - `_on_user_stream_reconnect()` callback for full reconciliation
    - `_handle_user_stream_message()` updated to trigger position reconciliation on fills
  - `tests/unit_tests/adapters/lighter/test_execution.py` - 13 tests total (9 position + 4 reconciliation)
- Tests: 49 Python tests pass, 26 Rust tests pass
- Key Design Decision: Lighter does not have a dedicated WebSocket channel for position updates.
  Position changes are derived from order fills (REST reconciliation triggered after fills detected in WS stream).

### Milestone 5: Hardening (Week 5-6)

**Definition of Done**: Production-ready adapter

- [ ] **PR5: Hardening**
  - [ ] Reconnect with backoff
  - [ ] Rate limit handling
  - [ ] Auth token refresh
  - [ ] Comprehensive logging
  - [ ] Metrics integration
  - [ ] 24-hour stability test
  - [ ] Documentation

---

### Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Signing algorithm unknown | High | High | Validation spike to capture real `sendTx` requests |
| Auth token requirement unclear | High | Medium | Implement token path; test both token/no-token during validation |
| WS schema/channel mismatch | Medium | Medium | Record payloads and adjust parsers before releasing |
| Fee schedule inconsistency | Medium | Medium | Avoid hardcoding; prefer exchange-reported fees once confirmed |
| Standard rate limits too restrictive | High | Medium | Recommend Premium accounts; implement strict throttling |
| Testnet != Mainnet behavior | Medium | Low | Test on mainnet with minimal size post-validation |

---

### Open Questions to Resolve

| # | Question | Priority | Validation Method |
|---|----------|----------|-------------------|
| 1 | Signing algorithm + payload hashing for `sendTx` | High | Capture successful tx and reproduce signature |
| 2 | Are auth tokens required for private REST/WS? | High | Attempt with/without token on testnet |
| 3 | ~~Exact WS channel names and payload schemas~~ | ~~High~~ | **RESOLVED**: Subscribe uses slashes (`order_book/{idx}`), responses use colons (`order_book:1`). See `03_LIGHTER_API_SPEC.md`. |
| 4 | Do WS channels emit snapshots on subscribe? | High | Observe initial messages and compare to REST snapshot |
| 5 | Fee schedule (Standard vs Premium) | Medium | Confirm via support or live fills; prefer exchange-reported fees |
| 6 | Nonce persistence/recovery rules | Medium | Force mismatch and use `nextNonce` (or equivalent) to reconcile |
| 7 | Batch transaction limits and error behavior | Medium | Test `sendTxBatch` with varying sizes |
| 8 | Funding payment timing/precision | Medium | Observe funding events and compare to docs |
| 9 | WS ping/pong expectations | Low | Monitor keepalive needs; add client-side ping if required |
| 10 | Max orders per account / throttling | Low | Probe limits on testnet and document behavior |

---

### How to Test (Full Suite)

**Rust Tests**:

```bash
cargo test -p nautilus-lighter
```

**Python Unit Tests**:

```bash
uv run pytest tests/unit_tests/adapters/lighter/ -v
```

**Python Integration Tests**:

```bash
uv run pytest tests/integration_tests/adapters/lighter/ -v
```

**All Python Tests**:

```bash
uv run pytest tests/unit_tests/adapters/lighter/ tests/integration_tests/adapters/lighter/ -v
```

**Individual Test Files**:

```bash
# Config tests (PR0)
uv run pytest tests/unit_tests/adapters/lighter/test_config.py -v

# Provider tests (PR1)
uv run pytest tests/unit_tests/adapters/lighter/test_providers.py -v

# Data client tests (PR2)
uv run pytest tests/integration_tests/adapters/lighter/test_data_client.py -v

# Order book sync tests (PR2)
uv run pytest tests/integration_tests/adapters/lighter/test_order_book_sync.py -v

# Message parsing tests (PR2)
uv run pytest tests/integration_tests/adapters/lighter/test_parsing.py -v

# Execution client tests (PR3/PR4)
uv run pytest tests/unit_tests/adapters/lighter/test_execution.py -v

# Execution lifecycle tests (PR3)
uv run pytest tests/integration_tests/adapters/lighter/test_execution_lifecycle.py -v
```

---

### GitHub Issue Templates

**Bug Report**:

```markdown
## Bug Report: Lighter Adapter

**Component**: [data/execution/account/websocket]
**Severity**: [critical/high/medium/low]

### Description
[Clear description of the bug]

### Steps to Reproduce
1.
2.
3.

### Expected Behavior
[What should happen]

### Actual Behavior
[What actually happens]

### Logs
```

[Relevant log output]

```

### Environment
- Nautilus version:
- Python version:
- Lighter account type: [Standard/Premium]
- Network: [Testnet/Mainnet]
```

**Feature Request**:

```markdown
## Feature Request: Lighter Adapter

**Feature**: [Brief title]

### User Story
As a [persona], I want [feature] so that [benefit].

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Technical Notes
[Implementation considerations]

### Priority Justification
[Why this matters]
```

**Investigation Task**:

```markdown
## Investigation: [Topic]

**Goal**: [What we're trying to learn]

### Questions to Answer
1.
2.

### Approach
[How to investigate]

### Success Criteria
[How we know we're done]

### Findings
[To be filled after investigation]
```

---
