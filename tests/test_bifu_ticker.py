import asyncio
from types import SimpleNamespace

import pytest
from aiohttp import web
from ccxt import BadResponse, NotSupported

from ccxt_cm import create_exchange
from examples.inspect_bifu_ticker import inspect_ticker


def new_bifu(config=None):
    return create_exchange("bifu", config, mode="async")


@pytest.fixture
async def bifu_ticker_server(unused_tcp_port):
    state = SimpleNamespace(
        calls=[],
        ticker_response={
            "instrument_id": 90000001,
            "last_price": "538944.47",
            "open_price": "538000.00",
            "high_price": "540000.00",
            "low_price": "530000.00",
            "volume": "0.44998",
            "quote_volume": "242966.07064",
            "count": "460",
            "price_change": "944.47",
            "price_change_percent": "0.18",
            "ts": "1789712421923",
        },
        ticker_status=200,
        tickers_response=None,
        delay_ticker_first_seconds=0,
    )

    async def meta(request):
        state.calls.append((request.method, request.path, dict(request.query)))
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
                        "rules": {},
                    }
                ],
            }
        )

    async def ticker(request):
        state.calls.append((request.method, request.path, dict(request.query)))
        if state.delay_ticker_first_seconds:
            delay = state.delay_ticker_first_seconds
            state.delay_ticker_first_seconds = 0
            await asyncio.sleep(delay)
        return web.json_response(state.ticker_response, status=state.ticker_status)

    async def tickers(request):
        state.calls.append((request.method, request.path, dict(request.query)))
        response = state.tickers_response or {"tickers": [state.ticker_response]}
        return web.json_response(response)

    app = web.Application()
    app.router.add_get("/market/v1/meta", meta)
    app.router.add_get("/market/v1/ticker", ticker)
    app.router.add_get("/market/v1/tickers", tickers)
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
async def test_fetch_ticker_returns_standard_24h_statistics(bifu_ticker_server):
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        ticker = await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()

    assert ticker["symbol"] == "BTC/USDT"
    assert ticker["timestamp"] == 1789712421923
    assert ticker["datetime"] == "2026-09-18T06:20:21.923Z"
    assert ticker["last"] == 538944.47
    assert ticker["open"] == 538000.0
    assert ticker["high"] == 540000.0
    assert ticker["low"] == 530000.0
    assert ticker["baseVolume"] == 0.44998
    assert ticker["quoteVolume"] == 242966.07064
    assert ticker["change"] == 944.47
    assert ticker["percentage"] == 0.18
    assert ticker["average"] is None
    assert ticker["bid"] is None
    assert ticker["ask"] is None
    assert ticker["info"]["count"] == "460"
    assert bifu_ticker_server.calls == [
        ("GET", "/market/v1/meta", {}),
        ("GET", "/market/v1/ticker", {"instrument_id": "90000001"}),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_tickers_returns_symbol_indexed_ccxt_tickers(bifu_ticker_server):
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        tickers = await exchange.fetch_tickers(["BTC/USDT"])
    finally:
        await exchange.close()

    assert list(tickers) == ["BTC/USDT"]
    assert tickers["BTC/USDT"]["last"] == 538944.47
    assert tickers["BTC/USDT"]["average"] is None
    assert bifu_ticker_server.calls == [
        ("GET", "/market/v1/meta", {}),
        ("GET", "/market/v1/tickers", {"type": "FULL"}),
    ]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_tickers_rejects_unknown_response_market(bifu_ticker_server):
    bifu_ticker_server.tickers_response = {
        "tickers": [{**bifu_ticker_server.ticker_response, "instrument_id": 999}]
    }
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(BadResponse, match="unknown market"):
            await exchange.fetch_tickers()
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_tickers_rejects_mini_shape_in_unified_method(bifu_ticker_server):
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(NotSupported, match="FULL"):
            await exchange.fetch_tickers(params={"type": "MINI"})
    finally:
        await exchange.close()

    assert bifu_ticker_server.calls == []


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_rejects_unsupported_params_before_request(bifu_ticker_server):
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(NotSupported, match="does not accept params"):
            await exchange.fetch_ticker("BTC/USDT", {"unexpected": "value"})
    finally:
        await exchange.close()

    assert bifu_ticker_server.calls == []


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_rejects_a_different_instrument(bifu_ticker_server):
    bifu_ticker_server.ticker_response["instrument_id"] = 90000002
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(BadResponse, match="instrument id"):
            await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_rejects_invalid_timestamp(bifu_ticker_server):
    bifu_ticker_server.ticker_response["ts"] = "not-a-timestamp"
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(BadResponse, match="timestamp"):
            await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_rejects_non_object_response(bifu_ticker_server):
    bifu_ticker_server.ticker_response = []
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(BadResponse, match="JSON object"):
            await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_keeps_empty_percentage_unknown(bifu_ticker_server):
    bifu_ticker_server.ticker_response["open_price"] = "0"
    bifu_ticker_server.ticker_response["price_change_percent"] = ""
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        ticker = await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()

    assert ticker["open"] == 0.0
    assert ticker["percentage"] is None
    assert ticker["average"] is None


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_fetch_ticker_reports_a_market_with_no_trades(bifu_ticker_server):
    bifu_ticker_server.ticker_status = 404
    bifu_ticker_server.ticker_response = {"code": 6005, "message": "no trades yet"}
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        with pytest.raises(BadResponse, match="has no trades"):
            await exchange.fetch_ticker("BTC/USDT")
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_readonly_ticker_inspector_explains_the_standard_result(bifu_ticker_server):
    exchange = new_bifu()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        result = await inspect_ticker("BTC/USDT", exchange=exchange)
    finally:
        await exchange.close()

    assert result == {
        "environment": "test",
        "symbol": "BTC/USDT",
        "instrument_id": "90000001",
        "timestamp": 1789712421923,
        "datetime": "2026-09-18T06:20:21.923Z",
        "last": 538944.47,
        "open": 538000.0,
        "high": 540000.0,
        "low": 530000.0,
        "base_volume": 0.44998,
        "quote_volume": 242966.07064,
        "change": 944.47,
        "percentage": 0.18,
        "bid": None,
        "ask": None,
    }


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_readonly_ticker_inspector_retries_one_timeout(bifu_ticker_server):
    bifu_ticker_server.delay_ticker_first_seconds = 0.05
    exchange = new_bifu({"timeout": 10})
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_ticker_server.url
    try:
        result = await inspect_ticker("BTC/USDT", exchange=exchange, retry_delay=0)
    finally:
        await exchange.close()

    assert result["last"] == 538944.47
    assert [call[1] for call in bifu_ticker_server.calls] == [
        "/market/v1/meta",
        "/market/v1/ticker",
        "/market/v1/ticker",
    ]
