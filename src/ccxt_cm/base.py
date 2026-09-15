"""Optional bases for new venues. Existing official adapters should be subclassed directly."""

import ccxt
from ccxt.async_support.base.exchange import Exchange as UpstreamAsyncExchange


class _ExplicitCapabilities:
    def describe(self):
        description = super().describe()
        # Upstream's generic Exchange advertises some methods that a new venue may not implement.
        description["has"] = dict.fromkeys(description["has"], False)
        description["has"]["ws"] = False
        description.setdefault("options", {})["maxRetriesOnFailure"] = 0
        return description


class Exchange(_ExplicitCapabilities, ccxt.Exchange):
    """New synchronous venue; enable only capabilities backed by implementation and tests."""


class AsyncExchange(_ExplicitCapabilities, UpstreamAsyncExchange):
    """New async REST venue; also supplies the official Pro transport/cache primitives."""
