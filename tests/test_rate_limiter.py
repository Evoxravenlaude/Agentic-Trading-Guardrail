import pytest

from guardrail.checks.rate_limiter import check_rate_limit
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig(max_orders_per_minute=5, max_orders_per_symbol_per_minute=3)


@pytest.fixture
def st():
    return GuardrailState()


def make_order(symbol="BTCUSDT"):
    return OrderRequest(symbol=symbol, side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)


async def test_orders_within_limit_pass(cfg, st):
    # Spread across symbols so the tighter per-symbol limit (3) doesn't
    # interfere with exercising the global limit (5).
    symbols = ["BTCUSDT", "ETHUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
    for symbol in symbols:
        result = await check_rate_limit(make_order(symbol), st, cfg)
        assert result.passed


async def test_global_limit_blocks_excess_orders(cfg, st):
    symbols = ["BTCUSDT", "ETHUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    results = [await check_rate_limit(make_order(s), st, cfg) for s in symbols]
    assert all(r.passed for r in results[:5])
    assert not results[5].passed
    assert "global" in results[5].reason


async def test_per_symbol_limit_blocks_before_global_when_concentrated(cfg, st):
    # Symbol limit (3) is tighter than global (5) for a single symbol.
    results = [await check_rate_limit(make_order("ETHUSDT"), st, cfg) for _ in range(4)]
    assert all(r.passed for r in results[:3])
    assert not results[3].passed
    assert "ETHUSDT" in results[3].reason


async def test_different_symbols_have_independent_counters(cfg, st):
    r1 = await check_rate_limit(make_order("BTCUSDT"), st, cfg)
    r2 = await check_rate_limit(make_order("ETHUSDT"), st, cfg)
    assert r1.passed and r2.passed
