"""CCXT-compatible Bifu adapter for one caller-selected API environment."""

import hashlib
import hmac
import json

from ccxt import (
    ArgumentsRequired,
    BadRequest,
    BadResponse,
    InvalidOrder,
    NotSupported,
    OrderNotFound,
    PermissionDenied,
)
from ccxt.base.decimal_to_precision import TICK_SIZE
from ccxt.base.precise import Precise
from ccxt.base.types import Entry

from ..base import AsyncExchange
from ..registry import Extension

_DEVELOPMENT_REST_URL = "https://flame-api.bifu.dev"
_DEVELOPMENT_WS_URL = "wss://flame-api.bifu.dev"


class BifuREST(AsyncExchange):
    """Async Bifu REST adapter; endpoint methods are added one accepted slice at a time."""

    id = "bifu"
    public_get_market_v1_depth = Entry("market/v1/depth", "public", "GET", {"cost": 1})
    public_get_market_v1_klines = Entry("market/v1/klines", "public", "GET", {"cost": 1})
    public_get_market_v1_meta = Entry("market/v1/meta", "public", "GET", {"cost": 1})
    public_get_market_v1_ticker = Entry("market/v1/ticker", "public", "GET", {"cost": 1})
    public_get_market_v1_tickers = Entry("market/v1/tickers", "public", "GET", {"cost": 1})
    public_get_market_v1_trades = Entry("market/v1/trades", "public", "GET", {"cost": 1})
    private_get_spot_v1_account = Entry("spot/v1/account", "private", "GET", {"cost": 1})
    private_get_spot_v1_history_orders = Entry(
        "spot/v1/historyOrders", "private", "GET", {"cost": 1}
    )
    private_get_spot_v1_my_trades = Entry("spot/v1/myTrades", "private", "GET", {"cost": 1})
    private_get_spot_v1_open_orders = Entry("spot/v1/openOrders", "private", "GET", {"cost": 1})
    private_get_spot_v1_order_query = Entry("spot/v1/order/query", "private", "GET", {"cost": 1})
    private_post_spot_v1_order = Entry("spot/v1/order", "private", "POST", {"cost": 1})
    private_post_spot_v1_order_cancel = Entry(
        "spot/v1/order/cancel", "private", "POST", {"cost": 1}
    )

    def describe(self):
        return self.deep_extend(
            super().describe(),
            {
                "id": self.id,
                "name": "Bifu",
                "countries": [],
                "precisionMode": TICK_SIZE,
                "has": {
                    "publicAPI": True,
                    "privateAPI": True,
                    "spot": True,
                    "cancelOrder": True,
                    "createOrder": True,
                    "fetchBalance": True,
                    "fetchClosedOrders": True,
                    "fetchMarkets": True,
                    "fetchMyTrades": True,
                    "fetchOHLCV": True,
                    "fetchOpenOrders": True,
                    "fetchOrder": True,
                    "fetchOrderBook": True,
                    "fetchTicker": True,
                    "fetchTickers": True,
                    "fetchTrades": True,
                },
                "urls": {
                    # Production deliberately has no guessed endpoint. Deployment must
                    # inject confirmed production URLs into the instance configuration.
                    "api": {"public": None, "private": None, "ws": None},
                    "test": {
                        "public": _DEVELOPMENT_REST_URL,
                        "private": _DEVELOPMENT_REST_URL,
                        "ws": _DEVELOPMENT_WS_URL,
                    },
                    "www": "https://bifu.dev",
                    "doc": "https://flame-api.bifu.dev/docs",
                },
                "timeframes": {
                    period: period
                    for period in (
                        "1m",
                        "5m",
                        "15m",
                        "30m",
                        "1h",
                        "2h",
                        "4h",
                        "6h",
                        "12h",
                        "1d",
                        "1w",
                        "1M",
                    )
                },
            },
        )

    def sign(self, path, api="public", method="GET", params=None, headers=None, body=None):
        base_url = self.urls["api"][api]
        if not base_url:
            raise BadRequest("bifu API URL is not configured")
        params = dict(params or {})
        headers = dict(headers or {})
        canonical_path = "/" + path.lstrip("/")
        url = base_url.rstrip("/") + canonical_path
        body = None
        if method == "GET":
            if params:
                url += "?" + self.urlencode(dict(sorted(params.items())))
        else:
            body = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            headers["Content-Type"] = "application/json"
        if api == "private":
            self.check_required_credentials()
            timestamp = str(self.milliseconds())
            payload = "\n".join((timestamp, method.upper(), canonical_path, body or ""))
            signature = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            headers.update({"X-API-KEY": self.apiKey, "X-TS": timestamp, "X-SIGN": signature})
        return {"url": url, "method": method, "body": body, "headers": headers}

    def handle_errors(
        self,
        status_code,
        status_text,
        url,
        method,
        response_headers,
        response_body,
        response,
        request_headers,
        request_body,
    ):
        code = self.safe_integer(response, "code")
        message = self.safe_string(response, "message", "unknown error")
        if code in (3000, 3001):
            raise OrderNotFound(f"bifu {code} {message}")
        if code == 4001:
            raise PermissionDenied(f"bifu {code} {message}")
        if code == 6005:
            raise BadResponse("bifu market has no trades yet")

    async def fetch_markets(self, params=None):
        if params:
            raise NotSupported("bifu fetch_markets does not accept params")
        response = await self.public_get_market_v1_meta(params or {})
        if not isinstance(response, dict):
            raise BadResponse("bifu market metadata must be a JSON object")
        assets = response.get("assets")
        spots = response.get("spots")
        if not isinstance(assets, list) or not isinstance(spots, list):
            raise BadResponse("bifu market metadata is missing assets or spots")
        assets_by_id = {}
        for asset in assets:
            if not isinstance(asset, dict):
                raise BadResponse("bifu market metadata has an invalid asset entry")
            asset_id = self.safe_string(asset, "asset_id")
            if not asset_id:
                raise BadResponse("bifu market asset id is missing")
            assets_by_id[asset_id] = asset
        if any(not isinstance(spot, dict) for spot in spots):
            raise BadResponse("bifu market metadata has an invalid spot entry")
        self._bifu_assets_by_id = assets_by_id
        return [self.parse_market(spot, assets_by_id) for spot in spots]

    async def fetch_balance(self, params=None):
        await self.load_markets()
        response = await self.private_get_spot_v1_account(params or {})
        balances = self.safe_list(response, "balances")
        if balances is None:
            raise BadResponse("bifu account response is missing balances")
        assets = getattr(self, "_bifu_assets_by_id", {})
        result = {"info": response}
        for item in balances:
            asset_id = self.safe_string(item, "asset_id")
            asset = assets.get(asset_id)
            code = self.safe_string(asset, "code") if asset else self.safe_currency_code(asset_id)
            if not code:
                raise BadResponse("bifu balance asset id is missing")
            result[code] = {
                "free": self.safe_string(item, "available"),
                "used": self.safe_string(item, "frozen"),
            }
        return self.safe_balance(result)

    async def create_order(self, symbol, type, side, amount, price=None, params=None):
        params = dict(params or {})
        self._check_supported_params(
            "create_order", params, {"clientOrderId", "postOnly", "timeInForce"}
        )
        if not isinstance(type, str):
            raise InvalidOrder("bifu order type must be a string")
        if not isinstance(side, str):
            raise InvalidOrder("bifu order side must be a string")
        order_type = type.lower()
        order_side = side.lower()
        if order_type != "limit":
            raise NotSupported("bifu create_order currently supports limit orders only")
        if order_side not in ("buy", "sell"):
            raise InvalidOrder("bifu limit order side must be buy or sell")
        if price is None:
            raise InvalidOrder("bifu limit orders require a price")
        amount_input = self._positive_decimal_string(amount)
        price_input = self._positive_decimal_string(price)
        if amount_input is None or price_input is None:
            raise InvalidOrder("bifu order amount and price must be positive finite values")

        await self.load_markets()
        market = self.market(symbol)
        instrument_id = self.safe_integer(market, "id")
        if instrument_id is None:
            raise BadResponse("bifu market instrument id must be an integer")
        quantity = self.amount_to_precision(symbol, amount_input)
        order_price = self.price_to_precision(symbol, price_input)
        amount_limits = market["limits"]["amount"]
        cost_limits = market["limits"]["cost"]
        if amount_limits["min"] is not None and Precise.string_lt(
            quantity, str(amount_limits["min"])
        ):
            raise InvalidOrder("bifu order amount is below the market minimum amount")
        if amount_limits["max"] is not None and Precise.string_gt(
            quantity, str(amount_limits["max"])
        ):
            raise InvalidOrder("bifu order amount is above the market maximum amount")
        cost = Precise.string_mul(quantity, order_price)
        if cost_limits["min"] is not None and Precise.string_lt(cost, str(cost_limits["min"])):
            raise InvalidOrder("bifu order value is below the market minimum cost")
        if cost_limits["max"] is not None and Precise.string_gt(cost, str(cost_limits["max"])):
            raise InvalidOrder("bifu order value is above the market maximum cost")
        client_order_id = self.safe_string(params, "clientOrderId") or self.uuid16()
        time_in_force_value = params.get("timeInForce", "GTC")
        if not isinstance(time_in_force_value, str):
            raise InvalidOrder("bifu timeInForce must be a string")
        time_in_force = time_in_force_value.upper()
        if time_in_force == "PO":
            time_in_force = "POST_ONLY"
        post_only = self.safe_bool(params, "postOnly", False)
        if post_only:
            if time_in_force not in ("GTC", "POST_ONLY"):
                raise InvalidOrder("bifu postOnly conflicts with timeInForce")
            time_in_force = "POST_ONLY"
        if time_in_force not in ("GTC", "IOC", "FOK", "POST_ONLY"):
            raise InvalidOrder("bifu limit order timeInForce must be GTC, IOC, FOK, or PO")
        request = {
            "instrument_id": instrument_id,
            "side": order_side.upper(),
            "type": "LIMIT",
            "client_order_id": client_order_id,
            "time_in_force": time_in_force,
            "price": order_price,
            "qty": quantity,
        }
        response = await self.private_post_spot_v1_order(request)
        if not isinstance(response, dict):
            raise BadResponse("bifu create order response must be a JSON object")
        order_id = self.safe_string(response, "order_id")
        if not order_id:
            raise BadResponse("bifu create order response is missing order_id")
        order = self.parse_order(
            {
                "order_id": order_id,
                "client_order_id": client_order_id,
                "instrument_id": market["id"],
                "side": request["side"],
                "type": request["type"],
                "time_in_force": request["time_in_force"],
                "price": order_price,
                "orig_qty": quantity,
            },
            market,
        )
        order["info"] = response
        return order

    async def cancel_order(self, id, symbol=None, params=None):
        params = dict(params or {})
        self._check_supported_params("cancel_order", params, set())
        if symbol is None:
            raise ArgumentsRequired("bifu cancel_order requires a symbol")
        await self.load_markets()
        market = self.market(symbol)
        instrument_id = self.safe_integer(market, "id")
        if instrument_id is None:
            raise BadResponse("bifu market instrument id must be an integer")
        response = await self.private_post_spot_v1_order_cancel(
            {"instrument_id": instrument_id, "order_id": id}
        )
        if not isinstance(response, dict) or self.safe_bool(response, "accepted") is not True:
            raise BadResponse("bifu cancel order response was not accepted")
        return self.safe_order(
            {
                "id": id,
                "symbol": market["symbol"],
                "status": None,
                "info": response,
            },
            market,
        )

    async def fetch_order(self, id, symbol=None, params=None):
        params = dict(params or {})
        self._check_supported_params("fetch_order", params, set())
        await self.load_markets()
        response = await self.private_get_spot_v1_order_query({"order_id": id})
        if not isinstance(response, dict):
            raise BadResponse("bifu order response must be a JSON object")
        if self.safe_string(response, "order_id") != id:
            raise BadResponse("bifu order id does not match requested order")
        if symbol is None:
            market = self._market_from_response(response, "order")
        else:
            market = self.market(symbol)
            self._check_instrument(response, market, "order")
        return self.parse_order(response, market)

    async def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        params = dict(params or {})
        self._check_supported_params(
            "fetch_open_orders", params, {"origin", "side", "status", "type"}
        )
        await self.load_markets()
        market = self.market(symbol) if symbol is not None else None
        request = {"instrument_id": market["id"]} if market else {}
        response = await self.private_get_spot_v1_open_orders(self.extend(request, params))
        return self._parse_order_list(response, market, "open orders", since, limit)

    async def fetch_closed_orders(self, symbol=None, since=None, limit=None, params=None):
        params = dict(params or {})
        self._check_supported_params(
            "fetch_closed_orders",
            params,
            {"cursor", "end_ts_ms", "origin", "side", "status", "type"},
        )
        await self.load_markets()
        market = self.market(symbol) if symbol is not None else None
        request = {"instrument_id": market["id"]} if market else {}
        if since is not None:
            request["start_ts_ms"] = since
        if limit is not None:
            request["limit"] = limit
        response = await self.private_get_spot_v1_history_orders(self.extend(request, params))
        return self._parse_order_list(response, market, "history orders", since, limit)

    def _parse_order_list(self, response, market, label, since=None, limit=None):
        if response == {}:
            return []
        orders = self.safe_list(response, "orders")
        if orders is None:
            raise BadResponse(f"bifu {label} response is missing orders")
        parsed = []
        for order in orders:
            if not isinstance(order, dict):
                raise BadResponse(f"bifu {label} response has an invalid order entry")
            order_market = market or self._market_from_response(order, "order")
            if market:
                self._check_instrument(order, market, "order")
            parsed.append(self.parse_order(order, order_market))
        return self.filter_by_since_limit(self.sort_by(parsed, "timestamp"), since, limit)

    async def fetch_my_trades(self, symbol=None, since=None, limit=None, params=None):
        params = dict(params or {})
        self._check_supported_params("fetch_my_trades", params, {"cursor", "end_ts_ms", "order_id"})
        await self.load_markets()
        market = self.market(symbol) if symbol is not None else None
        request = {"instrument_id": market["id"]} if market else {}
        if since is not None:
            request["start_ts_ms"] = since
        if limit is not None:
            request["limit"] = limit
        response = await self.private_get_spot_v1_my_trades(self.extend(request, params))
        if response == {}:
            return []
        trades = self.safe_list(response, "trades")
        if trades is None:
            raise BadResponse("bifu private trades response is missing trades")
        parsed = []
        for trade in trades:
            if not isinstance(trade, dict):
                raise BadResponse("bifu private trades response has an invalid trade entry")
            trade_market = market or self._market_from_response(trade, "trade")
            if market:
                self._check_instrument(trade, market, "trade")
            parsed.append(self.parse_trade(trade, trade_market))
        return self.filter_by_since_limit(self.sort_by(parsed, "timestamp"), since, limit)

    def parse_order(self, order, market=None):
        timestamp = self.safe_integer(order, "created_ts")
        raw_type = self.safe_string(order, "type")
        side = self.safe_string_lower(order, "side")
        time_in_force = self.safe_string(order, "time_in_force")
        amount = self.safe_string(order, "orig_qty")
        quote_amount = self.safe_number(order, "quote_qty")
        quote_amount_market_buy = (
            raw_type == "MARKET"
            and side == "buy"
            and self.safe_number(order, "orig_qty") == 0
            and quote_amount is not None
            and quote_amount > 0
        )
        if quote_amount_market_buy:
            amount = None
        parsed = self.safe_order(
            {
                "info": order,
                "id": self.safe_string(order, "order_id"),
                "clientOrderId": self.safe_string(order, "client_order_id"),
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "lastTradeTimestamp": None,
                "lastUpdateTimestamp": self.safe_integer(order, "updated_ts"),
                "status": self.parse_order_status(self.safe_string(order, "status")),
                "symbol": market["symbol"] if market else None,
                "type": self.parse_order_type(raw_type),
                "timeInForce": "PO" if time_in_force == "POST_ONLY" else time_in_force,
                "postOnly": time_in_force == "POST_ONLY",
                "side": side,
                "price": self.safe_string(order, "price"),
                "triggerPrice": None,
                "cost": self.safe_string(order, "cum_quote"),
                "average": None,
                "amount": amount,
                "filled": self.safe_string(order, "filled_qty"),
                "remaining": None,
                "trades": None,
                "fee": self._parse_fee(order, "cum_fee"),
                "reduceOnly": None,
            },
            market,
        )
        # CCXT's safe_order derives amount from filled for closed orders. Bifu's
        # quote-amount market buys do not expose the requested base amount, so keep
        # that value unknown instead of turning the filled quantity into the request.
        if quote_amount_market_buy:
            parsed["amount"] = None
            parsed["remaining"] = None
        return parsed

    def parse_order_status(self, status):
        statuses = {
            "NEW": "open",
            "PENDING": "open",
            "OPEN": "open",
            "PARTIALLY_FILLED": "open",
            "CANCELING": "open",
            "FILLED": "closed",
            "CANCELED": "canceled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }
        return self.safe_string(statuses, status)

    def parse_order_type(self, order_type):
        types = {
            "LIMIT": "limit",
            "ICE_LIMIT": "limit",
            "MARKET": "market",
            "SANDBOX_MARKET": "market",
        }
        return self.safe_string(types, order_type, order_type.lower() if order_type else None)

    def _check_supported_params(self, method_name, params, allowed):
        unsupported = sorted(set(params) - allowed)
        if unsupported:
            names = ", ".join(unsupported)
            raise NotSupported(f"bifu {method_name} does not accept params: {names}")

    @staticmethod
    def _positive_decimal_string(value):
        try:
            text = str(value)
            return text if Precise.string_gt(text, "0") else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _parse_fee(self, response, cost_key):
        fee_cost = self.safe_number(response, cost_key)
        if fee_cost is None:
            return None
        fee_asset_id = self.safe_string(response, "fee_asset_id")
        assets = getattr(self, "_bifu_assets_by_id", {})
        fee_asset = assets.get(fee_asset_id)
        fee_currency = (
            self.safe_string(fee_asset, "code")
            if fee_asset
            else self.safe_currency_code(fee_asset_id)
        )
        return {"cost": fee_cost, "currency": fee_currency}

    async def fetch_ticker(self, symbol, params=None):
        if params:
            raise NotSupported("bifu fetch_ticker does not accept params")
        await self.load_markets()
        market = self.market(symbol)
        response = await self.public_get_market_v1_ticker({"instrument_id": market["id"]})
        if not isinstance(response, dict):
            raise BadResponse("bifu ticker must be a JSON object")
        if self.safe_string(response, "instrument_id") != market["id"]:
            raise BadResponse("bifu ticker instrument id does not match requested market")
        return self.parse_ticker(response, market)

    async def fetch_tickers(self, symbols=None, params=None):
        params = dict(params or {})
        response_type = params.pop("type", "FULL")
        if response_type != "FULL":
            raise NotSupported("bifu unified fetch_tickers only supports FULL responses")
        await self.load_markets()
        symbols = self.market_symbols(symbols)
        response = await self.public_get_market_v1_tickers(self.extend({"type": "FULL"}, params))
        tickers = self.safe_list(response, "tickers")
        if tickers is None:
            raise BadResponse("bifu tickers response is missing tickers")
        requested_ids = (
            {self.market(symbol)["id"] for symbol in symbols} if symbols is not None else None
        )
        parsed = []
        for raw_ticker in tickers:
            if (
                requested_ids is not None
                and self.safe_string(raw_ticker, "instrument_id") not in requested_ids
            ):
                continue
            market = self._market_from_response(raw_ticker, "ticker")
            parsed.append(self.parse_ticker(raw_ticker, market))
        return self.filter_by_array_tickers(parsed, "symbol", symbols)

    def parse_ticker(self, response, market=None):
        timestamp = self.safe_integer(response, "ts")
        if timestamp is None:
            raise BadResponse("bifu ticker timestamp is invalid")
        ticker = self.safe_ticker(
            {
                "symbol": market["symbol"] if market else None,
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "open": self.safe_number(response, "open_price"),
                "high": self.safe_number(response, "high_price"),
                "low": self.safe_number(response, "low_price"),
                "last": self.safe_number(response, "last_price"),
                "change": self.safe_number(response, "price_change"),
                "percentage": self.safe_number(response, "price_change_percent"),
                "baseVolume": self.safe_number(response, "volume"),
                "quoteVolume": self.safe_number(response, "quote_volume"),
                "info": response,
            },
            market,
        )
        # Bifu explicitly uses open=0 with an empty percentage when no percentage can
        # be computed. CCXT's generic safe_ticker omits zero open and derives values,
        # so restore exchange-provided fields and remove the unreported average.
        ticker["open"] = self.safe_number(response, "open_price")
        ticker["percentage"] = self.safe_number(response, "price_change_percent")
        ticker["average"] = None
        return ticker

    async def fetch_order_book(self, symbol, limit=None, params=None):
        await self.load_markets()
        market = self.market(symbol)
        request = {"instrument_id": market["id"]}
        if limit is not None:
            request["limit"] = limit
        response = await self.public_get_market_v1_depth(self.extend(request, params or {}))
        if not isinstance(response, dict):
            raise BadResponse("bifu order book must be a JSON object")
        self._check_instrument(response, market, "order book")
        timestamp = self.safe_integer(response, "book_time")
        order_book = self.parse_order_book(
            response,
            market["symbol"],
            timestamp,
            "bids",
            "asks",
            "price",
            "qty",
        )
        order_book["nonce"] = self.safe_integer(response, "last_id")
        return order_book

    async def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None, params=None):
        await self.load_markets()
        market = self.market(symbol)
        if timeframe not in self.timeframes:
            raise NotSupported(f"bifu does not support timeframe {timeframe!r}")
        request = {"instrument_id": market["id"], "period": self.timeframes[timeframe]}
        if limit is not None:
            request["limit"] = limit
        response = await self.public_get_market_v1_klines(self.extend(request, params or {}))
        candles = self.safe_list(response, "klines")
        if candles is None:
            raise BadResponse("bifu klines response is missing klines")
        for candle in candles:
            self._check_instrument(candle, market, "kline")
        return self.parse_ohlcvs(candles, market, timeframe, since, limit)

    def parse_ohlcv(self, ohlcv, market=None):
        return [
            self.safe_integer(ohlcv, "open_time"),
            self.safe_number(ohlcv, "open"),
            self.safe_number(ohlcv, "high"),
            self.safe_number(ohlcv, "low"),
            self.safe_number(ohlcv, "close"),
            self.safe_number(ohlcv, "volume"),
        ]

    async def fetch_trades(self, symbol, since=None, limit=None, params=None):
        await self.load_markets()
        market = self.market(symbol)
        request = {"instrument_id": market["id"]}
        if limit is not None:
            request["limit"] = limit
        response = await self.public_get_market_v1_trades(self.extend(request, params or {}))
        trades = self.safe_list(response, "trades")
        if trades is None:
            raise BadResponse("bifu trades response is missing trades")
        for trade in trades:
            self._check_instrument(trade, market, "trade")
        return self.parse_trades(trades, market, since, limit)

    def parse_trade(self, trade, market=None):
        if "trade_id" in trade:
            timestamp = self.safe_integer(trade, "ts_ms")
            is_maker = self.safe_bool(trade, "is_maker")
            return self.safe_trade(
                {
                    "id": self.safe_string(trade, "trade_id"),
                    "order": self.safe_string(trade, "order_id"),
                    "timestamp": timestamp,
                    "datetime": self.iso8601(timestamp),
                    "symbol": market["symbol"] if market else None,
                    "type": None,
                    "side": self.safe_string_lower(trade, "side"),
                    "takerOrMaker": (
                        "maker" if is_maker else "taker" if is_maker is not None else None
                    ),
                    "price": self.safe_number(trade, "price"),
                    "amount": self.safe_number(trade, "qty"),
                    "cost": None,
                    "fee": self._parse_fee(trade, "fee"),
                    "info": trade,
                },
                market,
            )
        timestamp = self.safe_integer(trade, "ts")
        return self.safe_trade(
            {
                "id": None,
                "order": None,
                "timestamp": timestamp,
                "datetime": self.iso8601(timestamp),
                "symbol": market["symbol"] if market else None,
                "type": None,
                "side": self.safe_string_lower(trade, "taker_side"),
                "takerOrMaker": "taker",
                "price": self.safe_number(trade, "price"),
                "amount": self.safe_number(trade, "qty"),
                "cost": None,
                "fee": None,
                "info": trade,
            },
            market,
        )

    def _market_from_response(self, response, label):
        market_id = self.safe_string(response, "instrument_id")
        markets = self.markets_by_id.get(market_id) if self.markets_by_id else None
        if not markets:
            raise BadResponse(f"bifu {label} references an unknown market")
        return markets[0]

    def _check_instrument(self, response, market, label):
        if self.safe_string(response, "instrument_id") != market["id"]:
            raise BadResponse(f"bifu {label} instrument id does not match requested market")

    def parse_market(self, market, assets_by_id):
        base_id = str(market.get("base_asset_id"))
        quote_id = str(market.get("quote_asset_id"))
        base = assets_by_id.get(base_id)
        quote = assets_by_id.get(quote_id)
        if base is None or quote is None:
            raise BadResponse("bifu market references an unknown asset")
        base_code = self.safe_string(base, "code")
        quote_code = self.safe_string(quote, "code")
        if not base_code or not quote_code:
            raise BadResponse("bifu market asset code is missing")
        instrument_id = self.safe_string(market, "instrument_id")
        if not instrument_id:
            raise BadResponse("bifu market instrument id is missing")
        rules = self.safe_dict(market, "rules", {})
        status = self.safe_string(market, "status")
        active = None if status is None else status == "TRADING"
        return {
            "id": instrument_id,
            "symbol": base_code + "/" + quote_code,
            "base": base_code,
            "quote": quote_code,
            "baseId": base_id,
            "quoteId": quote_id,
            "settle": None,
            "settleId": None,
            "type": "spot",
            "spot": True,
            # Raw metadata includes a margin object for some spots, but that alone does
            # not prove a usable margin-trading contract or implemented account methods.
            "margin": False,
            "swap": False,
            "future": False,
            "option": False,
            "contract": False,
            "contractSize": None,
            "linear": None,
            "inverse": None,
            "active": active,
            "taker": self.safe_number(market, "taker_fee_rate"),
            "maker": self.safe_number(market, "maker_fee_rate"),
            "percentage": True,
            "precision": {
                "amount": self.safe_number(rules, "qty_step"),
                "price": self.safe_number(rules, "price_tick"),
            },
            "limits": {
                "amount": {
                    "min": self.safe_number(rules, "min_qty"),
                    "max": self.safe_number(rules, "max_qty"),
                },
                "price": {"min": None, "max": None},
                "cost": {
                    "min": self.safe_number(rules, "min_notional"),
                    "max": self.safe_number(rules, "max_notional"),
                },
            },
            "info": market,
        }


BIFU_EXTENSION = Extension("bifu", rest=BifuREST)

__all__ = ["BIFU_EXTENSION", "BifuREST"]
