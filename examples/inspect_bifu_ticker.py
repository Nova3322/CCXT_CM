"""Read-only Bifu test-environment ticker inspection for beginner acceptance."""

import argparse
import asyncio
import json

from ccxt_cm import create_exchange
from examples._bifu_readonly import retry_readonly_once


async def inspect_ticker(symbol="BTC/USDT", *, exchange=None, retry_delay=1.0):
    owns_exchange = exchange is None
    if owns_exchange:
        exchange = create_exchange("bifu", {"timeout": 30000}, mode="async")
        exchange.set_sandbox_mode(True)
    try:
        ticker = await retry_readonly_once(
            lambda: exchange.fetch_ticker(symbol),
            retry_delay=retry_delay,
        )
        return {
            "environment": "test",
            "symbol": ticker["symbol"],
            "instrument_id": exchange.market(symbol)["id"],
            "timestamp": ticker["timestamp"],
            "datetime": ticker["datetime"],
            "last": ticker["last"],
            "open": ticker["open"],
            "high": ticker["high"],
            "low": ticker["low"],
            "base_volume": ticker["baseVolume"],
            "quote_volume": ticker["quoteVolume"],
            "change": ticker["change"],
            "percentage": ticker["percentage"],
            "bid": ticker["bid"],
            "ask": ticker["ask"],
        }
    finally:
        if owns_exchange:
            await exchange.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="BTC/USDT")
    args = parser.parse_args()
    print(json.dumps(await inspect_ticker(args.symbol), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
