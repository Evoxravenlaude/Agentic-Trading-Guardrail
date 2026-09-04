"""Minimal toy agent used purely to exercise the guardrail layer.

It knows nothing about Binance directly — it only talks to the guardrail
proxy's /trade endpoint, exactly like a real trading agent would. This
file exists to have something concrete "in front of" the guardrail for
the demo video, per the build plan's Day 5 step.
"""

from __future__ import annotations

import argparse
import json
import uuid

import httpx

DEFAULT_PROXY_URL = "http://localhost:8000"


def place_order(
    proxy_url: str,
    symbol: str,
    side: str,
    quantity: float,
    price: float | None = None,
    order_type: str = "MARKET",
    agent_id: str = "demo-agent",
    client_order_id: str | None = None,
) -> dict:
    payload = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "price": price,
        "agent_id": agent_id,
        "client_order_id": client_order_id,
    }
    resp = httpx.post(f"{proxy_url}/trade", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Toy agent — sends one order through the guardrail proxy")
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--quantity", type=float, default=0.01)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--type", dest="order_type", choices=["MARKET", "LIMIT"], default="MARKET")
    parser.add_argument("--client-order-id", default=None)
    args = parser.parse_args()

    result = place_order(
        args.proxy_url,
        args.symbol,
        args.side,
        args.quantity,
        price=args.price,
        order_type=args.order_type,
        client_order_id=args.client_order_id or f"demo-{uuid.uuid4().hex[:8]}",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
