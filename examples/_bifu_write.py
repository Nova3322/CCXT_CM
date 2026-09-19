"""Shared safety boundaries for Bifu test-environment write acceptance."""

import asyncio
import os

from ccxt import NetworkError

_PREFLIGHT_ATTEMPTS = 3
_PREFLIGHT_RETRY_DELAY = 1


def credentials_from_environment():
    api_key = os.environ.get("BIFU_API_KEY")
    secret = os.environ.get("BIFU_API_SECRET")
    if not api_key or not secret:
        raise RuntimeError("BIFU_API_KEY and BIFU_API_SECRET must be set")
    return {"apiKey": api_key, "secret": secret, "timeout": 30000}


async def load_markets_with_retry(exchange):
    """Retry only the idempotent public metadata preflight."""
    for attempt in range(_PREFLIGHT_ATTEMPTS):
        try:
            return await exchange.load_markets()
        except NetworkError:
            if attempt == _PREFLIGHT_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_PREFLIGHT_RETRY_DELAY)
