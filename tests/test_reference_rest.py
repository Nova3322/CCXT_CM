import copy
import hashlib
import hmac
import inspect
from unittest.mock import AsyncMock

import ccxt
import pytest

from examples.reference_exchange import ReferenceREST
from tests.conftest import BALANCE, BOOK, MARKET, ORDER, TICKER


def test_standard_signatures():
    for method in (
        "create_order",
        "cancel_order",
        "fetch_order",
        "fetch_open_orders",
        "fetch_trades",
    ):
        actual = list(inspect.signature(getattr(ReferenceREST, method)).parameters)
        expected = list(inspect.signature(getattr(ccxt.async_support.Exchange, method)).parameters)
        assert actual == expected, (method, actual, expected)


def test_markets_precision_and_unknown_values(rest):
    assert rest.market("BTC/USDT")["type"] == "spot"
    assert rest.amount_to_precision("BTC/USDT", 1.2349) == "1.234"
    assert rest.price_to_precision("BTC/USDT", 100.1234) == "100.1"
    assert rest.parse_market({**MARKET, "active": None})["active"] is None
    ticker = rest.parse_ticker(TICKER)
    assert ticker["timestamp"] == 1700000000000
    assert ticker["symbol"] == "BTC/USDT"
    assert ticker["last"] == 101
    assert ticker["info"] == TICKER
    order = rest.parse_order({"id": "ack", "symbol": "BTC_USDT"})
    for name in ("status", "filled", "remaining", "average", "timestamp"):
        assert order[name] is None, (name, order)
    assert rest.parse_balance({"USDT": {}})["USDT"]["free"] is None
    balance = rest.parse_balance(BALANCE)
    assert balance["USDT"] == {"free": 1000.0, "used": 100.0, "total": 1100.0}


@pytest.mark.parametrize(
    "state,status",
    [
        ("NEW", "open"),
        ("PARTIAL", "open"),
        ("FILLED", "closed"),
        ("CANCELED", "canceled"),
        ("REJECTED", "rejected"),
        ("EXPIRED", "expired"),
        ("UNRECOGNIZED", None),
    ],
)
def test_order_states(rest, state, status):
    raw = {**ORDER, "state": state, "filled": "0.25"}
    result = rest.parse_order(raw)
    assert result["status"] == status
    assert result["filled"] == 0.25
    assert result["remaining"] == 0.75
    assert result["info"] is raw


def test_golden_signing_and_params_not_mutated(rest):
    rest.nonce = lambda: 1700000000000
    params = {"symbol": "BTC_USDT", "id": "abc +/"}
    signed = rest.sign("order", "private", "GET", params)
    target = "/order?id=abc+%2B%2F&symbol=BTC_USDT"
    assert signed["url"].endswith(target)
    expected = hmac.new(
        b"fixture-secret", ("1700000000000GET" + target).encode(), hashlib.sha256
    ).hexdigest()
    assert signed["headers"]["X-Signature"] == expected
    assert params == {"symbol": "BTC_USDT", "id": "abc +/"}
    signed = rest.sign("order", "private", "POST", {"amount": "1", "price": "100"})
    assert signed["body"] == '{"amount":"1","price":"100"}'
    rest.apiKey = ""
    with pytest.raises(ccxt.AuthenticationError):
        rest.sign("order", "private", "GET")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost",
        "http://127.0.0.1.evil",
        "http://user:pass@127.0.0.1",
        "http://127.0.0.1?foo=bar",
    ],
)
def test_reference_rejects_non_loopback(rest, url):
    rest.urls["api"]["public"] = url
    with pytest.raises(ccxt.BadRequest):
        rest.sign("markets")


@pytest.mark.parametrize(
    "error,exception",
    [
        ("AUTH", ccxt.AuthenticationError),
        ("RATE_LIMIT", ccxt.RateLimitExceeded),
        ("INVALID_ORDER", ccxt.InvalidOrder),
        ("ORDER_NOT_FOUND", ccxt.OrderNotFound),
        ("UNKNOWN", ccxt.BadResponse),
    ],
)
def test_exchange_error_mapping(rest, error, exception):
    with pytest.raises(exception):
        rest.handle_errors(200, "OK", "", "GET", {}, "", {"error": error}, {}, None)


def test_malformed_response(rest):
    for raw in ([], {}, None):
        with pytest.raises(ccxt.BadResponse):
            rest.handle_errors(200, "OK", "", "GET", {}, "", raw, {}, None)


@pytest.mark.parametrize(
    "args,params,exception",
    [
        (("market", "buy", 1, None), {}, ccxt.NotSupported),
        (("limit", "invalid", 1, 100), {}, ccxt.InvalidOrder),
        (("limit", "buy", 1, None), {}, ccxt.InvalidOrder),
        (("limit", "buy", -1, 100), {}, ccxt.InvalidOrder),
        (("limit", "buy", float("nan"), 100), {}, ccxt.InvalidOrder),
        (("limit", "buy", 0.0001, 100), {}, ccxt.InvalidOrder),
        (("limit", "buy", 0.001, 0.1), {}, ccxt.InvalidOrder),
        (("limit", "buy", 1, 100), {"reduceOnly": True}, ccxt.NotSupported),
    ],
)
async def test_invalid_orders_never_send(rest, args, params, exception):
    rest.request = AsyncMock()
    with pytest.raises(exception):
        await rest.create_order("BTC/USDT", *args, params)
    rest.request.assert_not_called()


async def test_timeout_never_retries_write_or_becomes_success(rest):
    rest.fetch = AsyncMock(side_effect=ccxt.RequestTimeout("fixture timeout"))
    with pytest.raises(ccxt.RequestTimeout):
        await rest.create_order("BTC/USDT", "limit", "buy", 1, 100)
    assert rest.fetch.await_count == 1


async def test_unsupported_methods_do_not_return_empty_success(rest):
    with pytest.raises(ccxt.NotSupported):
        await rest.fetch_ohlcv("BTC/USDT")
    with pytest.raises(ccxt.NotSupported):
        await rest.watch_balance()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_rest_end_to_end_and_special_implicit_api(venue):
    exchange = ReferenceREST(venue.config)
    try:
        markets = await exchange.load_markets()
        assert markets["BTC/USDT"]["precision"]["amount"] == 0.001
        assert (await exchange.fetch_ticker("BTC/USDT"))["last"] == 101
        assert (await exchange.fetch_order_book("BTC/USDT", 1))["bids"] == [[100.0, 2.0]]
        assert len((await exchange.fetch_order_book("BTC/USDT"))["asks"]) == len(BOOK["asks"])
        with pytest.raises(ccxt.BadRequest):
            await exchange.fetch_order_book("BTC/USDT", 0)
        trades = await exchange.fetch_trades("BTC/USDT", 1700000000000, 1)
        assert trades[0]["cost"] == 200
        assert await exchange.fetch_trades("BTC/USDT", 1700000000001) == []
        assert (await exchange.fetch_balance())["USDT"]["total"] == 1100
        order = await exchange.create_order(
            "BTC/USDT", "limit", "buy", 1.2349, 100.123, {"clientOrderId": "fixture-client"}
        )
        assert order["id"] == "1"
        assert order["clientOrderId"] == "fixture-client"
        assert order["amount"] == 1.234
        assert order["status"] is None
        assert order["filled"] is None
        assert (await exchange.fetch_order(order["id"]))["status"] == "open"
        assert len(await exchange.fetch_open_orders("BTC/USDT")) == 1
        canceled = await exchange.cancel_order(order["id"], "BTC/USDT")
        assert canceled["status"] is None
        assert (await exchange.fetch_order(order["id"], "BTC/USDT"))["status"] == "canceled"
        assert await exchange.fetch_open_orders() == []
        assert await exchange.fetch_account_limits() == {"requestsPerMinute": 60}
        assert (await exchange.private_get_account_limits())["data"] == {"requestsPerMinute": 60}
        with pytest.raises(ccxt.OrderNotFound):
            await exchange.fetch_order("missing")
        exchange.secret = "wrong"
        with pytest.raises(ccxt.AuthenticationError):
            await exchange.fetch_balance()
    finally:
        await exchange.close()
    assert exchange.session is None


async def test_instances_isolate_config_and_caches(rest):
    other = ReferenceREST()
    try:
        rest.balance = copy.deepcopy(BALANCE)
        rest.options["privateSetting"] = 1
        assert other.balance == {}
        assert "privateSetting" not in other.options
    finally:
        await other.close()
