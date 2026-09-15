"""Inspect declared capabilities offline; no exchange HTTP or WebSocket connection."""

import argparse
import asyncio
import json

from ccxt_cm import capability, create_exchange


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exchange", nargs="?", default="binance")
    parser.add_argument("--mode", choices=("async", "pro"), default="pro")
    args = parser.parse_args()
    exchange = create_exchange(args.exchange, mode=args.mode)
    try:
        names = (
            "fetchMarkets",
            "fetchTicker",
            "fetchOrderBook",
            "createOrder",
            "cancelOrder",
            "fetchOrder",
            "fetchOpenOrders",
            "fetchBalance",
            "watchTicker",
            "watchOrderBook",
            "watchOrders",
            "watchBalance",
            "createOrders",
            "cancelOrders",
            "createOrderWs",
        )
        print(
            json.dumps(
                {
                    "id": exchange.id,
                    "class": type(exchange).__module__,
                    "capabilities": {name: capability(exchange, name) for name in names},
                },
                indent=2,
            )
        )
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
