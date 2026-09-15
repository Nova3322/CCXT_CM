from unittest.mock import Mock

import ccxt
import ccxt.async_support
import ccxt.pro
import pytest

from ccxt_cm import AsyncExchange, Exchange, Extension, Registry, create_exchange
from examples.reference_exchange import EXTENSION, ReferencePro, ReferenceREST


@pytest.mark.parametrize(
    "mode,module", [("sync", ccxt), ("async", ccxt.async_support), ("pro", ccxt.pro)]
)
def test_every_official_class_is_resolved_without_wrapping(mode, module):
    registry = Registry()
    assert registry.list_exchanges(mode=mode) == sorted(module.exchanges)
    for name in module.exchanges:
        assert registry.exchange_class(name, mode=mode) is getattr(module, name)


@pytest.mark.parametrize("mode,module", [("async", ccxt.async_support), ("pro", ccxt.pro)])
async def test_official_instance_config_and_lifecycle(mode, module):
    config = {"options": {"defaultType": "spot"}, "timeout": 1234}
    exchange = create_exchange("binance", config, mode=mode)
    assert type(exchange) is module.binance
    assert exchange.timeout == 1234
    assert exchange.options["defaultType"] == "spot"
    assert config == {"options": {"defaultType": "spot"}, "timeout": 1234}
    await exchange.close()


def test_official_sync_and_custom_modes():
    sync = create_exchange("binance", mode="sync")
    assert type(sync) is ccxt.binance
    sync.session.close()
    registry = Registry()
    registry.register(EXTENSION)
    assert registry.exchange_class("cm_reference", mode="async") is ReferenceREST
    assert registry.exchange_class("cm_reference") is ReferencePro
    assert "cm_reference" in registry.list_exchanges()
    assert "cm_reference" not in registry.list_exchanges(mode="sync")
    assert not hasattr(ccxt.pro, "cm_reference")
    with pytest.raises(ccxt.NotSupported):
        registry.exchange_class("cm_reference", mode="sync")
    with pytest.raises(ValueError):
        registry.register(EXTENSION)


def test_new_sync_extension():
    class Custom(Exchange):
        id = "custom"

    registry = Registry()
    registry.register(Extension("custom", sync=Custom))
    assert registry.exchange_class("custom", mode="sync") is Custom


@pytest.mark.parametrize(
    "extension,error",
    [
        (object(), TypeError),
        (Extension("bad-name", rest=ReferenceREST), ValueError),
        (Extension("UPPER", rest=ReferenceREST), ValueError),
        (Extension("binance", rest=ReferenceREST), ValueError),
        (Extension("empty"), ValueError),
        (Extension("other", rest=ReferenceREST), ValueError),
        (Extension("cm_reference", rest=object), TypeError),
        (Extension("cm_reference", sync=ReferenceREST), TypeError),
    ],
)
def test_invalid_registrations(extension, error):
    with pytest.raises(error):
        Registry().register(extension)


def test_pro_must_share_rest():
    class Unrelated(AsyncExchange):
        id = "cm_reference"

    with pytest.raises(TypeError, match="extend"):
        Registry().register(Extension("cm_reference", rest=ReferenceREST, pro=Unrelated))


def test_errors_and_official_adoption(monkeypatch):
    registry = Registry()
    registry.register(EXTENSION)
    with pytest.raises(ValueError):
        registry.list_exchanges(mode="missing")
    with pytest.raises(ccxt.ExchangeNotAvailable):
        registry.exchange_class("does_not_exist")
    # Simulate upstream adopting the id with REST only: never silently use an old custom Pro.
    monkeypatch.setattr(ccxt, "exchanges", ccxt.exchanges + ["cm_reference"])
    with pytest.raises(ccxt.NotSupported):
        registry.exchange_class("cm_reference")
    assert "cm_reference" not in registry.list_exchanges()


def test_plugin_opt_in_atomicity_and_ambiguity(monkeypatch):
    point = Mock(name="entry")
    point.name = "fixture"
    point.load.return_value = EXTENSION
    monkeypatch.setattr("ccxt_cm.registry.metadata.entry_points", lambda **kwargs: [point])
    registry = Registry()
    assert "cm_reference" not in registry.list_exchanges()
    point.load.assert_not_called()
    with pytest.raises(ValueError):
        registry.load_extensions(["fixture", "missing"])
    assert "cm_reference" not in registry.list_exchanges()
    registry.load_extensions(["fixture"])
    assert registry.exchange_class("cm_reference") is ReferencePro
    for names in ("fixture", ["fixture", "fixture"]):
        with pytest.raises(ValueError):
            Registry().load_extensions(names)
    monkeypatch.setattr("ccxt_cm.registry.metadata.entry_points", lambda **kwargs: [point, point])
    with pytest.raises(ValueError):
        Registry().load_extensions(["fixture"])
