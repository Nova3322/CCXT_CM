import ccxt
import pytest

from ccxt_cm import Registry
from templates.exchange import EXTENSION


async def test_empty_template_is_honest():
    registry = Registry()
    registry.register(EXTENSION)
    exchange = registry.create_exchange("target", mode="async")
    try:
        assert not any(exchange.has.values())
        with pytest.raises(ccxt.NotSupported):
            await exchange.fetch_markets()
        with pytest.raises(ccxt.NotSupported):
            registry.create_exchange("target", mode="pro")
    finally:
        await exchange.close()
