"""Guardrail check pipeline.

Order: kill switch -> sanity -> symbol allowlist -> circuit breaker ->
position size -> dedup -> rate limiter. The kill switch runs before
anything else since it's an unconditional operator override. After that,
cheapest / most obviously-disqualifying checks run first so a malformed
or off-allowlist order fails fast without touching rate-limit or
circuit-breaker state.
"""

from __future__ import annotations

from typing import Optional

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest
from guardrail.state import GuardrailState

from .kill_switch import check_kill_switch
from .sanity import check_sanity
from .symbol_allowlist import check_symbol_allowlist
from .position_size import check_position_size
from .circuit_breaker import check_circuit_breaker
from .dedup import check_dedup
from .rate_limiter import check_rate_limit

__all__ = [
    "run_all_checks",
    "check_kill_switch",
    "check_sanity",
    "check_symbol_allowlist",
    "check_position_size",
    "check_circuit_breaker",
    "check_dedup",
    "check_rate_limit",
]


async def run_all_checks(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
    market_price: Optional[float] = None,
) -> list[CheckResult]:
    """Runs every check in sequence, short-circuiting on the first rejection.

    Short-circuiting means, e.g., a sanity-failing order never gets counted
    against the rate limiter or evaluated for dedup — it's not a "real"
    order attempt from the account's perspective, it's garbage input.
    """
    results: list[CheckResult] = []

    r = await check_kill_switch(order, state)
    results.append(r)
    if not r.passed:
        return results

    r = await check_sanity(order, state, config)
    results.append(r)
    if not r.passed:
        return results

    r = await check_symbol_allowlist(order, config)
    results.append(r)
    if not r.passed:
        return results

    r = await check_circuit_breaker(order, state, config)
    results.append(r)
    if not r.passed:
        return results

    r = await check_position_size(order, state, config, market_price)
    results.append(r)
    if not r.passed:
        return results

    r = await check_dedup(order, state, config)
    results.append(r)
    if not r.passed:
        return results

    r = await check_rate_limit(order, state, config)
    results.append(r)
    return results
