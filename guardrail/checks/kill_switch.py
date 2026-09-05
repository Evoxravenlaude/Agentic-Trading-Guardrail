"""Manual kill switch — an operator-triggered halt, distinct from the
circuit breaker's automatic loss-driven halt.

This is the check the industry commentary around Agent OS calls out as
missing from crypto agent trading by default: a broker-grade kill switch
that instantly stops all order flow regardless of cause, pending a human
decision. Runs first, before every other check, and before any state
that other checks touch gets mutated.
"""

from __future__ import annotations

from guardrail.models import CheckResult, OrderRequest
from guardrail.state import GuardrailState

CHECK_NAME = "kill_switch"


async def check_kill_switch(order: OrderRequest, state: GuardrailState) -> CheckResult:
    status = await state.kill_switch_status()
    if status["engaged"]:
        return CheckResult.reject(
            CHECK_NAME,
            f"kill switch is engaged ({status['reason']}); all order flow halted until an operator disengages it",
            engaged_at=status["engaged_at"],
        )
    return CheckResult.ok(CHECK_NAME)
