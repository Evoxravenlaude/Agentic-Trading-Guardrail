import pytest

from guardrail.checks import run_all_checks
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig(max_position_pct=0.10, fallback_account_balance=10_000.0)


@pytest.fixture
def st():
    return GuardrailState()


async def test_clean_order_passes_all_checks(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)
    results = await run_all_checks(order, st, cfg)
    assert len(results) == 5
    assert all(r.passed for r in results)


async def test_bad_sanity_short_circuits_before_rate_limiter(cfg, st):
    order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=-1, price=60000.0)
    results = await run_all_checks(order, st, cfg)
    # Only the sanity check should have run.
    assert len(results) == 1
    assert results[0].check_name == "sanity"
    assert not results[0].passed


async def test_oversized_order_never_counted_by_rate_limiter(cfg, st):
    """A position-size rejection shouldn't consume rate-limit budget —
    it never reached a 'real' attempt from the account's perspective."""
    big_order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=100, price=60000.0)
    await run_all_checks(big_order, st, cfg)

    good_order = OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)
    results = await run_all_checks(good_order, st, cfg)
    rate_result = next(r for r in results if r.check_name == "rate_limiter")
    assert rate_result.details["global_count"] == 1  # only the good order counted
