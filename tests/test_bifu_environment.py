import ccxt
import pytest

from ccxt_cm import Registry
from ccxt_cm.exchanges.bifu import BIFU_EXTENSION, BifuREST
from examples.inspect_bifu_environment import inspect_environment


@pytest.fixture
async def exchanges():
    registry = Registry()
    registry.register(BIFU_EXTENSION)
    test_exchange = registry.create_exchange(
        "bifu",
        {"apiKey": "test-key", "secret": "test-secret"},
        mode="async",
    )
    closed_production_exchange = registry.create_exchange("bifu", mode="async")
    yield registry, test_exchange, closed_production_exchange
    await test_exchange.close()
    await closed_production_exchange.close()


async def test_bifu_is_an_explicit_async_extension(exchanges):
    registry, test_exchange, _ = exchanges

    assert registry.exchange_class("bifu", mode="async") is BifuREST
    assert type(test_exchange) is BifuREST
    assert test_exchange.id == "bifu"
    assert test_exchange.has["fetchMarkets"] is True


async def test_test_environment_requires_the_standard_ccxt_switch(exchanges):
    _, test_exchange, _ = exchanges

    assert test_exchange.urls["api"] == {
        "public": None,
        "private": None,
        "ws": None,
    }
    assert test_exchange.isSandboxModeEnabled is False

    test_exchange.set_sandbox_mode(True)

    assert test_exchange.isSandboxModeEnabled is True
    assert test_exchange.urls["api"] == {
        "public": "https://flame-api.bifu.dev",
        "private": "https://flame-api.bifu.dev",
        "ws": "wss://flame-api.bifu.dev",
    }


async def test_test_and_production_instances_do_not_share_environment_or_credentials(exchanges):
    _, test_exchange, closed_production_exchange = exchanges

    test_exchange.set_sandbox_mode(True)

    assert closed_production_exchange.isSandboxModeEnabled is False
    assert closed_production_exchange.urls["api"] == {
        "public": None,
        "private": None,
        "ws": None,
    }
    assert closed_production_exchange.apiKey is None
    assert closed_production_exchange.secret is None
    assert test_exchange.apiKey == "test-key"
    assert test_exchange.secret == "test-secret"

    test_exchange.urls["api"]["public"] = "https://changed.example.invalid"
    assert closed_production_exchange.urls["api"]["public"] is None


@pytest.mark.parametrize(
    ("environment", "sandbox", "configured"),
    [("test", True, True), ("production", False, False)],
)
async def test_beginner_inspection_reports_the_environment_without_credentials(
    environment, sandbox, configured
):
    result = await inspect_environment(environment)

    assert result["id"] == "bifu"
    assert result["environment"] == environment
    assert result["sandbox"] is sandbox
    assert result["configured"] is configured
    assert "apiKey" not in result
    assert "secret" not in result


@pytest.mark.parametrize(
    "api_urls",
    [
        {
            "public": "https://api.example.invalid",
            "private": "https://api.example.invalid",
            "ws": "wss://stream.example.invalid",
        },
        {"public": "https://api.example.invalid"},
        {
            "public": "https://flame-api.bifu.dev",
            "private": "https://flame-api.bifu.dev",
            "ws": "wss://flame-api.bifu.dev",
        },
        {
            "public": "https://FLAME-API.BIFU.DEV/v1",
            "private": "https://flame-api.bifu.dev:443",
            "ws": "wss://flame-api.bifu.dev:443/stream",
        },
    ],
)
def test_production_urls_remain_disabled_until_test_acceptance_is_complete(api_urls):
    registry = Registry()
    registry.register(BIFU_EXTENSION)

    with pytest.raises(ccxt.BadRequest, match="production URLs are disabled"):
        registry.create_exchange("bifu", {"urls": {"api": api_urls}}, mode="async")
