"""HTTP proxy: agents POST orders here instead of hitting Binance directly.

    [Agent] --POST /trade--> [Guardrail proxy] --(if passed)--> [Binance MCP]
                                    |
                                    +--(if rejected)--> logged, blocked, 200 with allowed=false

Kept as a REST proxy (not a raw MCP-protocol passthrough) so any agent —
regardless of what client library it uses — can sit in front of it with a
single HTTP call. A thin MCP-native wrapper can be layered on later; see
README "Next steps".
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from guardrail.checks import run_all_checks
from guardrail.config import config
from guardrail.dashboard_html import DASHBOARD_HTML
from guardrail.mcp_client import BinanceMCPClient
from guardrail.models import GuardrailDecision, OrderRequest, OrderSide, OrderType
from guardrail.state import state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("guardrail.proxy")

mcp_client = BinanceMCPClient(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_client.connect()
    yield
    await mcp_client.close()


app = FastAPI(title="Agentic Trading Guardrail Layer", lifespan=lifespan)


# ---------------- Request/response schemas ----------------


class TradeRequestBody(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = Field(default=OrderType.MARKET, alias="type")
    quantity: float
    price: Optional[float] = None
    agent_id: str = "unknown-agent"
    client_order_id: Optional[str] = None

    class Config:
        populate_by_name = True


class TradeOutcomeBody(BaseModel):
    symbol: str
    pnl: float


class MarketPriceBody(BaseModel):
    symbol: str
    price: float


class KillSwitchBody(BaseModel):
    reason: str = "manual operator halt"


# ---------------- Routes ----------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "dry_run": config.dry_run, "mcp_url": config.mcp_url}


@app.post("/trade")
async def trade(body: TradeRequestBody) -> dict:
    """The core interception point. Every guardrail check runs here before
    anything is forwarded to Binance."""
    order = OrderRequest(
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        agent_id=body.agent_id,
        client_order_id=body.client_order_id,
    )

    market_price = await state.get_last_price(order.symbol)
    results = await run_all_checks(order, state, config, market_price=market_price)
    decision = GuardrailDecision(order=order, results=results)

    if decision.allowed:
        try:
            response = await mcp_client.place_order(order)
            decision.forwarded = True
            decision.forward_response = response
            logger.info("ALLOWED order %s (%s %s %s) -> forwarded", order.request_id, order.side, order.quantity, order.symbol)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Forwarding order %s to Binance failed", order.request_id)
            raise HTTPException(status_code=502, detail=f"Order passed guardrail but forwarding failed: {exc}") from exc
    else:
        rej = decision.rejection
        logger.warning("BLOCKED order %s: %s failed (%s)", order.request_id, rej.check_name, rej.reason)

    result_dict = decision.to_dict()
    await state.record_decision(result_dict)
    return result_dict


@app.post("/breaker/reset")
async def reset_breaker() -> dict:
    await state.reset_breaker()
    logger.info("Circuit breaker manually reset")
    return await state.breaker_status()


@app.get("/breaker/status")
async def breaker_status() -> dict:
    return await state.breaker_status()


@app.post("/trade-outcome")
async def report_trade_outcome(body: TradeOutcomeBody) -> dict:
    """Lets an agent (or the demo script) report a closed trade's realized
    P&L, which feeds the circuit breaker's loss-streak/drawdown tracking.
    In a live deployment this would instead be derived from fill events
    read back from Binance rather than self-reported by the agent."""
    await state.record_trade_outcome(body.symbol, body.pnl, config.drawdown_window_seconds)
    losses = await state.consecutive_losses()
    return {"recorded": True, "consecutive_losses": losses}


@app.post("/market-price")
async def set_market_price(body: MarketPriceBody) -> dict:
    """Lets the demo agent (or a real price feed) push a reference price
    used by the sanity check's deviation guard and as a MARKET-order
    fallback price for the position-size check."""
    await state.set_last_price(body.symbol, body.price)
    return {"symbol": body.symbol, "price": body.price}


@app.post("/account-balance")
async def set_account_balance(balance: float) -> dict:
    """Manually seed the account balance in dry-run/demo mode, where there's
    no live MCP session to fetch it from."""
    await state.set_account_balance(balance)
    return {"balance": balance}


# ---------------- Kill switch ----------------
# Distinct from the circuit breaker: this is an operator-triggered halt
# (the "kill switch" the industry commentary around Agent OS flags as
# missing from crypto agent trading by default), not an automatic
# loss-driven one. Mirrors Binance's own sub-account "Emergency stop".


@app.post("/kill-switch/engage")
async def engage_kill_switch(body: KillSwitchBody) -> dict:
    await state.engage_kill_switch(body.reason)
    logger.warning("KILL SWITCH ENGAGED: %s", body.reason)
    return await state.kill_switch_status()


@app.post("/kill-switch/disengage")
async def disengage_kill_switch() -> dict:
    await state.disengage_kill_switch()
    logger.warning("Kill switch disengaged")
    return await state.kill_switch_status()


@app.get("/kill-switch/status")
async def kill_switch_status() -> dict:
    return await state.kill_switch_status()


# ---------------- Observability ----------------


@app.get("/stats")
async def stats() -> dict:
    return await state.get_stats()


@app.get("/decisions")
async def recent_decisions(limit: int = 25) -> list[dict]:
    return await state.get_recent_decisions(limit)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """A judge-facing live view — no curl required. Polls /stats,
    /breaker/status, /kill-switch/status, and /decisions every 2s."""
    return DASHBOARD_HTML
