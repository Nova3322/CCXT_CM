"""Copy into an extension package; do not enable capabilities before adding tests."""

from ccxt import NotSupported

from ccxt_cm import AsyncExchange, Extension


class TargetREST(AsyncExchange):
    id = "target"

    def describe(self):
        return self.deep_extend(
            super().describe(),
            {
                "id": self.id,
                "name": "TARGET (not implemented)",
                "urls": {"api": {}},
                "has": {"fetchMarkets": False},
            },
        )

    async def fetch_markets(self, params=None):
        raise NotSupported("target fetchMarkets has not been implemented or validated")


class TargetPro(TargetREST):
    # Extend this class with official watch/client/cache primitives.
    # REST reuse is inherited. No REST polling masquerading as watch_*.
    pass


# Add pro=TargetPro only when real WebSocket capabilities pass the contract suite.
EXTENSION = Extension("target", rest=TargetREST)
