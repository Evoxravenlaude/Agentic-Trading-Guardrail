"""Core data models shared by every guardrail check and the proxy layer."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class OrderRequest:
    """A trade order as submitted by an upstream agent, before it reaches Binance."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None  # required for LIMIT orders
    agent_id: str = "unknown-agent"
    # Caller-supplied idempotency key. If the agent doesn't provide one, callers
    # should derive one deterministically (see guardrail.checks.dedup) rather
    # than leaving it unset, or retries after a dropped connection won't dedup.
    client_order_id: Optional[str] = None
    # Server-assigned, unique per request received (distinct from client_order_id,
    # which is what dedup keys off of).
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    received_at: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)


class CheckStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


@dataclass
class CheckResult:
    check_name: str
    status: CheckStatus
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASS

    @classmethod
    def ok(cls, check_name: str, **details: Any) -> "CheckResult":
        return cls(check_name=check_name, status=CheckStatus.PASS, details=details)

    @classmethod
    def reject(cls, check_name: str, reason: str, **details: Any) -> "CheckResult":
        return cls(check_name=check_name, status=CheckStatus.REJECT, reason=reason, details=details)


@dataclass
class GuardrailDecision:
    order: OrderRequest
    results: list[CheckResult]
    forwarded: bool = False
    forward_response: Optional[dict[str, Any]] = None

    @property
    def allowed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def rejection(self) -> Optional[CheckResult]:
        for r in self.results:
            if not r.passed:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.order.request_id,
            "client_order_id": self.order.client_order_id,
            "agent_id": self.order.agent_id,
            "symbol": self.order.symbol,
            "side": self.order.side.value,
            "quantity": self.order.quantity,
            "price": self.order.price,
            "allowed": self.allowed,
            "checks": [
                {"check": r.check_name, "status": r.status.value, "reason": r.reason, "details": r.details}
                for r in self.results
            ],
            "forwarded": self.forwarded,
            "forward_response": self.forward_response,
        }
