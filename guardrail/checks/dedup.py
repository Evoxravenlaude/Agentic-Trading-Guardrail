"""Reject duplicate orders caused by agent retries after a dropped connection.

Same underlying shape as the AuthKeyDuplicatedError fix on the Telethon
bot stack: a reconnect/retry re-fires the same logical action, and we need
an idempotency key to recognize "this already happened" rather than
executing it twice.
"""

from __future__ import annotations

import hashlib

from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, CheckResult
from guardrail.state import GuardrailState

CHECK_NAME = "dedup"


def derive_fallback_key(order: OrderRequest, bucket_seconds: int = 2) -> str:
    """Best-effort idempotency key for agents that don't send client_order_id.

    Buckets by a coarse time window so a genuine retry (fired milliseconds
    to a couple seconds after the original, same content) collides with the
    original, while two independently-decided identical orders placed
    minutes apart do not.
    """
    bucket = int(order.received_at // bucket_seconds)
    raw = f"{order.agent_id}|{order.symbol}|{order.side}|{order.order_type}|{order.quantity}|{order.price}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def check_dedup(
    order: OrderRequest,
    state: GuardrailState,
    config: GuardrailConfig,
) -> CheckResult:
    key = order.client_order_id or derive_fallback_key(order)
    is_new = await state.check_and_record_order_id(key, config.dedup_window_seconds)
    if not is_new:
        return CheckResult.reject(
            CHECK_NAME,
            f"duplicate order (idempotency key {key} seen within {config.dedup_window_seconds}s window) "
            "— likely a retry after a dropped connection",
            idempotency_key=key,
        )
    return CheckResult.ok(CHECK_NAME, idempotency_key=key)
