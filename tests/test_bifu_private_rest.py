import hashlib
import hmac
from types import SimpleNamespace

import pytest
from aiohttp import web
from ccxt import (
    AuthenticationError,
    BadResponse,
    NotSupported,
    OrderNotFound,
    PermissionDenied,
)

from ccxt_cm import create_exchange
from examples.inspect_bifu_orders import inspect_orders


async def test_order_inspection_keeps_unknown_and_known_statuses():
    base_order = {
        "id": "[REDACTED]",
        "symbol": "BTC/USDT",
        "type": "limit",
        "side": "buy",
        "amount": 1.0,
        "filled": 0.0,
    }

    class FakeExchange:
        async def fetch_open_orders(self, symbol):
            return [
                dict(base_order, status=None),
                dict(base_order, status="open"),
            ]

        async def fetch_closed_orders(self, symbol, limit):
            return []

        async def fetch_my_trades(self, symbol, limit):
            return []

        async def fetch_order(self, order_id, symbol):
            return dict(base_order, status="open")

    result = await inspect_orders(exchange=FakeExchange(), retry_delay=0)

    assert result["open_statuses"] == [None, "open"]


@pytest.fixture
async def bifu_private_server(unused_tcp_port):
    state = SimpleNamespace(
        calls=[],
        forced_errors={},
        history_orders_response=None,
        my_trades_response=None,
        open_orders_response=None,
        order_error=None,
        order={
            "order_id": "order-123",
            "client_order_id": "client-123",
            "account_id": "[REDACTED]",
            "instrument_id": 90000001,
            "side": "BUY",
            "type": "LIMIT",
            "time_in_force": "POST_ONLY",
            "price": "100.10",
            "orig_qty": "0.2",
            "quote_qty": "0",
            "display_qty": "0",
            "status": "PARTIALLY_FILLED",
            "filled_qty": "0.05",
            "cum_quote": "5.005",
            "cancel_reason": "",
            "created_ts": "1700000000000",
            "updated_ts": "1700000000500",
            "upper_trigger_price": "0",
            "lower_trigger_price": "0",
            "upper_order_price": "0",
            "lower_order_price": "0",
            "origin": "USER",
        },
    )

    async def endpoint(request):
        body = await request.text()
        timestamp = request.headers.get("X-TS", "")
        payload = "\n".join((timestamp, request.method, request.path, body))
        expected = hmac.new(b"fixture-secret", payload.encode(), hashlib.sha256).hexdigest()
        authenticated = request.headers.get("X-API-KEY") == "fixture-key" and hmac.compare_digest(
            request.headers.get("X-SIGN", ""), expected
        )
        state.calls.append((request.method, request.path, dict(request.query), authenticated))
        if not authenticated:
            return web.json_response({"code": 4002}, status=401)
        forced_error = state.forced_errors.get(request.path)
        if forced_error:
            return web.json_response(forced_error, status=403)
        if request.path == "/spot/v1/account":
            return web.json_response(
                {
                    "balances": [
                        {"asset_id": 1, "available": "0.5", "frozen": "0.1"},
                        {"asset_id": 2, "available": "100", "frozen": "5"},
                        {"asset_id": 999, "available": "3", "frozen": "0"},
                    ]
                }
            )
        if request.path == "/spot/v1/order/query":
            if state.order_error:
                return web.json_response(state.order_error, status=404)
            return web.json_response(state.order)
        if request.path == "/spot/v1/openOrders":
            response = state.open_orders_response
            return web.json_response(
                response if response is not None else {"orders": [state.order]}
            )
        if request.path == "/spot/v1/historyOrders":
            response = state.history_orders_response
            closed_order = dict(
                state.order,
                status="FILLED",
                filled_qty="0.2",
                cum_quote="20.02",
            )
            return web.json_response(
                response
                if response is not None
                else {"orders": [closed_order], "next_cursor": "next-page"}
            )
        if request.path == "/spot/v1/myTrades":
            response = state.my_trades_response
            return web.json_response(
                response
                if response is not None
                else {
                    "trades": [
                        {
                            "order_id": "order-123",
                            "instrument_id": 90000001,
                            "side": "BUY",
                            "price": "100.10",
                            "qty": "0.05",
                            "fee": "0.00005",
                            "fee_asset_id": 1,
                            "is_maker": True,
                            "product": "SPOT",
                            "ts_ms": "1700000000250",
                            "trade_id": "trade-123",
                        }
                    ],
                    "next_cursor": "next-page",
                }
            )
        return web.json_response({"code": 1000}, status=404)

    async def meta(request):
        state.calls.append((request.method, request.path, dict(request.query), None))
        return web.json_response(
            {
                "assets": [
                    {"asset_id": 1, "code": "BTC"},
                    {"asset_id": 2, "code": "USDT"},
                ],
                "spots": [
                    {
                        "instrument_id": 90000001,
                        "base_asset_id": 1,
                        "quote_asset_id": 2,
                        "status": "TRADING",
                        "rules": {
                            "price_tick": "0.01",
                            "qty_step": "0.00001",
                            "min_qty": "0.00001",
                            "max_qty": "9000",
                            "min_notional": "5",
                            "max_notional": "1000000",
                        },
                    }
                ],
            }
        )

    app = web.Application()
    app.router.add_get("/market/v1/meta", meta)
    app.router.add_route("*", "/spot/{path:.*}", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    state.url = f"http://127.0.0.1:{unused_tcp_port}"
    try:
        yield state
    finally:
        await runner.cleanup()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_balance_authenticates_and_returns_ccxt_balance(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        balance = await exchange.fetch_balance()
    finally:
        await exchange.close()

    assert balance["BTC"] == {"free": 0.5, "used": 0.1, "total": 0.6}
    assert balance["USDT"] == {"free": 100.0, "used": 5.0, "total": 105.0}
    assert balance["999"] == {"free": 3.0, "used": 0.0, "total": 3.0}
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        ("GET", "/spot/v1/account", {}, True),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_balance_maps_authentication_failure(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "wrong-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(AuthenticationError, match="4002"):
            await exchange.fetch_balance()
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_order_returns_a_standard_ccxt_order(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.fetch_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()

    assert order["id"] == "order-123"
    assert order["clientOrderId"] == "client-123"
    assert order["symbol"] == "BTC/USDT"
    assert order["type"] == "limit"
    assert order["side"] == "buy"
    assert order["timeInForce"] == "PO"
    assert order["postOnly"] is True
    assert order["status"] == "open"
    assert order["price"] == 100.1
    assert order["amount"] == 0.2
    assert order["filled"] == 0.05
    assert order["remaining"] == 0.15
    assert order["cost"] == 5.005
    assert order["average"] == 100.1
    assert order["timestamp"] == 1700000000000
    assert order["lastUpdateTimestamp"] == 1700000000500
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        ("GET", "/spot/v1/order/query", {"order_id": "order-123"}, True),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_open_orders_returns_standard_orders_for_one_symbol(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        orders = await exchange.fetch_open_orders("BTC/USDT")
    finally:
        await exchange.close()

    assert len(orders) == 1
    assert orders[0]["id"] == "order-123"
    assert orders[0]["status"] == "open"
    assert orders[0]["symbol"] == "BTC/USDT"
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        ("GET", "/spot/v1/openOrders", {"instrument_id": "90000001"}, True),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_open_orders_accepts_the_live_empty_object_shape(bifu_private_server):
    bifu_private_server.open_orders_response = {}
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        assert await exchange.fetch_open_orders("BTC/USDT") == []
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_order_maps_bifu_order_not_found(bifu_private_server):
    bifu_private_server.order_error = {"code": 3000, "message": "order not found"}
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(OrderNotFound, match="3000"):
            await exchange.fetch_order("missing-order", "BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_order_rejects_a_mismatched_response(bifu_private_server):
    bifu_private_server.order["order_id"] = "different-order"
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(BadResponse, match="order id does not match"):
            await exchange.fetch_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_order_keeps_unknown_status_unknown(bifu_private_server):
    bifu_private_server.order["status"] = "PAUSED_BY_OPERATOR"
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.fetch_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()

    assert order["status"] is None


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_order_handles_quote_amount_market_buy_and_fee(bifu_private_server):
    bifu_private_server.order.update(
        {
            "type": "MARKET",
            "time_in_force": "IOC",
            "orig_qty": "0",
            "quote_qty": "25",
            "status": "FILLED",
            "filled_qty": "0.249",
            "cum_quote": "24.9249",
            "cum_fee": "0.000249",
            "fee_asset_id": 1,
        }
    )
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.fetch_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()

    assert order["type"] == "market"
    assert order["status"] == "closed"
    assert order["amount"] is None
    assert order["filled"] == 0.249
    assert order["remaining"] is None
    assert order["cost"] == 24.9249
    assert order["fee"] == {"cost": 0.000249, "currency": "BTC"}


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(
    ("method_name", "endpoint"),
    [
        ("fetch_open_orders", "/spot/v1/openOrders"),
        ("fetch_closed_orders", "/spot/v1/historyOrders"),
        ("fetch_my_trades", "/spot/v1/myTrades"),
    ],
)
async def test_private_order_lists_map_bifu_permission_denied(
    bifu_private_server, method_name, endpoint
):
    bifu_private_server.forced_errors[endpoint] = {
        "code": 4001,
        "message": "permission denied",
    }
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(PermissionDenied, match="4001"):
            await getattr(exchange, method_name)("BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(
    "method_name",
    ["fetch_order", "fetch_open_orders", "fetch_closed_orders", "fetch_my_trades"],
)
async def test_private_order_methods_reject_unsupported_params_before_request(
    bifu_private_server, method_name
):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(NotSupported, match="does not accept params"):
            if method_name == "fetch_order":
                await exchange.fetch_order("order-123", "BTC/USDT", {"unsupported": True})
            else:
                await getattr(exchange, method_name)("BTC/USDT", params={"unsupported": True})
    finally:
        await exchange.close()

    assert bifu_private_server.calls == []


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_closed_orders_uses_server_filters_and_returns_standard_orders(
    bifu_private_server,
):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        orders = await exchange.fetch_closed_orders(
            "BTC/USDT",
            since=1699999999000,
            limit=10,
            params={"cursor": "page-1"},
        )
    finally:
        await exchange.close()

    assert len(orders) == 1
    assert orders[0]["id"] == "order-123"
    assert orders[0]["status"] == "closed"
    assert orders[0]["filled"] == 0.2
    assert orders[0]["remaining"] == 0.0
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        (
            "GET",
            "/spot/v1/historyOrders",
            {
                "cursor": "page-1",
                "instrument_id": "90000001",
                "limit": "10",
                "start_ts_ms": "1699999999000",
            },
            True,
        ),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_my_trades_returns_standard_private_trades(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        trades = await exchange.fetch_my_trades(
            "BTC/USDT",
            since=1699999999000,
            limit=10,
            params={"cursor": "page-1"},
        )
    finally:
        await exchange.close()

    assert len(trades) == 1
    assert trades[0]["id"] == "trade-123"
    assert trades[0]["order"] == "order-123"
    assert trades[0]["symbol"] == "BTC/USDT"
    assert trades[0]["side"] == "buy"
    assert trades[0]["takerOrMaker"] == "maker"
    assert trades[0]["price"] == 100.1
    assert trades[0]["amount"] == 0.05
    assert trades[0]["cost"] == 5.005
    assert trades[0]["fee"] == {"cost": 0.00005, "currency": "BTC"}
    assert trades[0]["timestamp"] == 1700000000250
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        (
            "GET",
            "/spot/v1/myTrades",
            {
                "cursor": "page-1",
                "instrument_id": "90000001",
                "limit": "10",
                "start_ts_ms": "1699999999000",
            },
            True,
        ),
    ]
