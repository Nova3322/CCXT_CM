import asyncio
from types import SimpleNamespace

import ccxt
import pytest
from aiohttp import web

from ccxt_cm.exchanges.bifu import BifuREST
from examples.inspect_bifu_markets import inspect_market


@pytest.fixture
async def bifu_market_server(unused_tcp_port):
    state = SimpleNamespace(
        calls=[],
        response={
            "globals": {"revision": 1000, "trading": "OPEN"},
            "assets": [
                {"asset_id": 1, "code": "BTC", "name": "Bitcoin", "scale": 8},
                {"asset_id": 2, "code": "USDT", "name": "Tether", "scale": 8},
            ],
            "spots": [
                {
                    "instrument_id": 90000001,
                    "symbol": "BTC-USDT",
                    "base_asset_id": 1,
                    "quote_asset_id": 2,
                    "status": "TRADING",
                    "display_status": "LISTED",
                    "rules": {
                        "price_tick": "0.01",
                        "qty_step": "0.00001",
                        "min_qty": "0.00001",
                        "max_qty": "9000",
                        "min_notional": "5",
                        "max_notional": "1000000",
                    },
                    "taker_fee_rate": "0.0005",
                    "maker_fee_rate": "0.0002",
                }
            ],
        },
        delay_first_seconds=0,
    )

    async def meta(request):
        state.calls.append((request.method, request.path, dict(request.query)))
        if state.delay_first_seconds:
            delay = state.delay_first_seconds
            state.delay_first_seconds = 0
            await asyncio.sleep(delay)
        return web.json_response(state.response)

    app = web.Application()
    app.router.add_get("/market/v1/meta", meta)
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
async def test_load_markets_returns_standard_spot_market(bifu_market_server):
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        markets = await exchange.load_markets()
    finally:
        await exchange.close()

    market = markets["BTC/USDT"]
    assert market["id"] == "90000001"
    assert market["info"]["symbol"] == "BTC-USDT"
    assert market["type"] == "spot"
    assert market["spot"] is True
    assert market["settle"] is None
    assert market["contractSize"] is None
    assert market["active"] is True
    assert market["precision"] == {"amount": 0.00001, "price": 0.01}
    assert market["limits"]["amount"] == {"min": 0.00001, "max": 9000.0}
    assert market["limits"]["cost"] == {"min": 5.0, "max": 1000000.0}
    assert bifu_market_server.calls == [("GET", "/market/v1/meta", {})]


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_load_markets_rejects_asset_without_code(bifu_market_server):
    del bifu_market_server.response["assets"][0]["code"]
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        with pytest.raises(ccxt.BadResponse, match="asset code"):
            await exchange.load_markets()
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_load_markets_rejects_unsupported_params_before_request(bifu_market_server):
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        with pytest.raises(ccxt.NotSupported, match="does not accept params"):
            await exchange.load_markets(True, {"unexpected": "value"})
    finally:
        await exchange.close()

    assert bifu_market_server.calls == []


def test_public_query_uses_ccxt_encoding_and_stable_order():
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)

    signed = exchange.sign(
        "market/v1/meta",
        params={"q": "a b+/", "enabled": True},
    )

    assert signed["url"] == ("https://flame-api.bifu.dev/market/v1/meta?enabled=true&q=a%20b%2B%2F")


def test_private_signing_is_explicitly_not_supported():
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)

    with pytest.raises(ccxt.NotSupported, match="private signing"):
        exchange.sign("account/v1/balance", "private")


async def test_load_markets_fails_when_production_url_is_closed():
    exchange = BifuREST()
    try:
        with pytest.raises(ccxt.BadRequest, match="URL is not configured"):
            await exchange.load_markets()
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(
    ("response", "message"),
    [
        ([], "JSON object"),
        ({}, "missing assets or spots"),
        (
            {
                "assets": [{"asset_id": 2, "code": "USDT"}],
                "spots": [{"base_asset_id": 999, "quote_asset_id": 2}],
            },
            "unknown asset",
        ),
        (
            {
                "assets": [
                    {"asset_id": 1, "code": "BTC"},
                    {"asset_id": 2, "code": "USDT"},
                ],
                "spots": [{"base_asset_id": 1, "quote_asset_id": 2}],
            },
            "instrument id",
        ),
    ],
)
async def test_load_markets_rejects_malformed_metadata(bifu_market_server, response, message):
    bifu_market_server.response = response
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        with pytest.raises(ccxt.BadResponse, match=message):
            await exchange.load_markets()
    finally:
        await exchange.close()


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.parametrize(("status", "active"), [("HALTED", False), (None, None)])
async def test_load_markets_preserves_paused_and_unknown_status(bifu_market_server, status, active):
    spot = bifu_market_server.response["spots"][0]
    if status is None:
        del spot["status"]
    else:
        spot["status"] = status
    spot["margin"] = {"max_leverage": 10}
    exchange = BifuREST()
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        markets = await exchange.load_markets()
    finally:
        await exchange.close()

    assert markets["BTC/USDT"]["active"] is active
    assert markets["BTC/USDT"]["margin"] is False


@pytest.mark.loopback
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_readonly_inspector_retries_one_timeout(bifu_market_server):
    bifu_market_server.delay_first_seconds = 0.05
    exchange = BifuREST({"timeout": 10})
    exchange.set_sandbox_mode(True)
    exchange.urls["api"]["public"] = bifu_market_server.url
    try:
        result = await inspect_market("BTC/USDT", exchange=exchange, retry_delay=0)
    finally:
        await exchange.close()

    assert result["market_count"] == 1
    assert len(bifu_market_server.calls) == 2
