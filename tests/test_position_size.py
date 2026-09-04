import pytest

from guardrail.checks.position_size import check_position_size
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig(max_position_pct=0.10, fallback_account_balance=10_000.0)


@pytest.fixture
def st():
    return GuardrailState()


async def test_order_within_cap_passes(cfg, st):
    # 10% of 10,000 = 1,000 max notional. 0.01 * 60000 = 600 — within cap.
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)
    result = await check_position_size(order, st, cfg, market_price=None)
    assert result.passed


async def test_order_exceeding_cap_rejected(cfg, st):
    # 0.5 * 60000 = 30,000 notional — way over the 1,000 cap.
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.5, price=60000.0)
    result = await check_position_size(order, st, cfg, market_price=None)
    assert not result.passed


async def test_market_order_uses_fallback_market_price(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.01, price=None)
    result = await check_position_size(order, st, cfg, market_price=60000.0)
    assert result.passed


async def test_market_order_with_no_price_anywhere_rejected(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.01, price=None)
    result = await check_position_size(order, st, cfg, market_price=None)
    assert not result.passed


async def test_respects_live_account_balance_over_fallback(cfg, st):
    await st.set_account_balance(100.0)  # much smaller live balance
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)
    result = await check_position_size(order, st, cfg, market_price=None)
    # 10% of 100 = 10 max notional; 600 notional order should now fail
    assert not result.passed
