"""Thin wrapper around the Binance Agent OS MCP server.

Connects over Streamable HTTP to https://agent.binance.com/mcp/agentic.
Market data tool calls need no auth; account/trade tool calls need
user-granted permissions on the Agentic sub-account (out of scope to
provision here — this client works either against a real authenticated
session or in DRY_RUN mode, which never calls a trade-execution tool at
all and instead returns a simulated fill).

Tool names below (get_price, get_account_balance, place_order) follow the
naming Binance's docs describe for the Agent OS Skill Hub; if the live
schema differs, only this file needs to change — every check operates on
the OrderRequest/CheckResult models, not on MCP wire types.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from guardrail.config import GuardrailConfig
from guardrail.models import OrderRequest

logger = logging.getLogger("guardrail.mcp_client")

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when `mcp` isn't installed
    MCP_SDK_AVAILABLE = False


class BinanceMCPClient:
    """Talks to the Binance Agent OS MCP server, or simulates it in dry-run mode."""

    def __init__(self, config: GuardrailConfig):
        self.config = config
        self._session: Optional["ClientSession"] = None
        self._cm = None  # holds the streamablehttp_client context manager

    async def connect(self) -> None:
        if self.config.dry_run:
            logger.info("MCP client in DRY_RUN mode — not connecting to %s", self.config.mcp_url)
            return
        if not MCP_SDK_AVAILABLE:
            raise RuntimeError(
                "The `mcp` package is not installed. Run `pip install mcp` or set "
                "GUARDRAIL_DRY_RUN=true to run without a live Binance connection."
            )
        self._cm = streamablehttp_client(self.config.mcp_url)
        read_stream, write_stream, _ = await self._cm.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("Connected to Binance Agent OS MCP server at %s", self.config.mcp_url)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._cm is not None:
            await self._cm.__aexit__(None, None, None)
            self._cm = None

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("MCP session not connected (call connect() first, or use dry_run mode)")
        result = await self._session.call_tool(name, arguments)
        # MCP tool results are a list of content blocks; text blocks carry JSON payloads.
        for block in result.content:
            if getattr(block, "type", None) == "text":
                try:
                    return json.loads(block.text)
                except json.JSONDecodeError:
                    return {"raw": block.text}
        return {}

    # ---------------- Market data (no auth required) ----------------

    async def get_price(self, symbol: str) -> Optional[float]:
        if self.config.dry_run:
            return None  # demo agent supplies its own simulated prices
        try:
            data = await self._call_tool("get_price", {"symbol": symbol})
            price = data.get("price")
            return float(price) if price is not None else None
        except Exception:  # noqa: BLE001 - market data is best-effort for guardrail checks
            logger.exception("get_price(%s) failed", symbol)
            return None

    # ---------------- Account (requires granted permissions) ----------------

    async def get_account_balance(self) -> Optional[float]:
        if self.config.dry_run:
            return None  # caller falls back to config.fallback_account_balance
        try:
            data = await self._call_tool("get_account_balance", {})
            balance = data.get("balance")
            return float(balance) if balance is not None else None
        except Exception:  # noqa: BLE001
            logger.exception("get_account_balance() failed")
            return None

    # ---------------- Trade execution (only reached if all checks pass) ----------------

    async def place_order(self, order: OrderRequest) -> dict[str, Any]:
        if self.config.dry_run:
            logger.info("[DRY_RUN] would forward order %s to Binance Agent OS", order.request_id)
            return {
                "dry_run": True,
                "request_id": order.request_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "status": "SIMULATED_FILLED",
            }
        return await self._call_tool(
            "place_order",
            {
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.order_type.value,
                "quantity": order.quantity,
                "price": order.price,
                "clientOrderId": order.client_order_id,
            },
        )
