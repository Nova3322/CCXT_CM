import asyncio
import hashlib
import hmac
from types import SimpleNamespace

import pytest
from aiohttp import web
from ccxt import (
    ArgumentsRequired,
    AuthenticationError,
    BadResponse,
    InvalidOrder,
    NotSupported,
    OrderNotFound,
    PermissionDenied,
    RequestTimeout,
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
        cancel_order_response={"accepted": True},
        create_order_response={"order_id": "created-order-456"},
        delays={},
        request_bodies=[],
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
        state.request_bodies.append((request.method, request.path, body))
        timestamp = request.headers.get("X-TS", "")
        payload = "\n".join((timestamp, request.method, request.path, body))
        expected = hmac.new(b"fixture-secret", payload.encode(), hashlib.sha256).hexdigest()
        authenticated = request.headers.get("X-API-KEY") == "fixture-key" and hmac.compare_digest(
            request.headers.get("X-SIGN", ""), expected
        )
        state.calls.append((request.method, request.path, dict(request.query), authenticated))
        delay = state.delays.get(request.path)
        if delay:
            await asyncio.sleep(delay)
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
        if request.path == "/spot/v1/order" and request.method == "POST":
            return web.json_response(state.create_order_response)
        if request.path == "/spot/v1/order/cancel" and request.method == "POST":
            return web.json_response(state.cancel_order_response)
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
async def test_create_limit_order_sends_bifu_request_and_returns_ccxt_ack(
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
        order = await exchange.create_order(
            "BTC/USDT",
            "limit",
            "buy",
            0.123456,
            100.129,
            {"clientOrderId": "fixture-create-1"},
        )
    finally:
        await exchange.close()

    assert order["id"] == "created-order-456"
    assert order["clientOrderId"] == "fixture-create-1"
    assert order["symbol"] == "BTC/USDT"
    assert order["type"] == "limit"
    assert order["side"] == "buy"
    assert order["timeInForce"] == "GTC"
    assert order["price"] == 100.13
    assert order["amount"] == 0.12345
    assert order["status"] is None
    assert order["filled"] is None
    assert order["remaining"] is None
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        ("POST", "/spot/v1/order", {}, True),
    ]
    assert bifu_private_server.request_bodies[-1] == (
        "POST",
        "/spot/v1/order",
        '{"client_order_id":"fixture-create-1","instrument_id":90000001,'
        '"price":"100.13","qty":"0.12345","side":"BUY",'
        '"time_in_force":"GTC","type":"LIMIT"}',
    )


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_limit_order_maps_post_only_to_bifu_time_in_force(
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
        order = await exchange.create_order(
            "BTC/USDT",
            "limit",
            "sell",
            0.1,
            100,
            {"clientOrderId": "fixture-post-only", "postOnly": True},
        )
    finally:
        await exchange.close()

    assert order["timeInForce"] == "PO"
    assert order["postOnly"] is True
    assert '"side":"SELL"' in bifu_private_server.request_bodies[-1][2]
    assert '"time_in_force":"POST_ONLY"' in bifu_private_server.request_bodies[-1][2]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_limit_order_accepts_ccxt_time_in_force(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.create_order(
            "BTC/USDT",
            "limit",
            "buy",
            0.1,
            100,
            {"clientOrderId": "fixture-fok", "timeInForce": "FOK"},
        )
    finally:
        await exchange.close()

    assert order["timeInForce"] == "FOK"
    assert '"time_in_force":"FOK"' in bifu_private_server.request_bodies[-1][2]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_limit_order_rejects_cost_below_market_minimum_before_post(
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
        with pytest.raises(InvalidOrder, match="minimum cost"):
            await exchange.create_order(
                "BTC/USDT",
                "limit",
                "buy",
                0.01,
                100,
                {"clientOrderId": "fixture-too-small"},
            )
    finally:
        await exchange.close()

    assert bifu_private_server.calls == [("GET", "/market/v1/meta", {}, None)]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_limit_order_accepts_cost_equal_to_market_minimum(
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
        order = await exchange.create_order(
            "BTC/USDT",
            "limit",
            "buy",
            "0.05",
            "100",
            {"clientOrderId": "fixture-exact-minimum"},
        )
    finally:
        await exchange.close()

    assert order["id"] == "created-order-456"
    assert '"price":"100"' in bifu_private_server.request_bodies[-1][2]
    assert '"qty":"0.05"' in bifu_private_server.request_bodies[-1][2]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_market_sell_sends_base_quantity_and_ioc(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.create_order(
            "BTC/USDT",
            "market",
            "sell",
            0.123456,
            params={"clientOrderId": "fixture-market-sell"},
        )
    finally:
        await exchange.close()

    assert order["id"] == "created-order-456"
    assert order["clientOrderId"] == "fixture-market-sell"
    assert order["symbol"] == "BTC/USDT"
    assert order["type"] == "market"
    assert order["side"] == "sell"
    assert order["timeInForce"] == "IOC"
    assert order["price"] is None
    assert order["amount"] == 0.12345
    assert order["status"] is None
    assert bifu_private_server.request_bodies[-1] == (
        "POST",
        "/spot/v1/order",
        '{"client_order_id":"fixture-market-sell","instrument_id":90000001,'
        '"qty":"0.12345","side":"SELL","time_in_force":"IOC",'
        '"type":"MARKET"}',
    )


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_market_buy_converts_amount_and_price_to_quote_budget(
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
        order = await exchange.create_order(
            "BTC/USDT",
            "market",
            "buy",
            0.123456,
            100.129,
            {"clientOrderId": "fixture-market-buy"},
        )
    finally:
        await exchange.close()

    assert order["id"] == "created-order-456"
    assert order["clientOrderId"] == "fixture-market-buy"
    assert order["symbol"] == "BTC/USDT"
    assert order["type"] == "market"
    assert order["side"] == "buy"
    assert order["timeInForce"] == "IOC"
    assert order["price"] is None
    assert order["amount"] is None
    assert order["cost"] is None
    assert order["status"] is None
    assert bifu_private_server.request_bodies[-1] == (
        "POST",
        "/spot/v1/order",
        '{"client_order_id":"fixture-market-buy","instrument_id":90000001,'
        '"quote_qty":"12.36","side":"BUY","time_in_force":"IOC",'
        '"type":"MARKET"}',
    )


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_market_buy_accepts_explicit_quote_cost(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.create_order(
            "BTC/USDT",
            "market",
            "buy",
            0.1,
            params={"clientOrderId": "fixture-market-cost", "cost": "5.019"},
        )
    finally:
        await exchange.close()

    assert order["type"] == "market"
    assert order["side"] == "buy"
    assert order["amount"] is None
    assert '"quote_qty":"5.01"' in bifu_private_server.request_bodies[-1][2]
    assert '"qty"' not in bifu_private_server.request_bodies[-1][2]
    assert '"price"' not in bifu_private_server.request_bodies[-1][2]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_market_buy_order_with_cost_uses_standard_ccxt_helper(
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
        assert exchange.has["createMarketOrder"] is False
        assert exchange.has["createMarketBuyOrder"] is False
        assert exchange.has["createMarketBuyOrderWithCost"] is True
        assert exchange.has["createMarketSellOrder"] is True
        order = await exchange.create_market_buy_order_with_cost(
            "BTC/USDT", "5.019", {"clientOrderId": "fixture-cost-helper"}
        )
    finally:
        await exchange.close()

    assert order["type"] == "market"
    assert order["side"] == "buy"
    assert '"quote_qty":"5.01"' in bifu_private_server.request_bodies[-1][2]


@pytest.mark.parametrize(
    ("side", "amount", "price", "params", "message"),
    [
        ("buy", 0.1, None, {}, "require a price or cost"),
        ("buy", 0.1, None, {"cost": 0}, "cost must be"),
        ("sell", 0.1, None, {"cost": 5}, "only supported for market buy"),
    ],
)
async def test_create_market_order_rejects_invalid_budget_before_network(
    side, amount, price, params, message
):
    exchange = create_exchange("bifu", mode="async")
    try:
        with pytest.raises(InvalidOrder, match=message):
            await exchange.create_order("BTC/USDT", "market", side, amount, price, params)
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"postOnly": True}, "do not support postOnly"),
        ({"timeInForce": "GTC"}, "must be IOC"),
    ],
)
async def test_create_market_order_rejects_limit_only_options_before_post(
    bifu_private_server, params, message
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
        with pytest.raises(InvalidOrder, match=message):
            await exchange.create_order("BTC/USDT", "market", "buy", 0.1, 100, params)
    finally:
        await exchange.close()

    assert bifu_private_server.calls == [("GET", "/market/v1/meta", {}, None)]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_market_buy_rejects_cost_below_minimum_before_post(
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
        with pytest.raises(InvalidOrder, match="minimum cost"):
            await exchange.create_order("BTC/USDT", "market", "buy", 0.1, params={"cost": "4.99"})
    finally:
        await exchange.close()

    assert bifu_private_server.calls == [("GET", "/market/v1/meta", {}, None)]


@pytest.mark.parametrize(
    ("order_type", "side", "amount", "price"),
    [
        (None, "buy", 0.1, 100),
        ("limit", None, 0.1, 100),
        ("limit", "buy", "not-a-number", 100),
        ("limit", "buy", 0.1, "not-a-number"),
    ],
)
async def test_create_order_maps_invalid_input_to_ccxt_invalid_order(
    order_type, side, amount, price
):
    exchange = create_exchange("bifu", mode="async")
    try:
        with pytest.raises(InvalidOrder):
            await exchange.create_order("BTC/USDT", order_type, side, amount, price)
    finally:
        await exchange.close()


async def test_create_order_rejects_unsupported_params_before_network():
    exchange = create_exchange("bifu", mode="async")
    try:
        with pytest.raises(NotSupported, match="unexpected"):
            await exchange.create_order("BTC/USDT", "limit", "buy", 0.1, 100, {"unexpected": True})
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_order_maps_bifu_permission_denied(bifu_private_server):
    bifu_private_server.forced_errors["/spot/v1/order"] = {
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
            await exchange.create_order("BTC/USDT", "limit", "buy", 0.1, 100)
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_order_rejects_ack_without_order_id(bifu_private_server):
    bifu_private_server.create_order_response = {}
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(BadResponse, match="missing order_id"):
            await exchange.create_order("BTC/USDT", "limit", "buy", 0.1, 100)
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_create_order_timeout_sends_exactly_one_post(bifu_private_server):
    bifu_private_server.delays["/spot/v1/order"] = 0.1
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        await exchange.load_markets()
        exchange.timeout = 10
        with pytest.raises(RequestTimeout):
            await exchange.create_order("BTC/USDT", "limit", "buy", 0.1, 100)
    finally:
        await exchange.close()

    order_posts = [
        call for call in bifu_private_server.calls if call[0:2] == ("POST", "/spot/v1/order")
    ]
    assert len(order_posts) == 1


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_cancel_order_sends_bifu_request_and_returns_ccxt_ack(bifu_private_server):
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        order = await exchange.cancel_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()

    assert order["id"] == "order-123"
    assert order["symbol"] == "BTC/USDT"
    assert order["status"] is None
    assert order["info"] == {"accepted": True}
    assert bifu_private_server.calls == [
        ("GET", "/market/v1/meta", {}, None),
        ("POST", "/spot/v1/order/cancel", {}, True),
    ]
    assert bifu_private_server.request_bodies[-1] == (
        "POST",
        "/spot/v1/order/cancel",
        '{"instrument_id":90000001,"order_id":"order-123"}',
    )


async def test_cancel_order_requires_symbol_before_network():
    exchange = create_exchange("bifu", mode="async")
    try:
        with pytest.raises(ArgumentsRequired, match="requires a symbol"):
            await exchange.cancel_order("order-123")
    finally:
        await exchange.close()


async def test_cancel_order_rejects_unsupported_params_before_network():
    exchange = create_exchange("bifu", mode="async")
    try:
        with pytest.raises(NotSupported, match="unexpected"):
            await exchange.cancel_order("order-123", "BTC/USDT", {"unexpected": True})
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_cancel_order_maps_bifu_order_not_found(bifu_private_server):
    bifu_private_server.forced_errors["/spot/v1/order/cancel"] = {
        "code": 3000,
        "message": "order not found",
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
        with pytest.raises(OrderNotFound, match="3000"):
            await exchange.cancel_order("missing-order", "BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_cancel_order_rejects_unaccepted_ack(bifu_private_server):
    bifu_private_server.cancel_order_response = {"accepted": False}
    exchange = create_exchange(
        "bifu",
        {"apiKey": "fixture-key", "secret": "fixture-secret"},
        mode="async",
    )
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_private_server.url
    exchange.urls["api"]["private"] = bifu_private_server.url
    try:
        with pytest.raises(BadResponse, match="not accepted"):
            await exchange.cancel_order("order-123", "BTC/USDT")
    finally:
        await exchange.close()


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
