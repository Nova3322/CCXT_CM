from types import SimpleNamespace

import ccxt
import pytest

from ccxt_cm import (
    AsyncExchange,
    Exchange,
    SpecialMethod,
    capability,
    require_capabilities,
    special_methods,
)


def test_new_bases_do_not_inherit_fake_support():
    for cls in (Exchange, AsyncExchange):
        instance = cls()
        assert set(instance.has.values()) == {False}
        assert instance.options["maxRetriesOnFailure"] == 0
        if instance.synchronous:
            instance.session.close()


def test_capability_values_and_aliases(rest):
    assert capability(rest, "fetchTicker") is True
    assert capability(rest, "fetch_ticker") is True
    assert capability(rest, "watch_order_book") is False
    assert capability(rest, "fetch_ohlcv") is False
    assert capability(rest, "not_a_method") is None
    rest.has["fetchOrders"] = "emulated"
    rest.has["futureCapability"] = None
    assert capability(rest, "future_capability") is None
    with pytest.raises(ccxt.NotSupported):
        require_capabilities(rest, "fetch_orders")
    require_capabilities(rest, "fetchOrders", allow_emulated=True)
    require_capabilities(rest, "create_order", "fetch_balance")
    with pytest.raises(ccxt.NotSupported, match="not_a_method=None"):
        require_capabilities(rest, "not_a_method", allow_emulated=True)
    rest.has["broken"] = "yes"
    with pytest.raises(ValueError):
        capability(rest, "broken")


def test_special_metadata(rest):
    specs = special_methods(rest)
    assert specs[0]["method"] == "fetch_account_limits"
    assert specs[0]["private"] is True
    assert specs[0]["mutating"] is False
    assert special_methods(SimpleNamespace()) == []
    specs[0]["private"] = False
    assert special_methods(rest)[0]["private"] is True


@pytest.mark.parametrize(
    "specs,error",
    [
        (("wrong",), TypeError),
        ((SpecialMethod("missing", "description", "doc"),), ValueError),
        ((SpecialMethod("fetch_account_limits", "", "doc"),), ValueError),
        ((SpecialMethod("fetch_account_limits", "description", ""),), ValueError),
        ((SpecialMethod("fetch_account_limits", "description", "doc"),) * 2, ValueError),
    ],
)
def test_invalid_special_metadata(rest, specs, error):
    rest.cm_special_methods = specs
    with pytest.raises(error):
        special_methods(rest)
