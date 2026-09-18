"""Bifu adapter foundation with fail-closed production configuration.

This stage intentionally implements only construction and environment isolation.
Capabilities remain disabled until their protocol behavior has its own tests.
"""

from ccxt import BadRequest

from ccxt_cm import AsyncExchange, Extension

_DEVELOPMENT_REST_URL = "https://flame-api.bifu.dev"
_DEVELOPMENT_WS_URL = "wss://flame-api.bifu.dev"


class BifuREST(AsyncExchange):
    """Async Bifu REST adapter; endpoint methods are added one accepted slice at a time."""

    id = "bifu"

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


BIFU_EXTENSION = Extension("bifu", rest=BifuREST)

__all__ = ["BIFU_EXTENSION", "BifuREST"]
