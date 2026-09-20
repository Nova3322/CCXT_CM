"""Accept Bifu private WebSocket updates with one sandbox-only mock trade."""

import argparse
import asyncio
import json

from ccxt_cm import create_exchange
from examples._bifu_write import credentials_from_environment, load_markets_with_retry

_CONFIRMATION = "BIFU_TEST_WS_WRITE"


async def _wait_for_private_connection(exchange, timeout=10):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if any(
            "/spot/v1/userDataStream" in url and client.isConnected
            for url, client in exchange.clients.items()
        ):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("Bifu private WebSocket did not connect before the test write")


async def accept_private_streams(symbol, value, *, confirmation):
    if confirmation != _CONFIRMATION:
        raise RuntimeError(f"test WebSocket write requires confirmation {_CONFIRMATION}")
    exchange = create_exchange("bifu", credentials_from_environment(), mode="pro")
    exchange.set_sandbox_mode(True)
    waiters = []
    try:
        await load_markets_with_retry(exchange)
        waiters = [
            asyncio.create_task(exchange.watch_orders(symbol)),
            asyncio.create_task(exchange.watch_my_trades(symbol)),
            asyncio.create_task(exchange.watch_balance()),
        ]
        await _wait_for_private_connection(exchange)
        created = await exchange.create_mock_order(symbol, "buy", value)
        orders, trades, balance = await asyncio.wait_for(asyncio.gather(*waiters), timeout=20)
        return {
            "environment": "test",
            "symbol": symbol,
            "trigger": "create_mock_order",
            "create_ack_standard_fields_present": all(
                field in created for field in ("id", "symbol", "type", "side", "status", "info")
            ),
            "watch_orders": {
                "received": bool(orders),
                "standard_fields_present": all(
                    field in orders[-1]
                    for field in ("id", "symbol", "type", "side", "status", "info")
                ),
            },
            "watch_my_trades": {
                "received": bool(trades),
                "standard_fields_present": all(
                    field in trades[-1]
                    for field in ("id", "order", "symbol", "price", "amount", "info")
                ),
            },
            "watch_balance": {
                "received": bool(balance),
                "standard_fields_present": all(
                    field in balance for field in ("free", "used", "total", "info")
                ),
            },
            "identifiers_and_balances_redacted": True,
        }
    finally:
        for waiter in waiters:
            if not waiter.done():
                waiter.cancel()
        await exchange.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="BTC/USDT")
    parser.add_argument("value", nargs="?", type=float, default=5.5)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    result = await accept_private_streams(
        args.symbol,
        args.value,
        confirmation=args.confirm,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
