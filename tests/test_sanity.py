import pytest

from guardrail.checks.sanity import check_sanity
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig()


@pytest.fixture
def st():
    return GuardrailState()


async def test_valid_order_passes(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)
    result = await check_sanity(order, st, cfg)
    assert result.passed


async def test_negative_quantity_rejected(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=-0.01, price=60000.0)
    result = await check_sanity(order, st, cfg)
    assert not result.passed


async def test_nan_quantity_rejected(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=float("nan"), price=60000.0)
    result = await check_sanity(order, st, cfg)
    assert not result.passed


async def test_limit_order_missing_price_rejected(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=None)
    result = await check_sanity(order, st, cfg)
    assert not result.passed


async def test_quantity_over_max_bound_rejected(cfg, st):
    order = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=cfg.max_quantity * 10, price=60000.0,
    )
    result = await check_sanity(order, st, cfg)
    assert not result.passed


async def test_price_deviation_from_market_rejected(cfg, st):
    await st.set_last_price("BTCUSDT", 60000.0)
    # 10x market price — classic decimal-shift bug
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=600000.0)
    result = await check_sanity(order, st, cfg)
    assert not result.passed
    assert "deviates" in result.reason


async def test_price_within_deviation_tolerance_passes(cfg, st):
    await st.set_last_price("BTCUSDT", 60000.0)
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=61000.0)
    result = await check_sanity(order, st, cfg)
    assert result.passed
