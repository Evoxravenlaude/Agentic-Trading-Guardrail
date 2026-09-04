"""Catch nonsensical price/size values before they reach the exchange.

Targets the "floating-point sizing errors" failure mode: an agent's
internal math produces a size or price that's off by orders of magnitude
(e.g. a precision bug multiplying quantity by 1e6), which passes a naive
"is it a positive number" check but is obviously wrong in context.
"""

from __future__ import annotations

import math

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest, OrderType
from guardrail.state import GuardrailState

CHECK_NAME = "sanity"


async def check_sanity(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
) -> CheckResult:
    # Basic finiteness / positivity
    if order.quantity is None or not math.isfinite(order.quantity) or order.quantity <= 0:
        return CheckResult.reject(CHECK_NAME, f"quantity {order.quantity!r} is not a finite positive number")

    if order.order_type is OrderType.LIMIT:
        if order.price is None or not math.isfinite(order.price) or order.price <= 0:
            return CheckResult.reject(CHECK_NAME, f"LIMIT order price {order.price!r} is not a finite positive number")

    # Bounds check — catches magnitude bugs (e.g. quantity in wrong units)
    if not (config.min_quantity <= order.quantity <= config.max_quantity):
        return CheckResult.reject(
            CHECK_NAME,
            f"quantity {order.quantity} outside sane bounds [{config.min_quantity}, {config.max_quantity}]",
        )

    if order.price is not None and not (config.min_price <= order.price <= config.max_price):
        return CheckResult.reject(
            CHECK_NAME,
            f"price {order.price} outside sane bounds [{config.min_price}, {config.max_price}]",
        )

    # Deviation from last known market price — catches a wrong-units or
    # decimal-shift bug that a bare range check would miss (e.g. an order
    # priced at 10x or 0.1x the going rate).
    market_price = await state.get_last_price(order.symbol)
    if market_price and order.price:
        deviation = abs(order.price - market_price) / market_price
        if deviation > config.max_price_deviation_pct:
            return CheckResult.reject(
                CHECK_NAME,
                f"price {order.price} deviates {deviation:.1%} from last known market price {market_price} "
                f"(limit {config.max_price_deviation_pct:.0%}) — likely a precision/unit bug, not a deliberate order",
                order_price=order.price,
                market_price=market_price,
                deviation=deviation,
            )

    return CheckResult.ok(CHECK_NAME, quantity=order.quantity, price=order.price)
