"""Explicit opt-in public network example. No credentials or trading requests."""

import argparse
import asyncio

from ccxt_cm import create_exchange, require_capabilities


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exchange")
    parser.add_argument("symbol", help="CCXT unified symbol, e.g. BTC/USDT")
    parser.add_argument("--connect", action="store_true", help="Actually contact the public API")
    parser.add_argument("--watch", action="store_true", help="Receive one WebSocket ticker update")
    args = parser.parse_args()
    if not args.connect:
        parser.error("Pass --connect to explicitly enable public network requests")
    exchange = create_exchange(args.exchange, mode="pro" if args.watch else "async")
    try:
        method = "watch_ticker" if args.watch else "fetch_ticker"
        require_capabilities(exchange, method)
        print(await asyncio.wait_for(getattr(exchange, method)(args.symbol), timeout=30))
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
