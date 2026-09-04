"""Cap orders per minute, globally and per-symbol, to limit the blast radius
of a buggy agent stuck in a decision loop.

Sliding-window counter (not fixed-window / token-bucket) so a burst can't
sneak two windows' worth of orders through right at a boundary.
"""

from __future__ import annotations

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest
from guardrail.state import GuardrailState

CHECK_NAME = "rate_limiter"


async def check_rate_limit(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
) -> CheckResult:
    global_count, symbol_count = await state.record_and_count_recent_orders(order.symbol, window_seconds=60)

    if global_count > config.max_orders_per_minute:
        return CheckResult.reject(
            CHECK_NAME,
            f"global rate limit exceeded: {global_count} orders in the last 60s "
            f"(limit {config.max_orders_per_minute})",
            global_count=global_count,
        )

    if symbol_count > config.max_orders_per_symbol_per_minute:
        return CheckResult.reject(
            CHECK_NAME,
            f"per-symbol rate limit exceeded for {order.symbol}: {symbol_count} orders in the last 60s "
            f"(limit {config.max_orders_per_symbol_per_minute})",
            symbol=order.symbol,
            symbol_count=symbol_count,
        )

    return CheckResult.ok(CHECK_NAME, global_count=global_count, symbol_count=symbol_count)
