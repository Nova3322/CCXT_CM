"""Synthetic data only. No credentials, production hosts or source archives in tests."""

import copy
import hashlib
import hmac
from types import SimpleNamespace

import pytest
from aiohttp import web

from examples.reference_exchange import ReferencePro, ReferenceREST

MARKET = {
    "id": "BTC_USDT",
    "base": "BTC",
    "quote": "USDT",
    "tick": "0.1",
    "step": "0.001",
    "minAmount": "0.001",
    "minCost": "1",
    "active": True,
}
TICKER = {"symbol": "BTC_USDT", "time": 1700000000000, "bid": "100", "ask": "102", "last": "101"}
BOOK = {
    "symbol": "BTC_USDT",
    "time": 1700000000000,
    "kind": "snapshot",
    "sequence": 10,
    "bids": [["100", "2"], ["99", "3"]],
    "asks": [["102", "4"], ["103", "5"]],
}
ORDER = {
    "id": "1",
    "symbol": "BTC_USDT",
    "time": 1700000000000,
    "type": "limit",
    "side": "buy",
    "amount": "1",
    "price": "100",
    "filled": "0",
    "state": "NEW",
    "clientOrderId": "fixture-1",
}
BALANCE = {"USDT": {"free": "1000", "used": "100"}, "BTC": {"free": "2", "used": "0"}}


@pytest.fixture
async def rest():
    exchange = ReferenceREST({"apiKey": "fixture-key", "secret": "fixture-secret"})
    exchange.set_markets([exchange.parse_market(copy.deepcopy(MARKET))])
    yield exchange
    await exchange.close()


@pytest.fixture
async def pro():
    exchange = ReferencePro({"apiKey": "fixture-key", "secret": "fixture-secret"})
    exchange.set_markets([exchange.parse_market(copy.deepcopy(MARKET))])
    yield exchange
    await exchange.close()


@pytest.fixture
async def venue(unused_tcp_port):
    """Real aiohttp protocol peer restricted by pytest-socket to 127.0.0.1."""
    state = SimpleNamespace(calls=[], clients=[], subscriptions=[], orders={}, sequence=0)

    async def endpoint(request):
        raw = await request.text()
        state.calls.append((request.method, request.path, dict(request.query), raw))
        private = request.path in {"/order", "/orders", "/cancel", "/balance", "/account/limits"}
        if private:
            payload = request.headers.get("X-Nonce", "") + request.method + request.raw_path + raw
            signature = hmac.new(b"fixture-secret", payload.encode(), hashlib.sha256).hexdigest()
            if request.headers.get("X-Key") != "fixture-key" or not hmac.compare_digest(
                request.headers.get("X-Signature", ""), signature
            ):
                return web.json_response({"error": "AUTH"}, status=401)
        if request.path == "/markets":
            data = [MARKET]
        elif request.path == "/ticker":
            data = TICKER
        elif request.path == "/book":
            data = BOOK
        elif request.path == "/trades":
            data = [
                {
                    "id": "trade-1",
                    "symbol": "BTC_USDT",
                    "time": 1700000000000,
                    "price": "100",
                    "amount": "2",
                    "side": "buy",
                }
            ]
        elif request.path == "/balance":
            data = BALANCE
        elif request.path == "/account/limits":
            data = {"requestsPerMinute": 60}
        elif request.path == "/order" and request.method == "POST":
            state.sequence += 1
            data = {**await request.json(), "id": str(state.sequence), "time": 1700000000000}
            state.orders[data["id"]] = {**data, "state": "NEW", "filled": "0"}
            # Only ACK on placement: neither status nor fills can be inferred.
        elif request.path == "/order":
            data = state.orders.get(request.query.get("id"))
            if data is None:
                return web.json_response({"error": "ORDER_NOT_FOUND"}, status=404)
        elif request.path == "/cancel":
            item = await request.json()
            if item["id"] not in state.orders:
                return web.json_response({"error": "ORDER_NOT_FOUND"}, status=404)
            state.orders[item["id"]]["state"] = "CANCELED"
            data = {"id": item["id"], "symbol": "BTC_USDT"}  # ACK only
        elif request.path == "/orders":
            data = [item for item in state.orders.values() if item["state"] == "NEW"]
        else:
            return web.json_response({"error": "UNSUPPORTED"}, status=400)
        return web.json_response({"data": data})

    async def websocket(request):
        ws = web.WebSocketResponse(heartbeat=15)
        await ws.prepare(request)
        state.clients.append(ws)
        authenticated = False
        async for message in ws:
            if message.type != web.WSMsgType.TEXT:
                continue
            event = message.json()
            if event["op"] == "login":
                expected = hmac.new(
                    b"fixture-secret", event["nonce"].encode(), hashlib.sha256
                ).hexdigest()
                authenticated = event["key"] == "fixture-key" and hmac.compare_digest(
                    event["signature"], expected
                )
                await ws.send_json({"event": "login", "ok": authenticated})
                continue
            channel = event["channel"]
            if channel in ("orders", "balance") and not authenticated:
                await ws.send_json({"event": "login", "ok": False})
                continue
            state.subscriptions.append(event)
            data = {"ticker": TICKER, "book": BOOK, "orders": [ORDER], "balance": BALANCE}[channel]
            await ws.send_json({"channel": channel, "data": data})
        return ws

    app = web.Application()
    app.router.add_get("/ws", websocket)
    app.router.add_route("*", "/{path:.*}", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    state.config = {
        "apiKey": "fixture-key",
        "secret": "fixture-secret",
        "timeout": 1000,
        "urls": {
            "api": {
                "public": f"http://127.0.0.1:{unused_tcp_port}",
                "private": f"http://127.0.0.1:{unused_tcp_port}",
                "ws": f"ws://127.0.0.1:{unused_tcp_port}/ws",
            }
        },
    }
    try:
        yield state
    finally:
        for ws in state.clients:
            await ws.close()
        await runner.cleanup()
