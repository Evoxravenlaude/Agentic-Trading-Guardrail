"""The demo script for the video: proves the negative case.

Run against a live guardrail proxy (`uvicorn guardrail.proxy:app`) with:

    python -m demo_agent.demo_scenario

Or against a deployed instance (e.g. Railway):

    PROXY_URL=https://your-app.up.railway.app python -m demo_agent.demo_scenario

Walks through, in order:
  1. A normal order — passes, gets forwarded (simulated fill in dry-run).
  2. The SAME order fired again immediately — blocked by dedup.
  3. A wildly oversized order — blocked by the position-size cap.
  4. A rapid-fire loop of 15 orders in a couple seconds — blocked by the
     rate limiter partway through.
  5. Three consecutive losing trades reported — trips the circuit breaker;
     the next order attempt is blocked outright.
  6. A manual kill switch engagement — halts everything until disengaged.

Each step prints the guardrail's JSON decision so the "blocked here" line
is visible on camera without needing to read logs.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx

from demo_agent.agent import place_order

PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:8000")


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def show(result: dict) -> None:
    allowed = result.get("allowed")
    label = "ALLOWED" if allowed else "BLOCKED"
    print(f"-> {label}")
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "PASS" else "REJECT"
        line = f"   [{mark}] {c['check']}"
        if c["reason"]:
            line += f" — {c['reason']}"
        print(line)


def setup() -> None:
    for attempt in range(3):
        try:
            httpx.post(f"{PROXY_URL}/market-price", json={"symbol": "BTCUSDT", "price": 60000.0}, timeout=30)
            httpx.post(f"{PROXY_URL}/account-balance", params={"balance": 10000.0}, timeout=30)
            httpx.post(f"{PROXY_URL}/breaker/reset", timeout=30)
            return
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == 2:
                raise
            print(f"  (network hiccup during setup, retrying {attempt + 1}/2...)")


def scenario_normal_order() -> None:
    banner("1. Normal order — should pass every check")
    result = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.01, price=60000.0, order_type="LIMIT")
    show(result)


def scenario_duplicate_order() -> None:
    banner("2. Duplicate order (simulated reconnect retry) — dedup should block the repeat")
    coid = f"demo-dup-{uuid.uuid4().hex[:8]}"
    r1 = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.01, price=60000.0, order_type="LIMIT", client_order_id=coid)
    print("First attempt:")
    show(r1)
    r2 = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.01, price=60000.0, order_type="LIMIT", client_order_id=coid)
    print("Retry with the same client_order_id:")
    show(r2)


def scenario_oversized_order() -> None:
    banner("3. Oversized order — position-size cap should block it")
    # 10000 balance, 10% cap = 1000 max notional. This order is ~30,000 notional.
    result = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.5, price=60000.0, order_type="LIMIT")
    show(result)


def scenario_rapid_fire_loop() -> None:
    banner("4. Rapid-fire loop (buggy agent stuck in a decision loop) — rate limiter should cut it off")
    for i in range(15):
        result = place_order(
            PROXY_URL, "ETHUSDT", "BUY", 0.01, price=3000.0, order_type="LIMIT",
            client_order_id=f"loop-{uuid.uuid4().hex[:8]}",
        )
        status = "ALLOWED" if result["allowed"] else f"BLOCKED ({result['checks'][-1]['reason']})"
        print(f"  order {i + 1:2d}: {status}")
        time.sleep(0.1)


def scenario_circuit_breaker() -> None:
    banner("5. Three consecutive losing trades — circuit breaker should trip and halt further orders")
    for i in range(3):
        httpx.post(f"{PROXY_URL}/trade-outcome", json={"symbol": "BTCUSDT", "pnl": -50.0}, timeout=30)
        print(f"  reported losing trade {i + 1}")
    result = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.01, price=60000.0, order_type="LIMIT")
    print("Next order attempt after the loss streak:")
    show(result)
    httpx.post(f"{PROXY_URL}/breaker/reset", timeout=30)
    print("  (breaker manually reset for the next scenario)")


def scenario_kill_switch() -> None:
    banner("6. Manual kill switch — an operator halt, independent of the automatic circuit breaker")
    httpx.post(f"{PROXY_URL}/kill-switch/engage", json={"reason": "suspected compromised agent"}, timeout=30)
    print("  operator engaged the kill switch")
    result = place_order(PROXY_URL, "BTCUSDT", "BUY", 0.01, price=60000.0, order_type="LIMIT")
    print("Order attempt while the kill switch is engaged:")
    show(result)
    httpx.post(f"{PROXY_URL}/kill-switch/disengage", timeout=30)
    print("  operator disengaged the kill switch")


def main() -> None:
    setup()
    scenario_normal_order()
    scenario_duplicate_order()
    scenario_oversized_order()
    scenario_rapid_fire_loop()
    scenario_circuit_breaker()
    scenario_kill_switch()
    banner("Done")
    print(f"\nOpen {PROXY_URL}/dashboard in a browser for a live view of everything that just happened.")


if __name__ == "__main__":
    main()
