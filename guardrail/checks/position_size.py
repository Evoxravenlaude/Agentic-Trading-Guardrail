"""Reject any order whose notional value exceeds max_position_pct of account balance."""

from __future__ import annotations

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest
from guardrail.state import GuardrailState

CHECK_NAME = "position_size_cap"


async def check_position_size(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
    market_price: float | None,
) -> CheckResult:
    balance = await state.get_account_balance(config.fallback_account_balance)
    if balance <= 0:
        return CheckResult.reject(CHECK_NAME, "account balance is zero or unknown", balance=balance)

    # For MARKET orders we need a price to compute notional; fall back to the
    # last cached market price if the order itself doesn't carry one.
    price = order.price or market_price
    if price is None:
        return CheckResult.reject(
            CHECK_NAME,
            "no price available to compute notional value (order has no price and no cached market price)",
        )

    notional = order.quantity * price
    max_notional = balance * config.max_position_pct
    if notional > max_notional:
        return CheckResult.reject(
            CHECK_NAME,
            f"order notional {notional:.2f} exceeds cap of {max_notional:.2f} "
            f"({config.max_position_pct:.0%} of balance {balance:.2f})",
            notional=notional,
            max_notional=max_notional,
            balance=balance,
        )

    return CheckResult.ok(CHECK_NAME, notional=notional, max_notional=max_notional)
