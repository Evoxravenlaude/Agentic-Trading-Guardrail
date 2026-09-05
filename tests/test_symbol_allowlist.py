import pytest

from guardrail.checks.symbol_allowlist import check_symbol_allowlist
from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest, OrderSide, OrderType


def make_order(symbol="BTCUSDT"):
    return OrderRequest(symbol=symbol, side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.01, price=60000.0)


async def test_empty_allowlist_allows_everything():
    cfg = GuardrailConfig(allowed_symbols=frozenset())
    result = await check_symbol_allowlist(make_order("SOMERANDOMCOIN"), cfg)
    assert result.passed


async def test_allowed_symbol_passes():
    cfg = GuardrailConfig(allowed_symbols=frozenset({"BTCUSDT", "ETHUSDT"}))
    result = await check_symbol_allowlist(make_order("BTCUSDT"), cfg)
    assert result.passed


async def test_disallowed_symbol_rejected():
    cfg = GuardrailConfig(allowed_symbols=frozenset({"BTCUSDT", "ETHUSDT"}))
    result = await check_symbol_allowlist(make_order("DOGEUSDT"), cfg)
    assert not result.passed
    assert "DOGEUSDT" in result.reason
