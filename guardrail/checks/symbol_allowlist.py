"""Reject trades on symbols not explicitly allowed.

Targets "hallucinated asset routing": an LLM-driven agent can misread a
symbol, invent one that sounds plausible, or get steered by a prompt
injection into trading something the operator never intended it to touch.
An empty allowlist (the default) means "allow everything" — set
GUARDRAIL_ALLOWED_SYMBOLS to opt into an allowlist.
"""

from __future__ import annotations

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest

CHECK_NAME = "symbol_allowlist"


async def check_symbol_allowlist(order: OrderRequest, config: GuardrailConfig) -> CheckResult:
    if not config.allowed_symbols:
        return CheckResult.ok(CHECK_NAME, enforced=False)

    if order.symbol not in config.allowed_symbols:
        return CheckResult.reject(
            CHECK_NAME,
            f"symbol {order.symbol} is not in the configured allowlist "
            f"({', '.join(sorted(config.allowed_symbols))}) — refusing to route an order "
            "to an asset the operator never approved",
            symbol=order.symbol,
        )

    return CheckResult.ok(CHECK_NAME, enforced=True, symbol=order.symbol)
