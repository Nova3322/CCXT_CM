"""Bifu test-only market-order acceptance with an explicit write confirmation."""

import argparse
import asyncio
import json
from decimal import Decimal, InvalidOperation

from ccxt import OrderNotFound, RequestTimeout

from ccxt_cm import create_exchange
from examples._bifu_write import credentials_from_environment, load_markets_with_retry

_CONFIRMATION = "BIFU_TEST_MARKET_WRITE"


def _validate_value(value):
    try:
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite() or decimal_value <= 0:
            raise ValueError
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("market-order value must be a positive finite number") from exc


async def _wait_for_order(exchange, order_id, symbol, poll_attempts, poll_delay):
    for attempt in range(poll_attempts):
        try:
            return await exchange.fetch_order(order_id, symbol)
        except OrderNotFound:
            pass
        except RequestTimeout:
            if attempt == poll_attempts - 1:
                raise
        if poll_delay:
            await asyncio.sleep(poll_delay)
    return None


async def _wait_for_trades(exchange, order_id, symbol, poll_attempts, poll_delay):
    for attempt in range(poll_attempts):
        trades = await exchange.fetch_my_trades(symbol, params={"order_id": order_id})
        matching = [trade for trade in trades if trade.get("order") == order_id]
        if matching:
            return matching
        if attempt < poll_attempts - 1 and poll_delay:
            await asyncio.sleep(poll_delay)
    return []


async def accept_market_order(
    symbol,
    side,
    value,
    *,
    confirmation,
    exchange=None,
    poll_attempts=10,
    poll_delay=0.5,
):
    """Create one test IOC market order and verify its resulting standard data."""
    if confirmation != _CONFIRMATION:
        raise RuntimeError(f"test market write requires confirmation {_CONFIRMATION}")
    if side not in ("buy", "sell"):
        raise ValueError("market-order side must be buy or sell")
    _validate_value(value)

    owns_exchange = exchange is None
    if owns_exchange:
        exchange = create_exchange("bifu", credentials_from_environment(), mode="async")
        exchange.set_sandbox_mode(True)

    created = None
    open_orders_checked = False
    try:
        await load_markets_with_retry(exchange)
        if side == "buy":
            created = await exchange.create_market_buy_order_with_cost(symbol, value)
            value_unit = "quote"
        else:
            created = await exchange.create_order(symbol, "market", "sell", value)
            value_unit = "base"

        order_id = created["id"]
        after_create = await _wait_for_order(exchange, order_id, symbol, poll_attempts, poll_delay)
        trades = await _wait_for_trades(exchange, order_id, symbol, poll_attempts, poll_delay)
        open_orders = await exchange.fetch_open_orders(symbol)
        still_open = any(order["id"] == order_id for order in open_orders)
        cleanup_attempted = False
        if still_open:
            cleanup_attempted = True
            await exchange.cancel_order(order_id, symbol)
            open_orders = await exchange.fetch_open_orders(symbol)
            still_open = any(order["id"] == order_id for order in open_orders)
            if still_open:
                raise RuntimeError("test market order is still open after cleanup cancel")
        open_orders_checked = True
        if not trades:
            raise RuntimeError("test market order has no matching trade evidence")

        order_fields = (
            "id",
            "clientOrderId",
            "symbol",
            "type",
            "side",
            "amount",
            "price",
            "cost",
            "status",
            "filled",
        )
        trade_fields = ("id", "order", "symbol", "price", "amount", "cost")
        return {
            "environment": "test",
            "symbol": symbol,
            "side": side,
            "order_type": "market",
            "requested_value": value,
            "requested_value_unit": value_unit,
            "create_ack_standard_fields_present": all(field in created for field in order_fields),
            "create_status": created["status"],
            "query_after_create_found": after_create is not None,
            "query_after_create_status": (
                after_create["status"] if after_create is not None else None
            ),
            "trade_count": len(trades),
            "trade_standard_fields_present": bool(trades)
            and all(field in trade for trade in trades for field in trade_fields),
            "order_absent_from_open_orders": not still_open,
            "unexpected_open_cleanup_attempted": cleanup_attempted,
            "identifiers_redacted": True,
        }
    finally:
        try:
            if created is not None and not open_orders_checked:
                order_id = created["id"]
                open_orders = await exchange.fetch_open_orders(symbol)
                if any(order["id"] == order_id for order in open_orders):
                    await exchange.cancel_order(order_id, symbol)
                    open_orders = await exchange.fetch_open_orders(symbol)
                    if any(order["id"] == order_id for order in open_orders):
                        raise RuntimeError("test market order is still open after cleanup cancel")
        finally:
            if owns_exchange:
                await exchange.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    parser.add_argument("side", choices=("buy", "sell"))
    parser.add_argument(
        "value",
        type=float,
        help="buy: quote-currency budget; sell: base-currency amount",
    )
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    result = await accept_market_order(
        args.symbol,
        args.side,
        args.value,
        confirmation=args.confirm,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
