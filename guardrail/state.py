"""In-memory state shared across guardrail checks.

Kept as a single class so it's trivial to swap for a Redis/Postgres-backed
implementation later (see README "Next steps") without touching check
logic — checks only ever call methods on a `GuardrailState` instance.

Not process-safe across multiple workers by design: for a hackathon-grade
deployment run a single guardrail process in front of Binance. Scaling out
is a "next step" noted in the README, not solved here.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class TradeOutcome:
    symbol: str
    pnl: float
    closed_at: float = field(default_factory=time.time)


class GuardrailState:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # Dedup: client_order_id -> timestamp last seen
        self._seen_order_ids: dict[str, float] = {}

        # Rate limiting: timestamps of accepted orders (global + per-symbol)
        self._order_timestamps: Deque[float] = deque()
        self._symbol_timestamps: dict[str, Deque[float]] = {}

        # Circuit breaker
        self._consecutive_losses: int = 0
        self._trade_outcomes: Deque[TradeOutcome] = deque()
        self._breaker_tripped: bool = False
        self._breaker_reason: str = ""
        self._breaker_tripped_at: Optional[float] = None

        # Account balance cache (falls back to config.fallback_account_balance
        # if the MCP client can't supply a live figure)
        self._account_balance: Optional[float] = None

        # Last known market price per symbol, used by the sanity check to
        # catch orders priced wildly off-market.
        self._last_price: dict[str, float] = {}

        # Judge/dashboard-facing observability: a rolling log of recent
        # decisions plus running counters. Capped so it can't grow unbounded
        # in a long-running demo.
        self._recent_decisions: Deque[dict] = deque(maxlen=200)
        self._total_orders: int = 0
        self._total_allowed: int = 0
        self._rejections_by_check: dict[str, int] = {}

        # Kill switch: distinct from the loss-driven circuit breaker so the
        # dashboard/API can tell "an operator hit the button" apart from
        # "the risk engine tripped on its own".
        self._kill_switch_engaged: bool = False
        self._kill_switch_reason: str = ""
        self._kill_switch_at: Optional[float] = None

    # ---------------- Dedup ----------------

    async def check_and_record_order_id(self, client_order_id: str, window_seconds: int) -> bool:
        """Returns True if this is a NEW order id (not a duplicate within the window)."""
        async with self._lock:
            now = time.time()
            self._prune_seen_ids(now, window_seconds)
            if client_order_id in self._seen_order_ids:
                return False
            self._seen_order_ids[client_order_id] = now
            return True

    def _prune_seen_ids(self, now: float, window_seconds: int) -> None:
        stale = [oid for oid, ts in self._seen_order_ids.items() if now - ts > window_seconds]
        for oid in stale:
            del self._seen_order_ids[oid]

    # ---------------- Rate limiter ----------------

    async def record_and_count_recent_orders(self, symbol: str, window_seconds: int = 60) -> tuple[int, int]:
        """Records this order attempt and returns (global_count, symbol_count) within the window."""
        async with self._lock:
            now = time.time()
            self._order_timestamps.append(now)
            self._prune_deque(self._order_timestamps, now, window_seconds)

            sym_dq = self._symbol_timestamps.setdefault(symbol, deque())
            sym_dq.append(now)
            self._prune_deque(sym_dq, now, window_seconds)

            return len(self._order_timestamps), len(sym_dq)

    @staticmethod
    def _prune_deque(dq: Deque[float], now: float, window_seconds: int) -> None:
        while dq and now - dq[0] > window_seconds:
            dq.popleft()

    # ---------------- Circuit breaker ----------------

    async def record_trade_outcome(self, symbol: str, pnl: float, window_seconds: int) -> None:
        async with self._lock:
            now = time.time()
            self._trade_outcomes.append(TradeOutcome(symbol=symbol, pnl=pnl, closed_at=now))
            while self._trade_outcomes and now - self._trade_outcomes[0].closed_at > window_seconds:
                self._trade_outcomes.popleft()

            if pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

    async def rolling_pnl(self, window_seconds: int) -> float:
        async with self._lock:
            now = time.time()
            return sum(t.pnl for t in self._trade_outcomes if now - t.closed_at <= window_seconds)

    async def consecutive_losses(self) -> int:
        async with self._lock:
            return self._consecutive_losses

    async def trip_breaker(self, reason: str) -> None:
        async with self._lock:
            self._breaker_tripped = True
            self._breaker_reason = reason
            self._breaker_tripped_at = time.time()

    async def reset_breaker(self) -> None:
        async with self._lock:
            self._breaker_tripped = False
            self._breaker_reason = ""
            self._breaker_tripped_at = None
            self._consecutive_losses = 0

    async def breaker_status(self) -> dict:
        async with self._lock:
            return {
                "tripped": self._breaker_tripped,
                "reason": self._breaker_reason,
                "tripped_at": self._breaker_tripped_at,
                "consecutive_losses": self._consecutive_losses,
            }

    @property
    def breaker_tripped(self) -> bool:
        # Fast, lock-free read for the hot path check; fine since it's a
        # simple bool flip and staleness of a few microseconds is harmless.
        return self._breaker_tripped

    # ---------------- Account / price cache ----------------

    async def set_account_balance(self, balance: float) -> None:
        async with self._lock:
            self._account_balance = balance

    async def get_account_balance(self, fallback: float) -> float:
        async with self._lock:
            return self._account_balance if self._account_balance is not None else fallback

    async def set_last_price(self, symbol: str, price: float) -> None:
        async with self._lock:
            self._last_price[symbol] = price

    async def get_last_price(self, symbol: str) -> Optional[float]:
        async with self._lock:
            return self._last_price.get(symbol)

    # ---------------- Observability (decision log + counters) ----------------

    async def record_decision(self, decision_dict: dict) -> None:
        async with self._lock:
            self._recent_decisions.append(decision_dict)
            self._total_orders += 1
            if decision_dict.get("allowed"):
                self._total_allowed += 1
            else:
                for c in decision_dict.get("checks", []):
                    if c.get("status") == "REJECT":
                        self._rejections_by_check[c["check"]] = self._rejections_by_check.get(c["check"], 0) + 1
                        break  # only the first rejection is the actual cause (pipeline short-circuits)

    async def get_stats(self) -> dict:
        async with self._lock:
            return {
                "total_orders": self._total_orders,
                "total_allowed": self._total_allowed,
                "total_blocked": self._total_orders - self._total_allowed,
                "rejections_by_check": dict(self._rejections_by_check),
            }

    async def get_recent_decisions(self, limit: int = 25) -> list[dict]:
        async with self._lock:
            return list(self._recent_decisions)[-limit:][::-1]  # newest first

    # ---------------- Kill switch ----------------

    async def engage_kill_switch(self, reason: str) -> None:
        async with self._lock:
            self._kill_switch_engaged = True
            self._kill_switch_reason = reason
            self._kill_switch_at = time.time()

    async def disengage_kill_switch(self) -> None:
        async with self._lock:
            self._kill_switch_engaged = False
            self._kill_switch_reason = ""
            self._kill_switch_at = None

    async def kill_switch_status(self) -> dict:
        async with self._lock:
            return {
                "engaged": self._kill_switch_engaged,
                "reason": self._kill_switch_reason,
                "engaged_at": self._kill_switch_at,
            }

    @property
    def kill_switch_engaged(self) -> bool:
        return self._kill_switch_engaged


# Single shared instance for the whole process.
state = GuardrailState()
