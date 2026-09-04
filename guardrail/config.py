"""Central configuration for the guardrail layer.

Every threshold lives here so the checks stay pure/testable and the whole
risk posture can be tuned (or overridden per-deployment via env vars)
without touching check logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val not in (None, "") else default


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


@dataclass(frozen=True)
class GuardrailConfig:
    # --- Position size cap ---
    # Reject any single order whose notional value exceeds this fraction of
    # the account's known balance.
    max_position_pct: float = _float_env("GUARDRAIL_MAX_POSITION_PCT", 0.10)  # 10%

    # --- Circuit breaker ---
    max_consecutive_losses: int = _int_env("GUARDRAIL_MAX_CONSECUTIVE_LOSSES", 3)
    # Halt if realized P&L over the rolling window drops below this fraction
    # of account balance (negative number, e.g. -0.05 = -5%).
    max_drawdown_pct: float = _float_env("GUARDRAIL_MAX_DRAWDOWN_PCT", -0.05)
    drawdown_window_seconds: int = _int_env("GUARDRAIL_DRAWDOWN_WINDOW_SECONDS", 3600)
    # Circuit breaker requires an explicit manual reset call, never auto-resumes.

    # --- Dedup / idempotency ---
    dedup_window_seconds: int = _int_env("GUARDRAIL_DEDUP_WINDOW_SECONDS", 120)

    # --- Rate limiter ---
    max_orders_per_minute: int = _int_env("GUARDRAIL_MAX_ORDERS_PER_MINUTE", 10)
    max_orders_per_symbol_per_minute: int = _int_env("GUARDRAIL_MAX_ORDERS_PER_SYMBOL_PER_MINUTE", 5)

    # --- Sanity check ---
    min_price: float = _float_env("GUARDRAIL_MIN_PRICE", 0.0000001)
    max_price: float = _float_env("GUARDRAIL_MAX_PRICE", 10_000_000.0)
    min_quantity: float = _float_env("GUARDRAIL_MIN_QUANTITY", 0.0000001)
    max_quantity: float = _float_env("GUARDRAIL_MAX_QUANTITY", 1_000_000.0)
    # If an agent's order deviates from the last known market price by more
    # than this fraction, treat it as a likely float/precision bug rather
    # than a deliberate limit order far off market.
    max_price_deviation_pct: float = _float_env("GUARDRAIL_MAX_PRICE_DEVIATION_PCT", 0.20)

    # --- Account ---
    # Fallback account balance (quote currency) used when the MCP client
    # can't fetch a live balance (e.g. in tests/demo mode).
    fallback_account_balance: float = _float_env("GUARDRAIL_FALLBACK_BALANCE", 10_000.0)

    # --- Binance Agent OS MCP ---
    mcp_url: str = os.environ.get("BINANCE_MCP_URL", "https://agent.binance.com/mcp/agentic")
    dry_run: bool = os.environ.get("GUARDRAIL_DRY_RUN", "true").lower() in ("1", "true", "yes")


config = GuardrailConfig()
