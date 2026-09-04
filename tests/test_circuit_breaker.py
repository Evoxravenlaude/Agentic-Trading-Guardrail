import pytest

from guardrail.checks.circuit_breaker import check_circuit_breaker
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def cfg():
    return GuardrailConfig(
        max_consecutive_losses=3,
        max_drawdown_pct=-0.05,
        drawdown_window_seconds=3600,
        fallback_account_balance=10_000.0,
    )


@pytest.fixture
def st():
    return GuardrailState()


def make_order():
    return OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)


async def test_passes_with_no_history(cfg, st):
    result = await check_circuit_breaker(make_order(), st, cfg)
    assert result.passed


async def test_trips_on_consecutive_losses(cfg, st):
    for _ in range(3):
        await st.record_trade_outcome("BTCUSDT", -10.0, cfg.drawdown_window_seconds)
    result = await check_circuit_breaker(make_order(), st, cfg)
    assert not result.passed
    assert "consecutive losses" in result.reason


async def test_win_resets_consecutive_loss_counter(cfg, st):
    await st.record_trade_outcome("BTCUSDT", -10.0, cfg.drawdown_window_seconds)
    await st.record_trade_outcome("BTCUSDT", -10.0, cfg.drawdown_window_seconds)
    await st.record_trade_outcome("BTCUSDT", 5.0, cfg.drawdown_window_seconds)  # win resets streak
    result = await check_circuit_breaker(make_order(), st, cfg)
    assert result.passed


async def test_trips_on_drawdown_breach(cfg, st):
    # -5% of 10,000 = -500. Three losses of -200 = -600, breaches drawdown
    # threshold before hitting the 3-consecutive-loss count on the 3rd... but
    # 3 losses also equals max_consecutive_losses, so use 2 with a big loss
    # then check via a fresh state focused purely on drawdown.
    st2 = GuardrailState()
    await st2.record_trade_outcome("BTCUSDT", -600.0, cfg.drawdown_window_seconds)
    result = await check_circuit_breaker(make_order(), st2, cfg)
    assert not result.passed
    assert "drawdown" in result.reason


async def test_once_tripped_stays_tripped_until_manual_reset(cfg, st):
    for _ in range(3):
        await st.record_trade_outcome("BTCUSDT", -10.0, cfg.drawdown_window_seconds)
    r1 = await check_circuit_breaker(make_order(), st, cfg)
    assert not r1.passed

    # A subsequent win doesn't matter — breaker requires manual reset.
    await st.record_trade_outcome("BTCUSDT", 100.0, cfg.drawdown_window_seconds)
    r2 = await check_circuit_breaker(make_order(), st, cfg)
    assert not r2.passed

    await st.reset_breaker()
    r3 = await check_circuit_breaker(make_order(), st, cfg)
    assert r3.passed
