"""Halt all trading through the layer after a loss streak or drawdown breach.

Requires an explicit manual reset (POST /breaker/reset) — it never
auto-resumes, by design, per the build plan.
"""

from __future__ import annotations

from guardrail.config import GuardrailConfig
from guardrail.models import CheckResult, OrderRequest
from guardrail.state import GuardrailState

CHECK_NAME = "circuit_breaker"


async def check_circuit_breaker(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
) -> CheckResult:
    status = await state.breaker_status()
    if status["tripped"]:
        return CheckResult.reject(
            CHECK_NAME,
            f"circuit breaker is tripped ({status['reason']}); requires manual reset",
            tripped_at=status["tripped_at"],
            consecutive_losses=status["consecutive_losses"],
        )

    # Evaluate whether THIS check (not just past trade recording) should trip
    # the breaker, so the very order that would cross the threshold is itself
    # blocked rather than only the next one.
    losses = await state.consecutive_losses()
    if losses >= config.max_consecutive_losses:
        await state.trip_breaker(f"{losses} consecutive losses (limit {config.max_consecutive_losses})")
        return CheckResult.reject(
            CHECK_NAME,
            f"tripped: {losses} consecutive losses reached limit of {config.max_consecutive_losses}",
            consecutive_losses=losses,
        )

    pnl = await state.rolling_pnl(config.drawdown_window_seconds)
    balance = await state.get_account_balance(config.fallback_account_balance)
    if balance > 0:
        drawdown_pct = pnl / balance
        if drawdown_pct <= config.max_drawdown_pct:
            await state.trip_breaker(
                f"rolling drawdown {drawdown_pct:.2%} breached limit {config.max_drawdown_pct:.2%}"
            )
            return CheckResult.reject(
                CHECK_NAME,
                f"tripped: rolling P&L drawdown {drawdown_pct:.2%} breached limit {config.max_drawdown_pct:.2%}",
                drawdown_pct=drawdown_pct,
                rolling_pnl=pnl,
            )

    return CheckResult.ok(CHECK_NAME, consecutive_losses=losses, rolling_pnl=pnl)
