"""Executable fictitious venue. Loopback only; never a real exchange implementation.

REST and WebSocket share CCXT parsing, market metadata and the official async transport.
Protocol and limits: docs/reference-protocol.md.
"""

import hashlib
import hmac
import json
import math
from urllib.parse import urlencode, urlsplit

from ccxt import (
    AuthenticationError,
    BadRequest,
    BadResponse,
    BaseError,
    InvalidNonce,
    InvalidOrder,
    NotSupported,
    OrderNotFound,
    RateLimitExceeded,
)
from ccxt.async_support.base.ws.cache import ArrayCacheBySymbolById
from ccxt.base.decimal_to_precision import TICK_SIZE
from ccxt.base.types import Entry

from ccxt_cm import AsyncExchange, Extension, SpecialMethod


class ReferenceREST(AsyncExchange):
    id = "cm_reference"
    cm_special_methods = (
        SpecialMethod(
            "fetch_account_limits",
            "Read fixture account request quota",
            "docs/reference-protocol.md",
            private=True,
            returns="raw quota object",
        ),
    )
    public_get_markets = Entry("markets", "public", "GET", {"cost": 1})
    private_get_account_limits = Entry("account/limits", "private", "GET", {"cost": 1})

    def describe(self):
        return self.deep_extend(
            super().describe(),
            {
                "id": self.id,
                "name": "CCXT_CM loopback reference (not a real exchange)",
                "rateLimit": 10,
                "precisionMode": TICK_SIZE,
                "has": {
                    "publicAPI": True,
                    "privateAPI": True,
                    "spot": True,
                    "fetchMarkets": True,
                    "fetchTicker": True,
                    "fetchOrderBook": True,
                    "fetchTrades": True,
                    "fetchBalance": True,
                    "fetchOrder": True,
                    "fetchOpenOrders": True,
                    "createOrder": True,
                    "cancelOrder": True,
                },
                "urls": {"api": {"public": "http://127.0.0.1:1", "private": "http://127.0.0.1:1"}},
                "requiredCredentials": {"apiKey": True, "secret": True},
            },
        )

    @staticmethod
    def _loopback(url):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "ws")
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise BadRequest("Reference transport accepts only explicit http/ws://127.0.0.1 URLs")
        return url.rstrip("/")

    def sign(self, path, api="public", method="GET", params=None, headers=None, body=None):
        url = self._loopback(self.urls["api"][api]) + "/" + path
        params = dict(params or {})
        headers = dict(headers or {})
        body = None
        if method == "GET":
            query = urlencode(sorted(params.items()))
            if query:
                url += "?" + query
        else:
            body = json.dumps(params, sort_keys=True, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        if api == "private":
            self.check_required_credentials()
            nonce = str(self.nonce())
            target = urlsplit(url)
            signing_path = target.path + ("?" + target.query if target.query else "")
            payload = nonce + method + signing_path + (body or "")
            headers.update(
                {
                    "X-Key": self.apiKey,
                    "X-Nonce": nonce,
                    "X-Signature": hmac.new(
                        self.secret.encode(), payload.encode(), hashlib.sha256
                    ).hexdigest(),
                }
            )
        return {"url": url, "method": method, "body": body, "headers": headers}

    def handle_errors(
        self, code, reason, url, method, headers, body, response, req_headers, req_body
    ):
        if not isinstance(response, dict):
            raise BadResponse("Reference expected a JSON object")
        error = response.get("error")
        if error:
            errors = {
                "AUTH": AuthenticationError,
                "ORDER_NOT_FOUND": OrderNotFound,
                "RATE_LIMIT": RateLimitExceeded,
                "INVALID_ORDER": InvalidOrder,
            }
            # Do not echo request, credentials or raw response into exception text.
            raise errors.get(error, BadResponse)(f"{self.id}: {error}")
        if "data" not in response:
            raise BadResponse("Reference response is missing data")

    async def fetch_markets(self, params=None):
        response = await self.public_get_markets(params or {})
        return [self.parse_market(item) for item in response["data"]]

    def parse_market(self, item):
        return {
            "id": item["id"],
            "symbol": item["base"] + "/" + item["quote"],
            "base": item["base"],
            "quote": item["quote"],
            "baseId": item["base"],
            "quoteId": item["quote"],
            "settle": None,
            "settleId": None,
            "type": "spot",
            "spot": True,
            "margin": False,
            "swap": False,
            "future": False,
            "option": False,
            "contract": False,
            "contractSize": None,
            "linear": None,
            "inverse": None,
            "active": item.get("active"),
            "precision": {
                "price": self.safe_number(item, "tick"),
                "amount": self.safe_number(item, "step"),
            },
            "limits": {
                "amount": {"min": self.safe_number(item, "minAmount"), "max": None},
                "price": {"min": None, "max": None},
                "cost": {"min": self.safe_number(item, "minCost"), "max": None},
            },
            "info": item,
        }

    async def _market_request(self, path, symbol, params=None):
        await self.load_markets()
        market = self.market(symbol)
        response = await self.request(
            path, "public", "GET", {**(params or {}), "symbol": market["id"]}
        )
        return response["data"], market

    def parse_ticker(self, item, market=None):
        market = market or self.safe_market(item["symbol"])
        timestamp = self.safe_integer(item, "time")
        return self.safe_ticker(
            {
                "symbol": market["symbol"],
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "bid": self.safe_number(item, "bid"),
                "ask": self.safe_number(item, "ask"),
                "last": self.safe_number(item, "last"),
                "info": item,
            },
            market,
        )

    async def fetch_ticker(self, symbol, params=None):
        data, market = await self._market_request("ticker", symbol, params)
        return self.parse_ticker(data, market)

    async def fetch_order_book(self, symbol, limit=None, params=None):
        data, market = await self._market_request("book", symbol, params)
        result = self.parse_order_book(data, market["symbol"], self.safe_integer(data, "time"))
        result["nonce"] = self.safe_integer(data, "sequence")
        if limit is not None:
            if limit <= 0:
                raise BadRequest("limit must be positive")
            result["bids"], result["asks"] = result["bids"][:limit], result["asks"][:limit]
        return result

    def parse_trade(self, item, market=None):
        market = market or self.safe_market(item["symbol"])
        timestamp = self.safe_integer(item, "time")
        return self.safe_trade(
            {
                "id": self.safe_string(item, "id"),
                "symbol": market["symbol"],
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "side": self.safe_string(item, "side"),
                "price": self.safe_number(item, "price"),
                "amount": self.safe_number(item, "amount"),
                "info": item,
            },
            market,
        )

    async def fetch_trades(self, symbol, since=None, limit=None, params=None):
        data, market = await self._market_request("trades", symbol, params)
        return self.parse_trades(data, market, since, limit)

    def parse_balance(self, data):
        result = {"info": data}
        for code, account in data.items():
            result[code] = {
                "free": self.safe_number(account, "free"),
                "used": self.safe_number(account, "used"),
                "total": self.safe_number(account, "total"),
            }
        return self.safe_balance(result)

    async def fetch_balance(self, params=None):
        response = await self.request("balance", "private", "GET", params or {})
        return self.parse_balance(response["data"])

    def parse_order(self, item, market=None):
        market = market or self.safe_market(item.get("symbol"))
        timestamp = self.safe_integer(item, "time")
        return self.safe_order(
            {
                "id": self.safe_string(item, "id"),
                "clientOrderId": self.safe_string(item, "clientOrderId"),
                "symbol": market["symbol"],
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "type": self.safe_string(item, "type"),
                "side": self.safe_string(item, "side"),
                "price": self.safe_number(item, "price"),
                "amount": self.safe_number(item, "amount"),
                "filled": self.safe_number(item, "filled"),
                "remaining": self.safe_number(item, "remaining"),
                "average": self.safe_number(item, "average"),
                "cost": self.safe_number(item, "cost"),
                "status": {
                    "NEW": "open",
                    "FILLED": "closed",
                    "CANCELED": "canceled",
                    "PARTIAL": "open",
                    "REJECTED": "rejected",
                    "EXPIRED": "expired",
                }.get(item.get("state")),
                "info": item,
            },
            market,
        )

    async def create_order(self, symbol, type, side, amount, price=None, params=None):
        # Standard CCXT order: symbol, type, side, amount, price, params.
        if type != "limit":
            raise NotSupported("Reference implements limit orders only")
        if side not in ("buy", "sell") or price is None:
            raise InvalidOrder("Limit orders require buy/sell and price")
        if not all(math.isfinite(float(v)) and float(v) > 0 for v in (amount, price)):
            raise InvalidOrder("Amount and price must be positive finite values")
        params = dict(params or {})
        if set(params) - {"clientOrderId"}:
            raise NotSupported("Reference accepts only clientOrderId as an extra order parameter")
        await self.load_markets()
        market = self.market(symbol)
        request = {
            **params,
            "symbol": market["id"],
            "type": type,
            "side": side,
            "amount": self.amount_to_precision(symbol, amount),
            "price": self.price_to_precision(symbol, price),
        }
        if float(request["amount"]) < market["limits"]["amount"]["min"]:
            raise InvalidOrder("Amount below market minimum")
        if float(request["amount"]) * float(request["price"]) < market["limits"]["cost"]["min"]:
            raise InvalidOrder("Cost below market minimum")
        response = await self.request("order", "private", "POST", request)
        return self.parse_order(response["data"], market)

    async def fetch_order(self, id, symbol=None, params=None):
        await self.load_markets()
        response = await self.request("order", "private", "GET", {**(params or {}), "id": id})
        return self.parse_order(response["data"], self.market(symbol) if symbol else None)

    async def cancel_order(self, id, symbol=None, params=None):
        await self.load_markets()
        response = await self.request("cancel", "private", "POST", {**(params or {}), "id": id})
        # ACK-only cancellation is not proof of canceled state.
        return self.parse_order(response["data"], self.market(symbol) if symbol else None)

    async def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        await self.load_markets()
        request = dict(params or {})
        market = self.market(symbol) if symbol else None
        if market:
            request["symbol"] = market["id"]
        response = await self.request("orders", "private", "GET", request)
        return self.parse_orders(response["data"], market, since, limit)

    async def fetch_account_limits(self, params=None):
        response = await self.private_get_account_limits(params or {})
        return response["data"]


class ReferencePro(ReferenceREST):
    def describe(self):
        return self.deep_extend(
            super().describe(),
            {
                "has": {
                    "ws": True,
                    "watchTicker": True,
                    "watchOrderBook": True,
                    "watchOrders": True,
                    "watchBalance": True,
                },
                "urls": {"api": {"ws": "ws://127.0.0.1:1/ws"}},
                "options": {"ordersLimit": 100},
                "streaming": {"keepAlive": 15000},
            },
        )

    async def _subscribe(self, channel, symbol=None, private=False):
        await self.load_markets()
        url = self._loopback(self.urls["api"]["ws"])
        client = self.clients.get(url)
        if private and not (client and client.subscriptions.get("auth_ok")):
            self.check_required_credentials()
            nonce = str(self.nonce())
            signature = hmac.new(self.secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
            await self.watch(
                url,
                "authenticated",
                {
                    "op": "login",
                    "key": self.apiKey,
                    "nonce": nonce,
                    "signature": signature,
                },
                "authenticated",
            )
        market_id = self.market(symbol)["id"] if symbol else None
        message_hash = channel + (":" + market_id if market_id else "")
        return await self.watch(
            url,
            message_hash,
            {
                "op": "subscribe",
                "channel": channel,
                "symbol": market_id,
            },
            message_hash,
        )

    async def watch_ticker(self, symbol, params=None):
        self._no_params(params)
        return await self._subscribe("ticker", symbol)

    async def watch_order_book(self, symbol, limit=None, params=None):
        self._no_params(params)
        if limit is not None and limit <= 0:
            raise BadRequest("limit must be positive")
        book = await self._subscribe("book", symbol)
        # Keep the complete cache even when this caller requests a shallow view.
        result = dict(book)
        result["bids"] = list(book["bids"])[:limit]
        result["asks"] = list(book["asks"])[:limit]
        return result

    async def watch_orders(self, symbol=None, since=None, limit=None, params=None):
        self._no_params(params)
        if symbol:
            await self.load_markets()
            symbol = self.market(symbol)["symbol"]
        orders = await self._subscribe("orders", private=True)
        if self.newUpdates:
            limit = orders.get_limit(symbol, limit)
        return self.filter_by_symbol_since_limit(orders, symbol, since, limit)

    async def watch_balance(self, params=None):
        self._no_params(params)
        return await self._subscribe("balance", private=True)

    @staticmethod
    def _no_params(params):
        if params:
            raise NotSupported("Reference WS has no additional params")

    def handle_message(self, client, message):
        try:
            if not isinstance(message, dict):
                raise BadResponse("Expected a JSON WebSocket object")
            if message.get("event") == "login":
                if message.get("ok") is not True:
                    client.subscriptions.pop("authenticated", None)
                    raise AuthenticationError("Reference WebSocket authentication failed")
                client.subscriptions["auth_ok"] = True
                client.resolve(True, "authenticated")
                return
            if message.get("event") == "subscribed":
                return
            channel, data = message["channel"], message["data"]
            if channel in ("orders", "balance") and not client.subscriptions.get("auth_ok"):
                raise AuthenticationError("Unauthenticated private message")
            if channel == "ticker":
                ticker = self.parse_ticker(data)
                self.tickers[ticker["symbol"]] = ticker
                client.resolve(ticker, "ticker:" + data["symbol"])
            elif channel == "book":
                self._handle_book(client, data)
            elif channel == "orders":
                if self.orders is None:
                    self.orders = ArrayCacheBySymbolById(self.options["ordersLimit"])
                for item in data:
                    symbol = self.safe_market(item["symbol"])["symbol"]
                    previous = self.orders.hashmap.get(symbol, {}).get(str(item["id"]), {})
                    raw = {**previous.get("info", {}), **item}
                    self.orders.append(self.parse_order(raw))
                client.resolve(self.orders, "orders")
            elif channel == "balance":
                if message.get("delta") and not self.balance:
                    raise InvalidNonce("Balance delta received before initial snapshot")
                previous = self.balance.get("info", {}) if message.get("delta") else {}
                merged = {code: dict(values) for code, values in previous.items()}
                for code, values in data.items():
                    merged[code] = {**merged.get(code, {}), **values}
                    # A delta may change free/used: never carry forward a stale total.
                    if "total" not in values and ("free" in values or "used" in values):
                        merged[code].pop("total", None)
                self.balance = self.parse_balance(merged)
                client.resolve(self.balance, "balance")
            else:
                raise BadResponse("Unknown reference WebSocket channel")
        except Exception as error:
            self._reset_stream_state()
            client.subscriptions.clear()
            if not isinstance(error, BaseError):
                error = BadResponse("Malformed reference WebSocket payload")
            client.reject(error)

    def _handle_book(self, client, data):
        market = self.safe_market(data["symbol"])
        symbol, sequence = market["symbol"], data["sequence"]
        message_hash = "book:" + data["symbol"]
        current = self.orderbooks.get(symbol)
        if data["kind"] == "snapshot":
            parsed = self.parse_order_book(data, symbol, data.get("time"))
            parsed["nonce"] = sequence
            self.orderbooks[symbol] = self.order_book(parsed)
        elif data["kind"] == "delta":
            if current is not None and sequence <= current["nonce"]:
                return  # duplicate/old updates must not roll the book back
            if current is None or sequence != current["nonce"] + 1:
                self.orderbooks.pop(symbol, None)
                client.subscriptions.pop(message_hash, None)
                client.reject(
                    InvalidNonce("Order book gap; a new subscription snapshot is required"),
                    message_hash,
                )
                return
            for side in ("bids", "asks"):
                self.handle_deltas(current[side], data.get(side, []))
            current["nonce"] = sequence
            current["timestamp"] = data.get("time")
            current["datetime"] = self.iso8601(data.get("time"))
        else:
            raise BadResponse("Unknown order book message kind")
        client.resolve(self.orderbooks[symbol], message_hash)

    def handle_delta(self, bookside, delta):
        bookside.store(float(delta[0]), float(delta[1]))

    def _reset_stream_state(self):
        self.orderbooks.clear()
        self.tickers.clear()
        self.orders = None
        self.balance = {}

    def on_close(self, client, error):
        self._reset_stream_state()
        super().on_close(client, error)

    def on_error(self, client, error):
        self._reset_stream_state()
        super().on_error(client, error)


EXTENSION = Extension("cm_reference", rest=ReferenceREST, pro=ReferencePro)
