"""Bifu adapter foundation with fail-closed production configuration.

This stage intentionally implements only construction and environment isolation.
Capabilities remain disabled until their protocol behavior has its own tests.
"""

from ccxt import BadRequest, BadResponse, NotSupported
from ccxt.base.decimal_to_precision import TICK_SIZE
from ccxt.base.types import Entry

from ccxt_cm import AsyncExchange, Extension

_DEVELOPMENT_REST_URL = "https://flame-api.bifu.dev"
_DEVELOPMENT_WS_URL = "wss://flame-api.bifu.dev"


class BifuREST(AsyncExchange):
    """Async Bifu REST adapter; endpoint methods are added one accepted slice at a time."""

    id = "bifu"
    public_get_market_v1_meta = Entry("market/v1/meta", "public", "GET", {"cost": 1})

    def __init__(self, config=None):
        super().__init__(config or {})
        production = self.urls["api"]
        values = tuple(production.get(name) for name in ("public", "private", "ws"))
        if any(values):
            raise BadRequest(
                "bifu production URLs are disabled until test environment acceptance is complete"
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
                    "spot": True,
                    "fetchMarkets": True,
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
            },
        )

    def sign(self, path, api="public", method="GET", params=None, headers=None, body=None):
        if api != "public":
            raise NotSupported("bifu private signing is not implemented")
        base_url = self.urls["api"][api]
        if not base_url:
            raise BadRequest("bifu API URL is not configured")
        params = dict(params or {})
        url = base_url.rstrip("/") + "/" + path
        if params:
            url += "?" + self.urlencode(dict(sorted(params.items())))
        return {"url": url, "method": method, "body": None, "headers": headers}

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
        assets_by_id = {str(asset.get("asset_id")): asset for asset in assets}
        return [self.parse_market(spot, assets_by_id) for spot in spots]

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
