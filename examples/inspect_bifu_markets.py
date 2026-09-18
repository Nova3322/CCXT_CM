"""Read-only Bifu test-environment market inspection for beginner acceptance."""

import argparse
import asyncio
import json
import sys

from ccxt import RequestTimeout

from ccxt_cm.exchanges.bifu import BifuREST


async def inspect_market(symbol="BTC/USDT", *, exchange=None, retry_delay=1.0):
    owns_exchange = exchange is None
    if owns_exchange:
        exchange = BifuREST({"timeout": 30000})
        exchange.set_sandbox_mode(True)
    try:
        try:
            markets = await exchange.load_markets()
        except RequestTimeout:
            print(
                "Bifu 测试环境首次请求超时，正在进行第 2 次只读重试...",
                file=sys.stderr,
            )
            if retry_delay:
                await asyncio.sleep(retry_delay)
            markets = await exchange.load_markets(True)
        market = exchange.market(symbol)
        return {
            "environment": "test",
            "market_count": len(markets),
            "id": market["id"],
            "exchange_symbol": market["info"]["symbol"],
            "symbol": market["symbol"],
            "type": market["type"],
            "active": market["active"],
            "precision": market["precision"],
            "limits": {
                "amount": market["limits"]["amount"],
                "cost": market["limits"]["cost"],
            },
            "examples": {
                "amount_1.23456789": exchange.amount_to_precision(symbol, 1.23456789),
                "price_100.129": exchange.price_to_precision(symbol, 100.129),
            },
        }
    finally:
        if owns_exchange:
            await exchange.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="BTC/USDT")
    args = parser.parse_args()
    print(json.dumps(await inspect_market(args.symbol), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
