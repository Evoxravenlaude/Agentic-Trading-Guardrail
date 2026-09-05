import pytest

from guardrail.checks.dedup import check_dedup
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig(dedup_window_seconds=120)


@pytest.fixture
def st():
    return GuardrailState()


async def test_first_order_passes(cfg, st):
    order = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=0.01, price=60000.0, client_order_id="abc123",
    )
    result = await check_dedup(order, st, cfg)
    assert result.passed


async def test_retry_with_same_client_order_id_rejected(cfg, st):
    order1 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=0.01, price=60000.0, client_order_id="abc123",
    )
    order2 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=0.01, price=60000.0, client_order_id="abc123",
    )
    r1 = await check_dedup(order1, st, cfg)
    r2 = await check_dedup(order2, st, cfg)
    assert r1.passed
    assert not r2.passed


async def test_different_client_order_ids_both_pass(cfg, st):
    order1 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=0.01, price=60000.0, client_order_id="abc123",
    )
    order2 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=0.01, price=60000.0, client_order_id="xyz789",
    )
    r1 = await check_dedup(order1, st, cfg)
    r2 = await check_dedup(order2, st, cfg)
    assert r1.passed
    assert r2.passed


async def test_fallback_key_dedups_close_retries_without_client_order_id(cfg, st):
    # Use a fixed, boundary-safe timestamp instead of time.time() so this
    # test doesn't flake depending on where the wall clock lands relative
    # to the 2-second bucket used by derive_fallback_key.
    fixed_start = 1_700_000_000.0  # arbitrary, comfortably mid-bucket
    order1 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0,
        received_at=fixed_start,
    )
    order2 = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0,
        received_at=fixed_start + 0.5,  # fires half a second later, same 2s bucket
    )
    r1 = await check_dedup(order1, st, cfg)
    r2 = await check_dedup(order2, st, cfg)
    assert r1.passed
    assert not r2.passed
