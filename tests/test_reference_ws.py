import asyncio
import copy
from unittest.mock import Mock

import ccxt
import pytest

from examples.reference_exchange import ReferencePro
from tests.conftest import BALANCE, BOOK, ORDER, TICKER


def client_stub():
    client = Mock()
    client.subscriptions = {"book:BTC_USDT": True, "auth_ok": True}
    return client


def test_book_snapshot_delta_duplicates_gap_and_resnapshot(pro):
    client = client_stub()
    pro.handle_message(client, {"channel": "book", "data": copy.deepcopy(BOOK)})
    assert pro.orderbooks["BTC/USDT"]["nonce"] == 10
    delta = {
        "symbol": "BTC_USDT",
        "kind": "delta",
        "sequence": 11,
        "time": 1700000000100,
        "bids": [[100, 0], [98, 2]],
        "asks": [[102, 1]],
    }
    pro.handle_message(client, {"channel": "book", "data": delta})
    assert list(pro.orderbooks["BTC/USDT"]["bids"]) == [[99, 3], [98, 2]]
    assert pro.orderbooks["BTC/USDT"]["asks"][0] == [102, 1]
    calls = client.resolve.call_count
    pro.handle_message(client, {"channel": "book", "data": delta})
    assert client.resolve.call_count == calls
    pro.handle_message(client, {"channel": "book", "data": {**delta, "sequence": 13}})
    assert "BTC/USDT" not in pro.orderbooks
    assert "book:BTC_USDT" not in client.subscriptions
    assert isinstance(client.reject.call_args.args[0], ccxt.InvalidNonce)
    pro.handle_message(client, {"channel": "book", "data": {**BOOK, "sequence": 20}})
    assert pro.orderbooks["BTC/USDT"]["nonce"] == 20


def test_private_delta_merge_and_bounded_cache(pro):
    client = client_stub()
    pro.handle_message(client, {"channel": "balance", "data": copy.deepcopy(BALANCE)})
    pro.handle_message(
        client, {"channel": "balance", "delta": True, "data": {"USDT": {"free": "900"}}}
    )
    assert pro.balance["BTC"]["free"] == 2
    assert pro.balance["USDT"]["total"] == 1000
    pro.handle_message(client, {"channel": "orders", "data": [copy.deepcopy(ORDER)]})
    pro.handle_message(
        client, {"channel": "orders", "data": [{"id": "1", "symbol": "BTC_USDT", "filled": "0.5"}]}
    )
    assert pro.orders[0]["amount"] == 1
    assert pro.orders[0]["filled"] == 0.5
    assert pro.orders[0]["remaining"] == 0.5
    for number in range(120):
        pro.handle_message(
            client, {"channel": "orders", "data": [{**ORDER, "id": str(number + 2)}]}
        )
    assert len(pro.orders) == pro.options["ordersLimit"]
    client.reject.assert_not_called()


def test_authentication_unknown_frames_and_error_propagation(pro):
    client = client_stub()
    client.subscriptions = {}
    pro.handle_message(client, {"channel": "balance", "data": BALANCE})
    assert isinstance(client.reject.call_args.args[0], ccxt.AuthenticationError)
    pro.handle_message(client, {"event": "login", "ok": False})
    assert isinstance(client.reject.call_args.args[0], ccxt.AuthenticationError)
    pro.handle_message(client, {"event": "login", "ok": True})
    assert client.subscriptions["auth_ok"] is True
    for message in (b"broken", {"channel": "unknown", "data": {}}, {"event": "unexpected"}):
        before = client.reject.call_count
        pro.handle_message(client, message)
        assert client.reject.call_count == before + 1
    pro.handle_message(client, {"channel": "ticker", "data": TICKER})
    assert pro.tickers["BTC/USDT"]["last"] == 101
    pro.handle_message(client, {"event": "subscribed"})


async def test_ws_limits_params_and_unsupported(pro):
    with pytest.raises(ccxt.BadRequest):
        await pro.watch_order_book("BTC/USDT", 0)
    with pytest.raises(ccxt.NotSupported):
        await pro.watch_ticker("BTC/USDT", {"unexpected": True})
    with pytest.raises(ccxt.NotSupported):
        await pro.watch_trades("BTC/USDT")


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_real_websocket_subscriptions_updates_reconnect_and_close(venue):
    exchange = ReferencePro(venue.config)
    try:
        assert (await asyncio.wait_for(exchange.watch_ticker("BTC/USDT"), 3))["last"] == 101
        first = await asyncio.wait_for(exchange.watch_order_book("BTC/USDT", 1), 3)
        assert len(first["bids"]) == 1
        assert len(exchange.orderbooks["BTC/USDT"]["bids"]) == 2
        order = (await asyncio.wait_for(exchange.watch_orders("BTC/USDT"), 3))[0]
        assert order["id"] == "1"
        assert (await asyncio.wait_for(exchange.watch_balance(), 3))["USDT"]["total"] == 1100
        # Already-authenticated private calls must not wait for another login ACK.
        pending = asyncio.create_task(exchange.watch_orders("BTC/USDT", 1700000000000, 1))
        await asyncio.sleep(0.03)
        await venue.clients[0].send_json(
            {"channel": "orders", "data": [{**ORDER, "filled": "0.5"}]}
        )
        assert (await asyncio.wait_for(pending, 3))[0]["filled"] == 0.5
        assert len([x for x in venue.subscriptions if x["channel"] == "orders"]) == 1
        pending = asyncio.create_task(exchange.watch_order_book("BTC/USDT"))
        await asyncio.sleep(0.03)
        await venue.clients[0].send_json(
            {
                "channel": "book",
                "data": {
                    "symbol": "BTC_USDT",
                    "kind": "delta",
                    "sequence": 12,
                    "bids": [],
                    "asks": [],
                },
            }
        )
        with pytest.raises(ccxt.InvalidNonce):
            await asyncio.wait_for(pending, 3)
        assert "BTC/USDT" not in exchange.orderbooks
        assert (await asyncio.wait_for(exchange.watch_order_book("BTC/USDT"), 3))["nonce"] == 10
        pending = asyncio.create_task(exchange.watch_ticker("BTC/USDT"))
        await asyncio.sleep(0.03)
        await venue.clients[0].close()
        with pytest.raises(ccxt.NetworkError):
            await asyncio.wait_for(pending, 3)
        assert exchange.orderbooks == {}
        assert exchange.balance == {}
        assert exchange.orders is None
        assert (await asyncio.wait_for(exchange.watch_ticker("BTC/USDT"), 3))["last"] == 101
        assert len(venue.clients) == 2
        pending = asyncio.create_task(exchange.watch_ticker("BTC/USDT"))
        await asyncio.sleep(0.03)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    finally:
        await exchange.close()
    assert exchange.session is None
    assert exchange.clients == {}


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_real_ws_authentication_rejection(venue):
    exchange = ReferencePro({**venue.config, "secret": "wrong"})
    try:
        with pytest.raises(ccxt.AuthenticationError):
            await asyncio.wait_for(exchange.watch_balance(), 3)
    finally:
        await exchange.close()


def test_malformed_frames_invalidate_stream_and_missing_balance_snapshot(pro):
    client = client_stub()
    pro.handle_message(client, {"channel": "book", "data": copy.deepcopy(BOOK)})
    pro.handle_message(client, {"channel": "book", "data": {**BOOK, "kind": "invalid"}})
    assert pro.orderbooks == {}
    assert client.subscriptions == {}
    assert isinstance(client.reject.call_args.args[0], ccxt.BadResponse)
    client.subscriptions["auth_ok"] = True
    pro.handle_message(client, {"channel": "balance", "delta": True, "data": BALANCE})
    assert isinstance(client.reject.call_args.args[0], ccxt.InvalidNonce)
    assert pro.balance == {}


@pytest.mark.parametrize("new_updates", [True, False])
async def test_order_cache_new_updates_modes(pro, new_updates):
    from unittest.mock import AsyncMock

    client = client_stub()
    pro.newUpdates = new_updates
    pro.handle_message(client, {"channel": "orders", "data": [copy.deepcopy(ORDER)]})
    pro._subscribe = AsyncMock(return_value=pro.orders)
    assert len(await pro.watch_orders("BTC/USDT")) == 1
    pro.handle_message(client, {"channel": "orders", "data": [{**ORDER, "id": "2"}]})
    result = await pro.watch_orders("BTC/USDT")
    assert len(result) == (1 if new_updates else 2)
    assert result[-1]["id"] == "2"
