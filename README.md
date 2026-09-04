# Agentic Trading Guardrail Layer

Binance Agent OS Mini Hackathon — Track A ("Build an AI agent with Agent OS")

A generic middleware layer that sits between any trading agent's decision
("buy X") and Binance's actual trade execution via the [Agent OS MCP
server](https://agent.binance.com/mcp/agentic). It enforces hard pre-trade
risk checks and catches the failure modes that make agentic trading
dangerous — regardless of what strategy or agent is driving it.

It's infrastructure, not a strategy: it works underneath any agent.

```
[Any trading agent] → wants to place an order
        ↓ HTTP POST /trade
[Guardrail layer]  ← intercepts every trade call before it reaches Binance
   • sanity check (reject nonsensical price/size, e.g. float errors)
   • circuit breaker (halt on loss streak / drawdown; manual reset only)
   • position-size cap (reject if order exceeds max % of account)
   • dedup / idempotency check (reject duplicate orders from retries/reconnects)
   • rate limiter (cap orders per minute, globally and per symbol)
        ↓ if all pass
[Binance Agent OS MCP server] (Agentic sub-account)
```

## Why this, and why these checks

Most production agentic trading bots don't fail because of bad strategy
logic — they fail on infrastructure-level bugs: floating-point sizing
errors, duplicate order firing after a reconnect, runaway decision loops,
and missing pre-trade risk checks. This targets those known failure
classes directly instead of trying to out-predict the market.

| Failure mode | What happens | Guardrail response |
|---|---|---|
| Duplicate order firing | Connection drops mid-request, agent retries, same order fires twice | Dedup / idempotency key rejects the repeat |
| Floating-point sizing errors | Precision bug produces a wrong size/price | Sanity check on bounds + deviation from last market price |
| Runaway loops | A buggy agent gets stuck spamming orders | Rate limiter caps orders per minute (global + per-symbol) |
| No circuit breaker | Naive agent wrappers keep trading through a losing streak | Breaker halts activity after N consecutive losses or a drawdown breach; requires manual reset |
| Oversized positions | Agent sizes a position too large for the account | Position-size cap rejects orders over X% of balance |

The dedup/reconnect problem here is structurally the same one already
solved for Telegram/Solana bot session handling
(`AuthKeyDuplicatedError`, fixed with SIGTERM handlers, shutdown flags,
and backoff logic) — same shape of problem, applied to duplicate trade
orders instead of duplicate bot instances.

## Design decisions

- **Generic wrapper, not a built-in feature.** Any agent that can make an
  HTTP call can sit behind this, which fits Binance's "Infrastructure and
  Developer Tools" framing better than a guardrail baked into one
  specific strategy agent. A minimal toy agent (`demo_agent/`) is
  included purely as a concrete demo consumer.
- **Proxy pattern, not an in-process wrapper.** The agent calls the
  guardrail's `/trade` endpoint instead of hitting Binance directly. This
  makes "trade blocked here" a distinct, visible step — important both
  for the demo and for real deployments where you want the guardrail to
  be un-bypassable.
- **Circuit breaker never auto-resumes.** Once tripped, it stays tripped
  until an explicit `POST /breaker/reset`. A losing streak is exactly the
  situation where you don't want a naive timer to start trading again.
- **Short-circuiting pipeline.** Checks run cheapest/most-disqualifying
  first (sanity → circuit breaker → position size → dedup → rate limit)
  and stop at the first rejection. A malformed order never consumes rate
  limit budget or gets recorded as a dedup key — it's not a "real" order
  attempt from the account's perspective.

## Project layout

```
guardrail/
  models.py          OrderRequest / CheckResult / GuardrailDecision
  config.py           all thresholds, overridable via env vars
  state.py            shared in-memory state (dedup cache, rate counters, breaker, balances)
  mcp_client.py        Binance Agent OS MCP client (Streamable HTTP), with DRY_RUN simulation mode
  proxy.py             FastAPI app — the actual interception point (/trade)
  checks/
    sanity.py
    position_size.py
    circuit_breaker.py
    dedup.py
    rate_limiter.py
demo_agent/
  agent.py             minimal toy agent — sends one order through the proxy
  demo_scenario.py      the demo script: fires each failure mode live and shows it get blocked
tests/                 unit tests per check + pipeline short-circuit behavior
```

## Running it

```bash
pip install -r requirements.txt

# Start the guardrail proxy (DRY_RUN=true by default — never touches a real
# Binance account; place_order calls are simulated).
uvicorn guardrail.proxy:app --host 0.0.0.0 --port 8000

# In another terminal: run the full demo scenario
python -m demo_agent.demo_scenario

# Or send a single order by hand
python -m demo_agent.agent --symbol BTCUSDT --side BUY --quantity 0.01 --price 60000 --type LIMIT

# Run the test suite
pytest
```

### Going live against a real Agentic sub-account

Set `GUARDRAIL_DRY_RUN=false` and ensure the `mcp` Python package is
installed (`pip install mcp`, already in `requirements.txt`). The client
in `guardrail/mcp_client.py` connects over Streamable HTTP to
`BINANCE_MCP_URL` (defaults to `https://agent.binance.com/mcp/agentic`)
and calls `get_price` / `get_account_balance` / `place_order` tools.
Market data needs no auth; account and trade tools need permissions
granted to the Agentic sub-account per Binance's Agent OS docs. Tool
names/schemas are based on Binance's published Skill Hub conventions —
if the live schema differs, only `mcp_client.py` needs to change, since
every check operates on the `OrderRequest`/`CheckResult` models, not on
MCP wire types.

## Configuration

All thresholds live in `guardrail/config.py` and can be overridden via
environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `GUARDRAIL_MAX_POSITION_PCT` | `0.10` | Max order notional as a fraction of account balance |
| `GUARDRAIL_MAX_CONSECUTIVE_LOSSES` | `3` | Losses in a row before the breaker trips |
| `GUARDRAIL_MAX_DRAWDOWN_PCT` | `-0.05` | Rolling P&L drawdown (fraction of balance) that trips the breaker |
| `GUARDRAIL_DRAWDOWN_WINDOW_SECONDS` | `3600` | Rolling window for the drawdown check |
| `GUARDRAIL_DEDUP_WINDOW_SECONDS` | `120` | How long an idempotency key is remembered |
| `GUARDRAIL_MAX_ORDERS_PER_MINUTE` | `10` | Global rate limit |
| `GUARDRAIL_MAX_ORDERS_PER_SYMBOL_PER_MINUTE` | `5` | Per-symbol rate limit |
| `GUARDRAIL_MAX_PRICE_DEVIATION_PCT` | `0.20` | Max deviation from last known market price before sanity check rejects |
| `GUARDRAIL_FALLBACK_BALANCE` | `10000` | Balance used when no live balance is available (dry-run/demo) |
| `BINANCE_MCP_URL` | `https://agent.binance.com/mcp/agentic` | MCP server endpoint |
| `GUARDRAIL_DRY_RUN` | `true` | Simulate fills instead of connecting to Binance |

## API

- `POST /trade` — submit an order; runs the full check pipeline and
  forwards to Binance only if every check passes. Returns a decision
  object with per-check pass/reject reasons.
- `POST /breaker/reset` — manually clear a tripped circuit breaker.
- `GET /breaker/status` — current breaker state.
- `POST /trade-outcome` — report a closed trade's realized P&L (feeds the
  circuit breaker). In a live deployment this would be derived from fill
  events read back from Binance rather than self-reported by the agent.
- `POST /market-price` — push a reference price for a symbol (used by the
  sanity deviation check and as a MARKET-order fallback price).
- `POST /account-balance` — seed the account balance in dry-run/demo mode.
- `GET /health` — liveness + current config mode.

## Next steps (out of scope for this build)

- **Real MCP schema validation.** Tool names/argument shapes for
  `get_price` / `get_account_balance` / `place_order` are based on
  published Agent OS conventions and should be confirmed against a live
  session before trusting this against a funded account.
- **Persistent state.** `guardrail/state.py` is in-memory and single
  process by design; swap it for Redis/Postgres to survive restarts and
  scale beyond one process.
- **Fill-derived P&L instead of self-reported.** `/trade-outcome` is a
  stand-in for reading actual fills back from Binance.
- **MCP-native interception**, not just a REST proxy, for agents that
  want to keep speaking MCP end-to-end.
