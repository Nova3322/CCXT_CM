"""Bifu test-only order lifecycle acceptance with an explicit write confirmation."""

import argparse
import asyncio
import json
import os

from ccxt import NetworkError, OrderNotFound, RequestTimeout

from ccxt_cm import create_exchange

_CONFIRMATION = "BIFU_TEST_WRITE"
_PREFLIGHT_ATTEMPTS = 3
_PREFLIGHT_RETRY_DELAY = 1
_TERMINAL_STATUSES = {"canceled", "closed", "expired", "rejected"}


def _credentials_from_environment():
    api_key = os.environ.get("BIFU_API_KEY")
    secret = os.environ.get("BIFU_API_SECRET")
    if not api_key or not secret:
        raise RuntimeError("BIFU_API_KEY and BIFU_API_SECRET must be set")
    return {"apiKey": api_key, "secret": secret, "timeout": 30000}


async def _wait_for_order(
    exchange,
    order_id,
    symbol,
    *,
    terminal=False,
    poll_attempts=10,
    poll_delay=0.5,
):
    last_order = None
    for attempt in range(poll_attempts):
        try:
            last_order = await exchange.fetch_order(order_id, symbol)
            if not terminal or last_order["status"] in _TERMINAL_STATUSES:
                return last_order
        except (OrderNotFound, RequestTimeout):
            if attempt == poll_attempts - 1:
                raise
        if poll_delay:
            await asyncio.sleep(poll_delay)
    return last_order


async def _load_markets_with_retry(exchange):
    """Retry only the idempotent public metadata preflight."""
    for attempt in range(_PREFLIGHT_ATTEMPTS):
        try:
            return await exchange.load_markets()
        except NetworkError:
            if attempt == _PREFLIGHT_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_PREFLIGHT_RETRY_DELAY)


async def accept_order_lifecycle(
    symbol,
    side,
    amount,
    price,
    *,
    confirmation,
    exchange=None,
    poll_attempts=10,
    poll_delay=0.5,
):
    """Create one passive test order, query it, cancel it, and query the final state."""
    if confirmation != _CONFIRMATION:
        raise RuntimeError(f"test write requires confirmation {_CONFIRMATION}")

    owns_exchange = exchange is None
    if owns_exchange:
        exchange = create_exchange("bifu", _credentials_from_environment(), mode="async")
        exchange.set_sandbox_mode(True)

    created = None
    cancel_attempted = False
    try:
        await _load_markets_with_retry(exchange)
        created = await exchange.create_order(
            symbol,
            "limit",
            side,
            amount,
            price,
            {"postOnly": True},
        )
        order_id = created["id"]
        after_create = await _wait_for_order(
            exchange,
            order_id,
            symbol,
            poll_attempts=poll_attempts,
            poll_delay=poll_delay,
        )
        cancel_attempted = True
        await exchange.cancel_order(order_id, symbol)
        try:
            after_cancel = await _wait_for_order(
                exchange,
                order_id,
                symbol,
                terminal=True,
                poll_attempts=poll_attempts,
                poll_delay=poll_delay,
            )
        except OrderNotFound:
            # The current Bifu test environment can stop exposing an ended order
            # through the single-order endpoint. Verify the same id is absent from
            # open orders instead of treating invisibility as proof of cancellation.
            after_cancel = None
        open_orders = await exchange.fetch_open_orders(symbol)
        absent_from_open_orders = all(order["id"] != order_id for order in open_orders)
        if not absent_from_open_orders:
            raise RuntimeError("test order is still present in open orders after cancel")
        standard_fields = (
            "id",
            "clientOrderId",
            "symbol",
            "type",
            "side",
            "amount",
            "price",
            "status",
            "filled",
        )
        return {
            "environment": "test",
            "symbol": symbol,
            "side": side,
            "order_type": "limit",
            "post_only": True,
            "create_ack_standard_fields_present": all(
                field in created for field in standard_fields
            ),
            "create_status": created["status"],
            "query_after_create_status": after_create["status"],
            "cancel_command_accepted": True,
            "query_after_cancel_found": after_cancel is not None,
            "query_after_cancel_status": after_cancel["status"] if after_cancel else None,
            "order_absent_from_open_orders": absent_from_open_orders,
            "identifiers_redacted": True,
        }
    finally:
        if created is not None and not cancel_attempted:
            # This is cleanup, not a retry of create_order. If it fails, surface the
            # error so the operator knows an order may still be open.
            await exchange.cancel_order(created["id"], symbol)
        if owns_exchange:
            await exchange.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    parser.add_argument("side", choices=("buy", "sell"))
    parser.add_argument("amount", type=float)
    parser.add_argument("price", type=float)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    result = await accept_order_lifecycle(
        args.symbol,
        args.side,
        args.amount,
        args.price,
        confirmation=args.confirm,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
