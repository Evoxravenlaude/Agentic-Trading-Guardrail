import pytest

from guardrail.checks.kill_switch import check_kill_switch
from guardrail.models import OrderRequest, OrderSide, OrderType
from guardrail.state import GuardrailState


@pytest.fixture
def st():
    return GuardrailState()


def make_order():
    return OrderRequest(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)


async def test_passes_when_not_engaged(st):
    result = await check_kill_switch(make_order(), st)
    assert result.passed


async def test_blocks_when_engaged(st):
    await st.engage_kill_switch("suspected compromised agent")
    result = await check_kill_switch(make_order(), st)
    assert not result.passed
    assert "suspected compromised agent" in result.reason


async def test_disengage_restores_normal_flow(st):
    await st.engage_kill_switch("test")
    await st.disengage_kill_switch()
    result = await check_kill_switch(make_order(), st)
    assert result.passed
