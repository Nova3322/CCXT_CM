"""Resolve official classes without patching CCXT or maintaining an exchange list."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module, metadata
from typing import Any, Literal

import ccxt
from ccxt.async_support.base.exchange import Exchange as UpstreamAsyncExchange

Mode = Literal["sync", "async", "pro"]
_MODULES = {"sync": "ccxt", "async": "ccxt.async_support", "pro": "ccxt.pro"}


@dataclass(frozen=True)
class Extension:
    """Explicit, process-local registration. No import-time network calls are permitted."""

    id: str
    sync: type[ccxt.Exchange] | None = None
    rest: type[UpstreamAsyncExchange] | None = None
    pro: type[UpstreamAsyncExchange] | None = None


class Registry:
    def __init__(self) -> None:
        self._extensions: dict[str, Extension] = {}

    @staticmethod
    def _module(mode: Mode):
        if mode not in _MODULES:
            raise ValueError(f"Unknown mode {mode!r}; use sync, async or pro")
        return import_module(_MODULES[mode])

    def register(self, extension: Extension) -> None:
        if not isinstance(extension, Extension):
            raise TypeError("Expected an Extension")
        if not isinstance(extension.id, str) or not extension.id.isidentifier():
            raise ValueError("Extension id must be a Python identifier")
        if extension.id != extension.id.lower():
            raise ValueError("Extension id must be lowercase")
        if extension.id in ccxt.exchanges or extension.id in self._extensions:
            raise ValueError(f"Exchange id {extension.id!r} is already registered or official")
        if not any((extension.sync, extension.rest, extension.pro)):
            raise ValueError("Extension must provide at least one class")
        for mode, cls in (
            ("sync", extension.sync),
            ("async", extension.rest),
            ("pro", extension.pro),
        ):
            if cls is None:
                continue
            base = ccxt.Exchange if mode == "sync" else UpstreamAsyncExchange
            if isinstance(cls, type) and mode == "sync" and issubclass(cls, UpstreamAsyncExchange):
                raise TypeError("An async class is not a sync implementation")
            if not isinstance(cls, type) or not issubclass(cls, base):
                raise TypeError(f"{mode} class must inherit {base.__module__}.{base.__name__}")
            if cls.id != extension.id:
                raise ValueError("Declare class attribute id equal to the registration id")
        if extension.rest and extension.pro and not issubclass(extension.pro, extension.rest):
            raise TypeError("Pro class must extend the registered async REST class")
        self._extensions[extension.id] = extension

    def exchange_class(self, exchange_id: str, *, mode: Mode = "pro"):
        module = self._module(mode)
        # Official wins even if a newer CCXT release adopts an existing extension id.
        if exchange_id in ccxt.exchanges:
            if exchange_id not in module.exchanges:
                raise ccxt.NotSupported(f"{exchange_id} has no official {mode} implementation")
            return getattr(module, exchange_id)
        extension = self._extensions.get(exchange_id)
        if extension is None:
            raise ccxt.ExchangeNotAvailable(f"Unknown exchange {exchange_id!r}")
        cls = getattr(extension, "rest" if mode == "async" else mode)
        if cls is None:
            raise ccxt.NotSupported(f"{exchange_id} has no {mode} implementation")
        return cls

    def create_exchange(
        self, exchange_id: str, config: Mapping[str, Any] | None = None, *, mode: Mode = "pro"
    ):
        """Return the actual CCXT object, preserving its API, params, errors and lifecycle."""
        return self.exchange_class(exchange_id, mode=mode)(dict(config or {}))

    def list_exchanges(self, *, mode: Mode = "pro") -> list[str]:
        module = self._module(mode)
        field = "rest" if mode == "async" else mode
        custom = {
            name
            for name, ext in self._extensions.items()
            if name not in ccxt.exchanges and getattr(ext, field) is not None
        }
        return sorted(set(module.exchanges) | custom)

    def load_extensions(self, names: Sequence[str]) -> None:
        """Opt-in installed entry points only; validate the entire batch before committing."""
        if isinstance(names, str) or len(set(names)) != len(names):
            raise ValueError("Provide a sequence of unique entry-point names")
        points = metadata.entry_points(group="ccxt_cm.exchanges")
        staged = Registry()
        staged._extensions = dict(self._extensions)
        for name in names:
            matches = [point for point in points if point.name == name]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one installed extension named {name!r}")
            staged.register(matches[0].load())
        self._extensions = staged._extensions


_default = Registry()
create_exchange = _default.create_exchange
exchange_class = _default.exchange_class
list_exchanges = _default.list_exchanges
register = _default.register
load_extensions = _default.load_extensions
